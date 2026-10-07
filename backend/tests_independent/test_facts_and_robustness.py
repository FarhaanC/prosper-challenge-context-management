"""answer_question facts, and robustness to bad input."""

import pytest

from clinic import Preferences, answer_question, can_book_visit_type, find_options
from conftest import NOW, new_caller
from reference import LOC


# ---------------------------------------------------------------- locations
def test_location_facts_downtown(catalog):
    r = answer_question(catalog, "location", "Downtown")
    assert r["found"] and len(r["results"]) == 1
    x = r["results"][0]
    raw = LOC["loc_004"]
    assert x["name"] == raw["name"] and raw["address"] in x["address"]
    assert x["phone"] == raw["phone"] and x["hours"] == raw["hours"]
    assert x["neighbourhood"] == "Downtown"


def test_location_facts_ambiguous(catalog):
    r = answer_question(catalog, "location", "Mission")
    assert r["found"] and {x["name"] for x in r["results"]} == {LOC["loc_000"]["name"], LOC["loc_001"]["name"]}
    assert r["message"]


def test_location_facts_landmark(catalog):
    r = answer_question(catalog, "location", "Chinatown")
    assert r["found"] and r["results"][0]["name"] == LOC["loc_004"]["name"]


@pytest.mark.parametrize("name", ["Narnia", "", None])
def test_location_unknown(catalog, name):
    assert answer_question(catalog, "location", name)["found"] is False


# ---------------------------------------------------------------- doctors
def test_doctor_facts(catalog):
    r = answer_question(catalog, "doctor", "Dr. Hannah Nguyen")
    assert r["found"] and len(r["results"]) == 1
    x = r["results"][0]
    assert x["specialty"] == "Radiology" and set(x["languages"]) == {"English", "Vietnamese"}
    assert set(x["locations"]) == {LOC["loc_000"]["name"], LOC["loc_005"]["name"]}
    assert x["taking_new_patients"] is True


def test_doctor_facts_duplicate(catalog):
    r = answer_question(catalog, "doctor", "Linda Ramirez")
    assert {x["specialty"] for x in r["results"]} == {"Cardiology", "Radiology"} and r["message"]


def test_doctor_facts_seven_chens_not_silently_cut(catalog):
    """Spec: 'Always return all matches for duplicate names ... so the AI can ask which one'.
    answer_question also says 'small results only', so either list all 7 or say there are 7."""
    r = answer_question(catalog, "doctor", "Dr. Chen")
    assert len(r["results"]) == 7 or "7" in r["message"], (len(r["results"]), r["message"])


def test_doctor_facts_first_name_grace(catalog):
    r = answer_question(catalog, "doctor", "Dr. Grace")
    assert any("Grace Rodriguez" in x["name"] for x in r.get("results", [])), r


@pytest.mark.parametrize("about", ["Doctor", " DOCTOR ", "provider"])
def test_doctor_about_casing(catalog, about):
    assert answer_question(catalog, about, "Dr. Wei Lee")["found"]


# ---------------------------------------------------------------- visit types
def test_visit_type_facts_knee_mri(catalog):
    r = answer_question(catalog, "visit_type", "knee MRI")
    x = r["results"][0]
    assert x["name"] == "MRI - Knee" and x["minutes"] == 45 and x["needs_referral"] is True
    assert x["open_to_new_patients"] is False and x["needs_equipment"] == "imaging"
    assert x["offered_by_any_doctor"] is True


def test_visit_type_facts_dead_end(catalog):
    r = answer_question(catalog, "visit_type", "Eye Exam")
    x = r["results"][0]
    assert x["name"] == "Eye Exam" and x["offered_by_any_doctor"] is False


def test_visit_type_facts_skin_check(catalog):
    r = answer_question(catalog, "visit_type", "skin check")
    names = [x["name"] for x in r["results"]]
    assert "Skin Cancer Screening" in names or "Full Body Skin Exam" in names


@pytest.mark.parametrize("about,name", [("", "x"), (None, None), ("weather", "today"), ("visit_type", ""),
                                        ("doctor", None)])
def test_bad_questions_do_not_crash(catalog, about, name):
    r = answer_question(catalog, about, name)
    assert r["found"] is False


# ---------------------------------------------------------------- robustness
@pytest.mark.parametrize("vt", ["appt_999", "", None, "MRI - Knee"])
def test_can_book_unknown_visit_type_does_not_crash(catalog, vt):
    """The AI can pass a made-up id. check_booking already answers such ids with a
    plain problem; the 'can this caller book it?' check should say no, not crash."""
    b = can_book_visit_type(catalog, new_caller(), vt)
    assert b.bookable is False


@pytest.mark.parametrize("vt", ["appt_999", ""])
def test_find_options_unknown_visit_type_does_not_crash(catalog, schedule, vt):
    r = find_options(catalog, schedule, new_caller(), vt, Preferences(), NOW)
    assert not r.options and not r.bookable


def test_odd_preferences_do_not_crash(catalog, schedule):
    prefs = Preferences(days=["", "  "], time_of_day="MORNING", language="  ", doctor_name_heard="   ",
                        location_hint="")
    r = find_options(catalog, schedule, new_caller(), "appt_027", prefs, NOW)
    assert r.options


def test_uppercase_time_of_day(catalog, schedule):
    r = find_options(catalog, schedule, new_caller(), "appt_027", Preferences(time_of_day="Afternoon"), NOW)
    assert r.options and all(o.start.hour >= 12 for o in r.options)


def test_specialty_wording(catalog):
    assert catalog.match_specialty("OBGYN") == "OB/GYN"
    assert catalog.match_specialty("ob-gyn") == "OB/GYN"
    assert catalog.match_specialty("dermatology") == "Dermatology"
    assert catalog.match_specialty("Allergy/Immunology") == "Allergy/Immunology"
    assert catalog.match_specialty("banana") is None
