"""The booking card: the change table (plan + decision 26), and read-back = card."""

from datetime import datetime

import pytest

from clinic import BOOKING, VISIT_TYPE, BookingCard, Choices, Preferences, find_options, spoken_time
from conftest import NOW, new_caller, returning
from reference import LOC, PROV, VT

SLOT = datetime(2026, 10, 8, 10, 0)


def full_card(caller=None):
    c = BookingCard(caller=caller or new_caller())
    c.choices = Choices(specialty="Dermatology", visit_type_id="appt_027", provider_id="prov_001",
                        location_id="loc_004", slot=SLOT)
    return c


# ---------------------------------------------------------------- the change table
@pytest.mark.parametrize("what", ["visit_type", "Visit Type", "VISIT_TYPE"])
def test_change_visit_type(what):
    c = full_card()
    stage = c.change_choice(what, "knee MRI")
    assert stage == VISIT_TYPE
    ch = c.choices
    assert (ch.specialty, ch.visit_type_id, ch.provider_id, ch.location_id, ch.slot) == ("", "", "", "", None)
    assert c.preferences.visit_description == "knee MRI"


@pytest.mark.parametrize("what", ["doctor", "Doctor"])
def test_change_doctor(what):
    c = full_card()
    stage = c.change_choice(what, "Dr. Kenji Kim")
    assert stage == BOOKING
    ch = c.choices
    assert ch.visit_type_id == "appt_027" and ch.specialty == "Dermatology"
    assert (ch.provider_id, ch.location_id, ch.slot) == ("", "", None)
    assert c.preferences.doctor_name_heard == "Dr. Kenji Kim"
    assert c.preferences.preferred_location_id == "loc_004"   # old location kept as a wish
    assert c.preferences.preferred_provider_id != "prov_001"  # old doctor not kept


def test_change_location():
    c = full_card()
    stage = c.change_choice("location", "the Midtown one")
    assert stage == BOOKING
    ch = c.choices
    assert ch.visit_type_id == "appt_027"
    assert (ch.provider_id, ch.location_id, ch.slot) == ("", "", None)
    assert c.preferences.location_hint == "the Midtown one"
    assert c.preferences.preferred_provider_id == "prov_001"  # old doctor kept as a wish
    assert c.preferences.preferred_location_id != "loc_004"


def test_change_time_with_structured_days():
    c = full_card()
    stage = c.change_choice("time", days=["Thursday"], time_of_day="afternoon")
    assert stage == BOOKING
    ch = c.choices
    assert ch.visit_type_id == "appt_027"
    assert (ch.provider_id, ch.location_id, ch.slot) == ("", "", None)
    assert c.preferences.preferred_provider_id == "prov_001"
    assert c.preferences.preferred_location_id == "loc_004"
    assert c.preferences.days == ["Thursday"] and c.preferences.time_of_day == "afternoon"


def test_change_time_new_value_not_silently_dropped():
    """Plan: change_choice 'records the new value as a preference'. If the tool is
    called with new_value='Thursday' only, the wish must not vanish."""
    c = full_card()
    c.change_choice("time", "Thursday")
    p = c.preferences
    assert "Thursday" in p.days or "thursday" in [d.lower() for d in p.days], p


@pytest.mark.parametrize("what", ["doctor", "location", "time"])
def test_change_without_visit_type_goes_to_visit_type_stage(what):
    c = BookingCard(caller=new_caller())
    assert c.change_choice(what, "x") == VISIT_TYPE


def test_unknown_change_does_not_clear_anything():
    c = full_card()
    try:
        c.change_choice("insurance", "Aetna")
    except Exception:
        pass
    assert c.choices.provider_id == "prov_001" and c.choices.slot == SLOT


# ---------------------------------------------------------------- change table, end to end
def test_demo_skin_check_then_knee_mri(catalog, schedule, directory):
    james = directory.lookup("James Wilson").caller
    c = BookingCard(caller=james, preferences=Preferences(visit_description="skin check", doctor_name_heard="Dr. Garcia"))
    c.choices.specialty, c.choices.visit_type_id = "Dermatology", "appt_027"
    opts = find_options(catalog, schedule, james, "appt_027", c.preferences, NOW).options
    o = opts[0]
    c.choices.provider_id, c.choices.location_id, c.choices.slot = o.provider_id, o.location_id, o.start
    assert c.change_choice("visit_type", "knee MRI") == VISIT_TYPE
    assert c.choices.provider_id == ""
    c.choices.specialty, c.choices.visit_type_id = "Radiology", "appt_065"
    r = find_options(catalog, schedule, james, "appt_065", c.preferences, NOW)
    assert r.options and {(x.provider_id, x.location_id) for x in r.options} <= {("prov_014", "loc_004"), ("prov_015", "loc_005")}
    # the old doctor is not silently dropped: a note says they can't do it
    assert any(PROV[o.provider_id]["name"] in n for n in r.notes), r.notes


def test_location_change_to_place_old_doctor_does_not_work(catalog, schedule):
    """Plan: location change clears 'location, slot (and doctor, if they don't work there)'.
    Dr. Daniel Chen works Downtown + Richmond only. Caller switches to 'the Midtown one'.
    Midtown has valid dermatologists (Dr. Kenji Kim). Expected: Midtown options."""
    caller = new_caller()
    c = full_card(caller)
    c.change_choice("location", "the Midtown one")
    r = find_options(catalog, schedule, caller, "appt_027", c.preferences, NOW)
    assert r.options and all(o.location_id == "loc_005" for o in r.options), \
        ([(o.provider_name, o.location_name) for o in r.options], r.notes)


def test_location_change_to_place_old_doctor_works(catalog, schedule):
    # Dr. Daniel Chen also works at Richmond: keep him there.
    caller = new_caller()
    c = full_card(caller)
    c.change_choice("location", "Richmond")
    r = find_options(catalog, schedule, caller, "appt_027", c.preferences, NOW)
    assert r.options and all((o.provider_id, o.location_id) == ("prov_001", "loc_007") for o in r.options)


def test_doctor_change_new_doctor_works_at_old_location(catalog, schedule):
    # Kenji Kim works Downtown too: location kept.
    caller = new_caller()
    c = full_card(caller)
    c.change_choice("doctor", "Dr. Kenji Kim")
    r = find_options(catalog, schedule, caller, "appt_027", c.preferences, NOW)
    assert r.options and all((o.provider_id, o.location_id) == ("prov_027", "loc_004") for o in r.options)


def test_doctor_change_new_doctor_not_at_old_location(catalog, schedule):
    # Daniel Smith works Mission District + Richmond, not Downtown: location must give way.
    caller = new_caller()
    c = full_card(caller)
    c.change_choice("doctor", "Dr. Daniel Smith")
    r = find_options(catalog, schedule, caller, "appt_027", c.preferences, NOW)
    assert r.options and all(o.provider_id == "prov_035" for o in r.options)
    assert r.notes  # tells the caller Downtown isn't possible with him


def test_time_change_keeps_doctor_and_place_when_they_fit(catalog, schedule, directory):
    james = directory.lookup("James Wilson").caller
    c = BookingCard(caller=james)
    c.choices = Choices(specialty="Radiology", visit_type_id="appt_065", provider_id="prov_014",
                        location_id="loc_004", slot=SLOT)
    days_free = {s.strftime("%A") for s in schedule.open_slots("prov_014", "loc_004", 45, NOW)}
    day = sorted(days_free)[0]
    c.change_choice("time", days=[day])
    r = find_options(catalog, schedule, james, "appt_065", c.preferences, NOW)
    assert r.options and all((o.provider_id, o.location_id) == ("prov_014", "loc_004") and o.start.strftime("%A") == day
                             for o in r.options)


# ---------------------------------------------------------------- read-back
def test_read_back_matches_card(catalog, schedule, directory):
    james = directory.lookup("James Wilson").caller
    o = find_options(catalog, schedule, james, "appt_065", Preferences(), NOW).options[0]
    c = BookingCard(caller=james)
    c.choices = Choices(specialty="Radiology", visit_type_id="appt_065", provider_id=o.provider_id,
                        location_id=o.location_id, slot=o.start)
    text = c.read_back(catalog)
    assert VT["appt_065"]["name"] in text
    assert PROV[o.provider_id]["name"] in text
    assert LOC[o.location_id]["name"] in text and LOC[o.location_id]["address"] in text
    assert spoken_time(o.start) in text
    assert str(VT["appt_065"]["duration_min"]) in text
    # nothing from another doctor/location/visit type leaks in
    for pid, p in PROV.items():
        if p["name"] != PROV[o.provider_id]["name"]:
            assert p["name"] not in text
    # the option the caller heard and the read-back describe the same appointment
    assert spoken_time(o.start) in o.spoken


def test_read_back_after_change_uses_new_card(catalog):
    c = full_card()
    before = c.read_back(catalog)
    c.choices.provider_id, c.choices.location_id = "prov_027", "loc_005"
    after = c.read_back(catalog)
    assert "Kenji Kim" in after and "Midtown" in after and "Daniel Chen" not in after and before != after


def test_summary_shows_card(catalog):
    c = full_card(returning(["Radiology"], name="James Wilson"))
    s = c.summary(catalog)
    assert "James Wilson" in s and "returning" in s and "Radiology" in s
    assert "Skin Cancer Screening" in s and "Daniel Chen" in s and "Downtown" in s
    assert BookingCard().summary(catalog)


def test_card_to_dict_serialisable():
    import json
    json.dumps(full_card().to_dict())
