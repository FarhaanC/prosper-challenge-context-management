"""Round 3: note records (s2), the booking window (s3), and the other clarified behaviour
in s4 (specialty words, catalog checks, the fake schedule, check_booking)."""

import copy
import json
import pickle
from datetime import date, datetime, timedelta, timezone

import pytest

from clinic import Catalog, CatalogError, Note, Preferences, Schedule, check_booking, find_options
from conftest import NOW, new_caller, returning
from reference import DATA, LOC, PROV, SPECIALTIES, VT, ref_bookable

RAW = json.loads((DATA / "catalog.json").read_text())
EXTRAS = json.loads((DATA / "location_extras.json").read_text())
ALL = returning(list(SPECIALTIES))
KINDS = {"not_bookable", "bad_input", "doctor_not_found", "doctor_name_guess", "doctors_same_name",
         "no_other_doctor", "place_unknown", "place_ambiguous", "wish_impossible", "wish_conflict", "no_times"}


# ---------------------------------------------------------------- s2: notes are plain records
def _some_notes(catalog, schedule):
    prefs = [Preferences(doctor_name_heard="Dr. Garsha", location_hint="the Mission one", language="Klingon",
                         days=["Saturday"]),
             Preferences(location_hint="Mars"), Preferences(time_of_day="evening"),
             Preferences(doctor_name_heard="Dr. Maria Garcia"), Preferences(days=["20261013"])]
    out = []
    for vt in ["appt_002", "appt_027", "appt_065"]:
        for p in prefs:
            out += find_options(catalog, schedule, new_caller(), vt, p, NOW).notes
    return out


def test_note_is_a_record_not_a_string(catalog, schedule):
    notes = _some_notes(catalog, schedule)
    assert {n.kind for n in notes} >= {"doctor_name_guess", "place_ambiguous", "wish_impossible", "bad_input",
                                       "place_unknown", "doctors_same_name", "not_bookable"}
    for n in notes:
        assert isinstance(n, Note) and not isinstance(n, str)
        assert n.kind in KINDS and isinstance(n.say, str) and n.say
        assert str(n) == n.say
        assert n.to_dict() == {"kind": n.kind, "say": n.say}
        assert copy.copy(n) == n and copy.deepcopy(n) == n
        assert pickle.loads(pickle.dumps(n)) == n
        assert Note(n.kind, n.say) == n and hash(Note(n.kind, n.say)) == hash(n)
        assert Note("other_kind", n.say) != n and Note(n.kind, n.say + "x") != n
        json.dumps(n.to_dict())


def test_options_result_to_dict_is_json(catalog, schedule):
    r = find_options(catalog, schedule, new_caller(), "appt_027",
                     Preferences(doctor_name_heard="Dr. Garsha", location_hint="near Downtown"), NOW)
    d = json.loads(json.dumps(r.to_dict()))
    assert d["notes"] == [n.to_dict() for n in r.notes] and len(d["options"]) == len(r.options)


# ---------------------------------------------------------------- s3: the booking window
LAST = NOW.date() + timedelta(days=14)


@pytest.mark.parametrize("offset", [-1, -30, 15, 16, 400])
def test_dates_outside_the_window_are_refused(catalog, schedule, offset):
    d = (NOW.date() + timedelta(days=offset)).isoformat()
    r = find_options(catalog, schedule, ALL, "appt_002", Preferences(days=[d]), NOW)
    assert r.options == [] and [n.kind for n in r.notes] == ["bad_input"], [str(n) for n in r.notes]
    say = r.notes[0].say
    # "a bad_input note naming the window": the first and last day of the window
    assert ("6 October" in say or "October 6" in say or "2026-10-06" in say), say
    assert ("20 October" in say or "October 20" in say or "2026-10-20" in say), say


@pytest.mark.parametrize("offset", [0, 1, 7, 14])
def test_dates_inside_the_window_are_used(catalog, schedule, offset):
    d = NOW.date() + timedelta(days=offset)
    r = find_options(catalog, schedule, ALL, "appt_002", Preferences(days=[d.isoformat()]), NOW)
    assert "bad_input" not in [n.kind for n in r.notes]
    if r.options and d.weekday() < 5:
        assert all(o.start.date() == d for o in r.options)


def test_out_of_window_date_among_good_days_is_still_refused(catalog, schedule):
    far = (NOW.date() + timedelta(days=20)).isoformat()
    r = find_options(catalog, schedule, ALL, "appt_002", Preferences(days=["Thursday", far]), NOW)
    assert r.options == [] and {n.kind for n in r.notes} == {"bad_input"}


@pytest.mark.parametrize("day", ["20261013", "2026-1-13", "13-10-2026", "2026/10/13", "2026-10-13T09:00",
                                 "2026-02-30", "Oct 13"])
def test_only_yyyy_mm_dd(catalog, schedule, day):
    r = find_options(catalog, schedule, ALL, "appt_002", Preferences(days=[day]), NOW)
    assert r.options == [] and [n.kind for n in r.notes] == ["bad_input"], (day, [str(n) for n in r.notes])


@pytest.mark.parametrize("days", [[None], [""], ["   "], [None, "Thursday"], ["", "Thursday"]])
def test_blank_or_none_days_are_ignored(catalog, schedule, days):
    r = find_options(catalog, schedule, ALL, "appt_002", Preferences(days=days), NOW)
    assert "bad_input" not in [n.kind for n in r.notes] and r.options, [str(n) for n in r.notes]
    assert not any("None" in n.say for n in r.notes)
    if "Thursday" in days:
        assert all(o.start.strftime("%A") == "Thursday" for o in r.options)


# ---------------------------------------------------------------- s4: specialty words
@pytest.mark.parametrize("word,spec", [
    ("dermatologist", "Dermatology"), ("pediatrician", "Pediatrics"), ("allergist", "Allergy/Immunology"),
    ("dentist", "Dental"), ("orthopedist", "Orthopedics"), ("psychiatrist", "Psychiatry"),
    ("physical therapist", "Physical Therapy"), ("cardiologist", "Cardiology"), ("neurologist", "Neurology"),
    ("gastroenterologist", "Gastroenterology"), ("radiologist", "Radiology"), ("urologist", "Urology"),
    ("pulmonologist", "Pulmonology"), ("endocrinologist", "Endocrinology"), ("ophthalmologist", "Ophthalmology"),
    ("Dermatologists", "Dermatology"), ("PEDIATRICIAN", "Pediatrics"), ("immunologist", "Allergy/Immunology"),
])
def test_doctor_words_from_specialty_names(catalog, word, spec):
    assert catalog.match_specialty(word) == spec, word


@pytest.mark.parametrize("word", ["physician", "doctor", "surgeon", "therapist", "oncologist", "rheumatologist"])
def test_words_that_match_nothing(catalog, word):
    assert catalog.match_specialty(word) is None, (word, catalog.match_specialty(word))


@pytest.mark.parametrize("word,wrong", [("podiatrist", "Pediatrics"), ("nephrologist", "Neurology"),
                                        ("hematologist", "Dermatology"), ("audiologist", "Radiology")])
def test_other_doctors_are_not_guessed_as_a_different_specialty(catalog, word, wrong):
    """My own adversarial words: real kinds of doctor the catalog doesn't have, one or two letters
    away from a word we build. Like 'physician' (spec: matches nothing), they must not be mapped to
    a different specialty: a foot doctor is not a children's doctor."""
    assert catalog.match_specialty(word) != wrong, (word, catalog.match_specialty(word))


# ---------------------------------------------------------------- s4: catalog checks
def _raw():
    return copy.deepcopy(RAW)


def test_missing_hours_is_a_catalog_error():
    raw = _raw()
    del raw["locations"][0]["hours"]
    with pytest.raises(CatalogError) as e:
        Catalog(raw, EXTRAS)
    assert "hours" in str(e.value) and raw["locations"][0]["id"] in str(e.value)


@pytest.mark.parametrize("section,field", [("locations", "name"), ("locations", "address"), ("providers", "languages"),
                                           ("providers", "location_ids"), ("providers", "appointment_type_ids"),
                                           ("providers", "accepting_new_patients"), ("appointment_types", "duration_min"),
                                           ("appointment_types", "requires_referral"), ("appointment_types", "specialty")])
def test_missing_required_fields_are_catalog_errors(section, field):
    raw = _raw()
    del raw[section][1][field]
    with pytest.raises(CatalogError) as e:
        Catalog(raw, EXTRAS)
    assert field in str(e.value)


@pytest.mark.parametrize("section", ["locations", "providers", "appointment_types"])
def test_repeated_ids_are_catalog_errors(section):
    raw = _raw()
    raw[section].append(copy.deepcopy(raw[section][0]))
    with pytest.raises(CatalogError) as e:
        Catalog(raw, EXTRAS)
    assert raw[section][0]["id"] in str(e.value)


def test_every_problem_is_listed_at_once():
    raw = _raw()
    del raw["locations"][2]["hours"]
    raw["providers"].append(copy.deepcopy(raw["providers"][0]))
    del raw["appointment_types"][3]["name"]
    with pytest.raises(CatalogError) as e:
        Catalog(raw, EXTRAS)
    msg = str(e.value)
    assert "hours" in msg and raw["providers"][0]["id"] in msg and "name" in msg, msg


@pytest.mark.parametrize("breaker", ["no_providers_list", "providers_not_list", "unknown_location", "unknown_visit",
                                     "bad_hours", "no_coords", "provider_no_sites"])
def test_broken_data_never_crashes_with_anything_but_catalog_error(breaker):
    raw, extras = _raw(), copy.deepcopy(EXTRAS)
    if breaker == "no_providers_list":
        del raw["providers"]
    elif breaker == "providers_not_list":
        raw["providers"] = {"a": 1}
    elif breaker == "unknown_location":
        raw["providers"][0]["location_ids"] = ["loc_999"]
    elif breaker == "unknown_visit":
        raw["providers"][0]["appointment_type_ids"].append("appt_999")
    elif breaker == "bad_hours":
        raw["locations"][0]["hours"] = "9 to 5"
    elif breaker == "no_coords":
        del extras["locations"]["loc_003"]["lat"]
    elif breaker == "provider_no_sites":
        raw["providers"][0]["location_ids"] = []
    with pytest.raises(CatalogError):
        Catalog(raw, extras)


# ---------------------------------------------------------------- s4: fake schedule rotation
def _working_days():
    return [NOW.date() + timedelta(days=i) for i in range(15) if (NOW.date() + timedelta(days=i)).weekday() < 5]


def test_each_doctor_visits_every_site_and_rotates_daily(catalog):
    sch = Schedule(catalog)
    days = _working_days()
    for pid, p in PROV.items():
        seen = [sch.location_on(pid, d) for d in days]
        assert set(seen) == set(p["location_ids"]), (pid, seen)
        if len(p["location_ids"]) > 1:
            assert all(a != b for a, b in zip(seen, seen[1:])), (pid, seen)  # "rotating day by day"


def test_open_times_only_at_the_site_of_the_day(catalog):
    sch = Schedule(catalog)
    for pid, p in list(PROV.items())[:20]:
        for lid in p["location_ids"]:
            for s in sch.open_slots(pid, lid, 30, NOW):
                assert sch.location_on(pid, s.date()) == lid


def test_doctor_with_ten_sites_works_at_each(catalog):
    raw, extras = _raw(), copy.deepcopy(EXTRAS)
    for i in range(8, 10):
        loc = copy.deepcopy(raw["locations"][0])
        loc["id"] = f"loc_9{i}"
        loc["name"] = f"Extra Site {i}"
        raw["locations"].append(loc)
        extras["locations"][loc["id"]] = dict(extras["locations"]["loc_000"])
    raw["providers"][0]["location_ids"] = [l["id"] for l in raw["locations"]]
    assert len(raw["providers"][0]["location_ids"]) == 10
    cat = Catalog(raw, extras)
    sch = Schedule(cat)
    pid = raw["providers"][0]["id"]
    for start in [NOW] + [NOW + timedelta(days=k) for k in range(1, 7)]:
        days = [start.date() + timedelta(days=i) for i in range(15) if (start.date() + timedelta(days=i)).weekday() < 5]
        seen = {sch.location_on(pid, d) for d in days}
        assert seen == set(raw["providers"][0]["location_ids"]), (start, len(seen))


# ---------------------------------------------------------------- s4: check_booking with odd input
ODD = [None, ["prov_001"], {"id": "prov_001"}, 1, 1.5, ("prov_001",), b"prov_001", "", "   ", object()]


@pytest.mark.parametrize("odd", ODD, ids=[repr(type(x).__name__) + str(i) for i, x in enumerate(ODD)])
@pytest.mark.parametrize("position", ["visit", "provider", "location"])
def test_check_booking_refuses_odd_ids_politely(catalog, schedule, odd, position):
    args = {"visit": "appt_027", "provider": "prov_001", "location": "loc_004"}
    args[position] = odd
    out = check_booking(catalog, schedule, new_caller(), args["visit"], args["provider"], args["location"],
                        NOW + timedelta(days=1), NOW)
    assert isinstance(out, list) and out and all(isinstance(x, str) and x for x in out)


@pytest.mark.parametrize("start", [None, "2026-10-07T09:00", date(2026, 10, 7), 0, [],
                                   datetime(2026, 10, 7, 9, 0, tzinfo=timezone.utc)])
def test_check_booking_odd_start(catalog, schedule, start):
    out = check_booking(catalog, schedule, new_caller(), "appt_027", "prov_001", "loc_004", start, NOW)
    assert isinstance(out, list) and out


def test_check_booking_accepts_an_offered_option(catalog, schedule):
    for vt in ["appt_027", "appt_002"]:
        for o in find_options(catalog, schedule, new_caller(), vt, Preferences(), NOW).options:
            assert check_booking(catalog, schedule, new_caller(), vt, o.provider_id, o.location_id, o.start, NOW) == []


# ---------------------------------------------------------------- regressions from rounds 1 and 2
def test_regression_knee_mri_demo(catalog, schedule, directory):
    james = directory.lookup("James Wilson", "1984-03-12").caller
    r = find_options(catalog, schedule, james, "appt_065", Preferences(), NOW)
    assert {(o.provider_id, o.location_id) for o in r.options} == {("prov_014", "loc_004"), ("prov_015", "loc_005")}
    assert not find_options(catalog, schedule, new_caller(), "appt_065", Preferences(), NOW).bookable


def test_regression_no_option_breaks_a_rule_whole_catalog(catalog, schedule):
    from reference import ref_combo_ok
    bad = []
    for kind, caller, is_new, refs in [("new", new_caller(), True, []), ("all", ALL, False, list(SPECIALTIES))]:
        for vt in VT:
            r = find_options(catalog, schedule, caller, vt, Preferences(location_hint="near Downtown"), NOW)
            if r.bookable != ref_bookable(is_new, refs, vt):
                bad.append((kind, vt, "bookable"))
            for o in r.options:
                if not ref_combo_ok(is_new, refs, vt, o.provider_id, o.location_id):
                    bad.append((kind, vt, o.provider_id, o.location_id))
                if o.start.weekday() >= 5 or not (8 <= o.start.hour < 17) or o.start.hour == 12:
                    bad.append((kind, vt, "time", o.start))
                if not (NOW + timedelta(hours=2) <= o.start and o.start.date() <= LAST):
                    bad.append((kind, vt, "window", o.start))
    assert not bad, bad[:5]
