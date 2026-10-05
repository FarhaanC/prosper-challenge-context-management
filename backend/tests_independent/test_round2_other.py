"""Round 2, spec change 1 (change table details) and 7 (other behaviour)."""

import copy
import json
from datetime import datetime, timedelta

import pytest

from clinic import (BOOKING, VISIT_TYPE, BookingCard, Catalog, CatalogError, Choices, Preferences, Schedule,
                    SlotTaken, alternatives_for, answer_question, clinic_now, find_options)
from conftest import NOW, new_caller, returning
from reference import DATA, LOC, PROV, SPECIALTIES, VT, last_name, ref_bookable

RAW = json.loads((DATA / "catalog.json").read_text())
EXTRAS = json.loads((DATA / "location_extras.json").read_text())


def full_card(caller=None):
    c = BookingCard(caller=caller or new_caller())
    c.choices = Choices(specialty="Dermatology", visit_type_id="appt_027", provider_id="prov_001",
                        location_id="loc_004", slot=NOW + timedelta(days=2))
    return c


# ---------------------------------------------------------------- change table details
def test_unknown_change_raises_and_clears_nothing():
    c = full_card()
    c.preferences.days = ["Monday"]
    before = (copy.deepcopy(c.choices), copy.deepcopy(c.preferences))
    c.offered_options = ["sentinel"]
    with pytest.raises(ValueError):
        c.change_choice("insurance", "Aetna")
    assert (c.choices, c.preferences) == before and c.offered_options == ["sentinel"]


@pytest.mark.parametrize("what", ["doctor", "location", "time"])
def test_latest_is_set(what):
    c = full_card()
    c.change_choice(what, "Thursday" if what == "time" else "x")
    assert c.preferences.latest == what


def test_visit_type_change_carries_doctor_and_place_as_wishes_and_clears_choices():
    c = full_card()
    assert c.change_choice("visit_type", "knee MRI") == VISIT_TYPE
    assert c.choices == Choices()
    assert c.preferences.preferred_provider_id == "prov_001" and c.preferences.preferred_location_id == "loc_004"


@pytest.mark.parametrize("what,value", [("doctor", "Dr. Kenji Kim"), ("location", "the Midtown one"),
                                        ("time", "Monday")])
def test_at_most_one_doctor_and_one_place_wish(what, value):
    c = full_card()
    c.preferences.doctor_name_heard = "Dr. Daniel Chen"
    c.preferences.location_hint = "Downtown"
    c.change_choice(what, value)
    p = c.preferences
    assert not (p.doctor_name_heard and p.preferred_provider_id), p
    assert not (p.location_hint and p.preferred_location_id), p


def test_time_change_plain_value_is_day_wish():
    c = full_card()
    c.change_choice("time", "Thursday")
    assert c.preferences.days == ["Thursday"]


@pytest.mark.parametrize("value", ["any day", "Any day", "any", "ANY TIME"])
def test_any_day_clears_day_wish(value):
    c = full_card()
    c.preferences.days = ["Monday"]
    c.change_choice("time", value)
    assert c.preferences.days == []


def test_any_time_clears_time_of_day_wish():
    """Spec 1: '"any day" / "any time" clears the day or time wish.' A caller who said
    'morning' and now says 'any time is fine' should lose the morning restriction."""
    c = full_card()
    c.preferences.time_of_day = "morning"
    c.change_choice("time", "any time")
    assert c.preferences.time_of_day == "", c.preferences


def test_any_time_via_time_of_day_argument():
    c = full_card()
    c.preferences.time_of_day = "morning"
    c.change_choice("time", time_of_day="any time")
    assert c.preferences.time_of_day == ""


def test_offers_are_dropped_on_any_change():
    c = full_card()
    c.offered_options = ["x"]
    c.change_choice("doctor", "Dr. Kenji Kim")
    assert c.offered_options == [] and c.offered("1") is None


# ---------------------------------------------------------------- option numbers through a call
def test_option_numbers_keep_counting_and_old_ones_expire(catalog, schedule):
    caller = returning(list(SPECIALTIES))
    card = BookingCard(caller=caller)
    r1 = find_options(catalog, schedule, caller, "appt_002", Preferences(), NOW,
                      first_option_number=card.next_option_number)
    assert [o.option_id for o in r1.options] == ["1", "2", "3"]
    card.remember_offer(r1.options)
    assert card.next_option_number == 4
    assert card.offered("2") is r1.options[1] and card.offered(2) is r1.options[1] and card.offered(" 3 ")
    r2 = find_options(catalog, schedule, caller, "appt_002", Preferences(days=["Thursday"]), NOW,
                      first_option_number=card.next_option_number)
    assert [o.option_id for o in r2.options] == ["4", "5", "6"]
    card.remember_offer(r2.options)
    assert card.offered("2") is None and card.offered("5") is r2.options[1]
    assert card.next_option_number == 7
    assert card.offered("7") is None and card.offered("0") is None and card.offered("") is None


def test_remember_empty_offer_keeps_counter(catalog, schedule):
    card = BookingCard(caller=new_caller())
    card.next_option_number = 9
    card.remember_offer([])
    assert card.next_option_number == 9 and card.offered("9") is None


def test_card_to_dict_with_offers_is_json(catalog, schedule):
    caller = new_caller()
    card = full_card(caller)
    card.remember_offer(find_options(catalog, schedule, caller, "appt_027", Preferences(), NOW).options)
    d = json.loads(json.dumps(card.to_dict()))
    assert len(d["offered_options"]) == 3 and d["choices"]["slot"]


# ---------------------------------------------------------------- slots
def test_book_then_slot_taken(catalog):
    s = Schedule(catalog)
    start = s.open_slots("prov_001", "loc_004", 30, NOW)[0]
    s.book("prov_001", start, 30)
    with pytest.raises(SlotTaken):
        s.book("prov_001", start, 30)
    assert start not in s.open_slots("prov_001", "loc_004", 30, NOW)


def test_overlapping_longer_booking_is_taken(catalog):
    s = Schedule(catalog)
    slots = s.open_slots("prov_014", "loc_004", 60, NOW)
    start = slots[0]
    s.book("prov_014", start + timedelta(minutes=30), 30)
    with pytest.raises(SlotTaken):
        s.book("prov_014", start, 60)


@pytest.mark.parametrize("hour,minute", [(12, 0), (12, 30), (7, 30), (17, 0), (9, 15)])
def test_book_outside_open_blocks_is_taken(catalog, hour, minute):
    s = Schedule(catalog)
    day = next(d for d in (NOW + timedelta(days=i) for i in range(1, 8)) if d.weekday() < 5)
    with pytest.raises(SlotTaken):
        s.book("prov_001", day.replace(hour=hour, minute=minute), 30)


def test_book_on_weekend_is_taken(catalog):
    s = Schedule(catalog)
    sat = datetime(2026, 10, 10, 9, 0)
    with pytest.raises(SlotTaken):
        s.book("prov_001", sat, 30)


def test_book_a_block_that_was_never_open(catalog):
    s = Schedule(catalog)
    day = NOW.date() + timedelta(days=1)
    lid = s.location_on("prov_001", day)
    open_ = set(s.open_slots("prov_001", lid, 30, NOW))
    t = datetime.combine(day, datetime.min.time()).replace(hour=8)
    while t.hour < 17:
        if t not in open_ and not (12 <= t.hour < 13):
            with pytest.raises(SlotTaken):
                s.book("prov_001", t, 30)
            return
        t += timedelta(minutes=30)


def test_clinic_now_is_san_francisco_plain_datetime():
    from zoneinfo import ZoneInfo
    n = clinic_now()
    assert n.tzinfo is None
    sf = datetime.now(ZoneInfo("America/Los_Angeles")).replace(tzinfo=None)
    assert abs((sf - n).total_seconds()) < 120


def test_repeatable_across_fresh_objects():
    a = Schedule(Catalog.load()).open_slots("prov_027", "loc_005", 30, NOW)
    b = Schedule(Catalog.load()).open_slots("prov_027", "loc_005", 30, NOW)
    assert a == b


# ---------------------------------------------------------------- catalog validation
def broken(fn):
    raw, extras = copy.deepcopy(RAW), copy.deepcopy(EXTRAS)
    fn(raw, extras)
    return raw, extras


@pytest.mark.parametrize("name,fn,needle", [
    ("no coords", lambda r, e: e["locations"].pop("loc_003"), "loc_003"),
    ("no lat", lambda r, e: e["locations"]["loc_003"].pop("lat"), "loc_003"),
    ("bad hours", lambda r, e: r["locations"][2].__setitem__("hours", "9 to 5"), "loc_002"),
    ("backwards hours", lambda r, e: r["locations"][2].__setitem__("hours", "Mon-Fri 17:00-8:00"), "loc_002"),
    ("unknown loc", lambda r, e: r["providers"][0]["location_ids"].append("loc_999"), "loc_999"),
    ("unknown vt", lambda r, e: r["providers"][0]["appointment_type_ids"].append("appt_999"), "appt_999"),
])
def test_catalog_errors(name, fn, needle):
    with pytest.raises(CatalogError) as e:
        Catalog(*broken(fn))
    assert needle in str(e.value), name


def test_catalog_error_lists_every_problem():
    def fn(r, e):
        e["locations"].pop("loc_001")
        r["locations"][4]["hours"] = "always"
        r["providers"][3]["location_ids"].append("loc_777")
        r["providers"][5]["appointment_type_ids"].append("appt_888")
    with pytest.raises(CatalogError) as e:
        Catalog(*broken(fn))
    for needle in ("loc_001", "loc_004", "loc_777", "appt_888"):
        assert needle in str(e.value), needle


def test_catalog_missing_hours_field_is_a_catalog_error():
    with pytest.raises(CatalogError):
        Catalog(*broken(lambda r, e: r["locations"][0].pop("hours")))


def test_good_catalog_loads():
    Catalog(copy.deepcopy(RAW), copy.deepcopy(EXTRAS))


# ---------------------------------------------------------------- alternatives_for
PRIMARY = {"General", "Family Medicine", "Internal Medicine"}


@pytest.mark.parametrize("refused", ["appt_065", "appt_062", "appt_033" if "appt_033" in VT else "appt_029"])
def test_alternatives_for_new_patient(catalog, refused):
    alts = alternatives_for(catalog, new_caller(), refused)
    assert alts
    for vt in alts:
        a = VT[vt.id]
        assert a["specialty"] in PRIMARY and a["new_patients_allowed"] and ref_bookable(True, [], vt.id)
        assert "new patient" in a["name"].lower(), a["name"]


@pytest.mark.parametrize("refused", ["appt_065", "appt_062"])
def test_alternatives_for_returning_patient(catalog, refused):
    alts = alternatives_for(catalog, returning([]), refused)
    assert alts
    for vt in alts:
        a = VT[vt.id]
        assert a["specialty"] in PRIMARY and ref_bookable(False, [], vt.id)
        assert "follow" in a["name"].lower(), a["name"]


# ---------------------------------------------------------------- specialty words
@pytest.mark.parametrize("word,spec", [
    ("dermatologist", "Dermatology"), ("Dermatologist", "Dermatology"), ("pediatrician", "Pediatrics"),
    ("allergist", "Allergy/Immunology"), ("physical therapist", "Physical Therapy"),
    ("Allergy", "Allergy/Immunology"), ("immunology", "Allergy/Immunology"), ("OBGYN", "OB/GYN"),
    ("ob-gyn", "OB/GYN"), ("cardiologist", "Cardiology"), ("neurologist", "Neurology"),
    ("radiologist", "Radiology"), ("dermatology", "Dermatology"), ("Family Medicine", "Family Medicine"),
])
def test_match_specialty_words(catalog, word, spec):
    assert catalog.match_specialty(word) == spec


@pytest.mark.parametrize("word", ["astrology", "dentist?!", "plumber", "", "doctor", "ent specialist please"])
def test_match_specialty_rejects_nonsense(catalog, word):
    got = catalog.match_specialty(word)
    assert got in (None, "ENT" if "ent" in word else None, "Dental" if "dent" in word else None)


def test_every_specialty_name_matches_itself(catalog):
    for s in SPECIALTIES:
        assert catalog.match_specialty(s) == s and catalog.match_specialty(s.upper()) == s


# ---------------------------------------------------------------- answer_question
def test_answer_question_lists_all_seven_chens(catalog):
    a = answer_question(catalog, "doctor", "Dr. Chen")
    chens = sorted(p["name"] for p in PROV.values() if last_name(p["name"]) == "Chen")
    assert sorted(r["name"].split(",")[0] for r in a["results"]) == chens
    assert str(len(chens)) in a["message"]


@pytest.mark.parametrize("name", ["Dr. Garsha", "Dr. Cohen", "Dr. John Garcia"])
def test_answer_question_flags_approximate(catalog, name):
    a = answer_question(catalog, "doctor", name)
    assert a["found"] and "exactly" in a["message"].lower()


def test_answer_question_exact_single_doctor(catalog):
    a = answer_question(catalog, "doctor", "Dr. Grace Rodriguez")
    assert len(a["results"]) == 1 and a["results"][0]["specialty"] == "Orthopedics"
    assert a["results"][0]["locations"] == ["Richmond Care Center"]


def test_answer_question_location_and_unknowns(catalog):
    a = answer_question(catalog, "location", "the Midtown one")
    assert a["results"][0]["name"] == "Midtown Medical Group" and "2099 Market St" in a["results"][0]["address"]
    assert answer_question(catalog, "doctor", "Dr. Zzyzx")["found"] is False
    assert answer_question(catalog, "weather", "today")["found"] is False
    assert answer_question(catalog, "doctor", "")["found"] is False
    assert answer_question(catalog, None, None)["found"] is False


def test_answer_question_the_mission_is_ambiguous(catalog):
    a = answer_question(catalog, "location", "the Mission")
    assert len(a["results"]) == 2 and "which" in a["message"].lower()


def test_answer_question_visit_type_knee_mri(catalog):
    a = answer_question(catalog, "visit_type", "knee MRI")
    assert a["results"][0]["name"] == "MRI - Knee" and a["results"][0]["needs_referral"] is True
