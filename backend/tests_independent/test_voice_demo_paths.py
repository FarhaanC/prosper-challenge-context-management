"""Voice stages, area 1: the demo paths end to end through run_tool.

Plan "Demo script": "Skin check with Dr. Garcia" -> no Garcia does it, dermatologists
offered; "Actually, a knee MRI" -> refused without a referral; a returning patient with
a referral gets only the 2 valid options; book it, and the read-back matches what is saved.
Expected answers come from catalog.json, patients.json and location_extras.json.
"""

import json
from datetime import timedelta

import pytest

from call import Clinic
from voice_reference import (BOOKING, END, GARCIAS, JAMES, KNEE_MRI, LOC, NEW, NOW, PRIMARY_CARE, PROV,
                             SKIN_CHECK, VISIT_TYPE, VT, landmark, loc_point, make_clinic, miles, offered,
                             overlaps, ref_bookable, ref_pairs, result_text, section, snapshot, spoken, step,
                             to_booking, to_visit_type)
from round6_reference import who_can_problems

KNEE_PAIRS = ref_pairs(False, KNEE_MRI)
WINDOW_END = NOW.date() + timedelta(days=14)


@pytest.fixture
def clinic(catalog, directory, tmp_path):
    return make_clinic(catalog, directory, bookings_file=tmp_path / "bookings.jsonl", log_dir=tmp_path / "logs")


def test_reference_knee_mri_has_exactly_two_valid_pairs():
    # Sanity check of my own reference (the plan: "it offers the 2 valid options").
    assert KNEE_PAIRS == {("prov_014", "loc_004"), ("prov_015", "loc_005")}
    assert all("imaging" in LOC[l]["capabilities"] for _, l in KNEE_PAIRS)


# ====================================================== skin check with "Dr. Garsha"
def test_garsha_skin_check_new_patient_offers_no_garcia_and_says_so_truthfully(clinic):
    s = to_booking(clinic, SKIN_CHECK, NEW, visit_description="skin check", doctor_name="Dr. Garsha")
    opts = offered(s)
    assert 1 <= len(opts) <= 3
    for _, pid, lid, start in opts:
        assert pid not in GARCIAS, f"a Garcia was offered: {PROV[pid]['name']}"
        assert (pid, lid) in ref_pairs(True, SKIN_CHECK)
        assert PROV[pid]["specialty"] == "Dermatology"
        assert NOW < start and start.date() <= WINDOW_END
    text = s.fill("{options}")
    told = " ".join(section(text, "Tell the caller first"))
    assert "Garcia" in told and "Skin Cancer Screening" in told, text
    # The note says why the Garcias can't, and who can: every new-patient dermatologist who offers it.
    who = told.split("Doctors who can:", 1)[1].strip().rstrip(".")
    able = sorted({p for p, _ in ref_pairs(True, SKIN_CHECK)})
    assert able == ["prov_001", "prov_027", "prov_035"]
    assert who_can_problems(who, able) == [], who
    assert "Wei Sato" not in told, "Dr. Wei Sato isn't taking new patients and must not be named as able"


def test_garsha_skin_check_returning_patient_lists_all_four_dermatologists(clinic):
    s = to_booking(clinic, SKIN_CHECK, JAMES, doctor_name="Dr. Garsha")
    told = " ".join(section(s.fill("{options}"), "Tell the caller first"))
    who = told.split("Doctors who can:", 1)[1].strip().rstrip(".")
    able = sorted({p for p, _ in ref_pairs(False, SKIN_CHECK)})
    assert len(able) == 4
    assert who_can_problems(who, able) == [], who
    assert all(pid not in GARCIAS for _, pid, _, _ in offered(s))


def test_list_visit_types_dermatology_matches_the_catalog_for_a_new_patient(clinic):
    s = to_visit_type(clinic, NEW)
    out = step(s, "list_visit_types", {"specialty": "Dermatology"})
    assert out.next_stage is None and s.stage == VISIT_TYPE
    rows = {r["id"]: r for r in out.result["visit_types"]}
    assert set(rows) == {i for i, v in VT.items() if v["specialty"] == "Dermatology"}
    for vid, r in rows.items():
        v = VT[vid]
        assert r["name"] == v["name"] and r["minutes"] == v["duration_min"]
        assert r["needs_referral"] == v["requires_referral"]
        assert r["open_to_new_patients"] == v["new_patients_allowed"]
        assert r["can_book"] == ref_bookable(True, [], vid), vid
        assert bool(r["why_not"]) == (not r["can_book"]), r


# ====================================================== knee MRI, new patient
def test_knee_mri_refused_for_new_patient_with_primary_care_alternative(clinic):
    s = to_visit_type(clinic, NEW, visit_description="knee MRI")
    rows = {r["id"]: r for r in step(s, "list_visit_types", {"specialty": "Radiology"}).result["visit_types"]}
    assert rows[KNEE_MRI]["can_book"] is False
    why = " ".join(rows[KNEE_MRI]["why_not"]).lower()
    assert "referral" in why and "existing patients" in why

    before = snapshot(s)
    out = step(s, "choose_visit_type", {"visit_type_id": KNEE_MRI})
    assert out.result["ok"] is False
    assert out.next_stage is None and s.stage == VISIT_TYPE, "a refused choose stays in stage 2"
    assert snapshot(s) == before, "a refused choose must change nothing"
    assert s.card.choices.visit_type_id == "" and not s.card.offered_options
    reasons = " ".join(out.result["reasons"]).lower()
    assert "referral" in reasons
    alts = out.result["alternatives"]
    assert alts, "the plan: offer an alternative, e.g. a new-patient visit with a family doctor"
    for a in alts:
        v = VT[a["id"]]
        assert v["specialty"] in PRIMARY_CARE, a
        assert ref_bookable(True, [], a["id"]), f"alternative {a} isn't bookable for a new patient"
        assert not v["requires_referral"] and v["new_patients_allowed"]


def test_knee_mri_refusal_tells_the_ai_not_to_promise_a_referral(clinic):
    s = to_visit_type(clinic, NEW)
    out = step(s, "choose_visit_type", {"visit_type_id": KNEE_MRI})
    text = result_text(out.result).lower()
    assert "promise" in text and "referral" in text, out.result
    for bad in ("will get a referral", "will refer", "can refer you", "get you a referral", "will give you a referral"):
        assert bad not in text


def test_knee_mri_refused_for_returning_patient_without_radiology_referral(clinic):
    emily = {"full_name": "Emily Brown", "returning": True, "date_of_birth": "1988-01-19"}
    s = to_visit_type(clinic, emily)
    out = step(s, "choose_visit_type", {"visit_type_id": KNEE_MRI})
    assert out.result["ok"] is False and s.stage == VISIT_TYPE
    assert "referral" in " ".join(out.result["reasons"]).lower()
    assert "existing patients" not in " ".join(out.result["reasons"]).lower(), "Emily is returning"
    for a in out.result["alternatives"]:
        assert ref_bookable(False, [], a["id"])


# ====================================================== knee MRI, James Wilson
def test_james_wilson_radiology_all_bookable(clinic):
    s = to_visit_type(clinic, JAMES)
    rows = step(s, "list_visit_types", {"specialty": "Radiology"}).result["visit_types"]
    for r in rows:
        assert r["can_book"] == ref_bookable(False, ["Radiology", "Orthopedics"], r["id"]), r


def test_james_wilson_knee_mri_near_downtown_only_valid_imaging_options_nearest_first(clinic):
    s = to_booking(clinic, KNEE_MRI, JAMES, visit_description="knee MRI", place="Downtown", near=True)
    opts = offered(s)
    assert len(opts) == 3
    assert {(p, l) for _, p, l, _ in opts} == KNEE_PAIRS, "both valid pairs offered, nothing else"
    point = landmark("Downtown")
    # Different doctor/place pairs come before extra times with the same pair (rules module),
    # so check the order in which places first appear.
    first_seen = list(dict.fromkeys(l for _, _, l, _ in opts))
    dists = [miles(point, loc_point(l)) for l in first_seen]
    assert dists == sorted(dists), f"near Downtown must rank by distance: {opts}"
    assert opts[0][2] == "loc_004"
    for _, pid, lid, start in opts:
        assert "imaging" in LOC[lid]["capabilities"]
        assert NOW < start and start.date() <= WINDOW_END
    told = section(s.fill("{options}"), "Tell the caller first")
    assert not any("referral" in t.lower() for t in told), told


def test_demo_script_skin_check_then_knee_mri_for_returning_patient(clinic):
    s = to_booking(clinic, SKIN_CHECK, JAMES, visit_description="skin check", doctor_name="Dr. Garsha")
    first_numbers = [int(o[0]) for o in offered(s)]
    out = step(s, "change_choice", {"what": "visit_type", "new_value": "knee MRI"})
    assert out.result["ok"] is True and out.next_stage == VISIT_TYPE
    c = s.card.choices
    assert (c.visit_type_id, c.provider_id, c.location_id, c.slot) == ("", "", "", None)
    assert not s.card.offered_options
    assert s.card.preferences.visit_description == "knee MRI"

    out = step(s, "choose_visit_type", {"visit_type_id": KNEE_MRI})
    assert out.result["ok"] is True and s.stage == BOOKING
    opts = offered(s)
    assert {(p, l) for _, p, l, _ in opts} == KNEE_PAIRS
    assert min(int(o[0]) for o in opts) > max(first_numbers), "option numbers are never reused"
    # Decision 26: the old doctor wish is kept, and the note about it is true for the NEW visit.
    told = " ".join(section(s.fill("{options}"), "Tell the caller first"))
    assert "MRI - Knee" in told and "Garcia" in told
    who = told.split("Doctors who can:", 1)[1].strip().rstrip(".")
    assert who_can_problems(who, sorted({p for p, _ in KNEE_PAIRS})) == [], who


# ====================================================== book it; read-back == saved
def _book_first_option(s):
    o = s.card.offered_options[0]
    chosen = step(s, "choose_option", {"option_id": o.option_id})
    assert chosen.result["ok"] is True and chosen.next_stage is None
    done = step(s, "confirm_booking", {})
    return o, chosen.result["read_back"], done


def test_booking_read_back_matches_card_saved_line_and_outcome(clinic):
    s = to_booking(clinic, KNEE_MRI, JAMES, place="Downtown", near=True)
    o, read_back, done = _book_first_option(s)
    vt, p, loc = VT[KNEE_MRI], PROV[o.provider_id], LOC[o.location_id]
    for fact in (vt["name"], p["name"], loc["name"], loc["address"], spoken(o.start), f"{vt['duration_min']} minutes"):
        assert fact in read_back, (fact, read_back)

    assert done.result["ok"] is True and done.next_stage == END and s.stage == END
    assert done.result["booked"] == read_back
    assert s.card.status == "booked"

    lines = clinic.bookings_file.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    saved = json.loads(lines[0])
    assert saved["visit_type_id"] == KNEE_MRI
    assert saved["provider_id"] == o.provider_id and saved["location_id"] == o.location_id
    assert saved["start"] == o.start.isoformat()
    assert saved["duration_min"] == vt["duration_min"]
    assert saved["patient_id"] == "pat_001"
    assert saved["read_back"] == read_back
    assert read_back in s.fill("{outcome}")


def test_same_clinic_never_offers_a_booked_time_again(clinic):
    s = to_booking(clinic, KNEE_MRI, JAMES, place="Downtown", near=True)
    o, _, _ = _book_first_option(s)
    s2 = to_booking(clinic, KNEE_MRI, JAMES, place="Downtown", near=True)
    for _, pid, _, start in offered(s2):
        assert not (pid == o.provider_id and overlaps(start, 45, o.start, 45)), (pid, start)


def test_reloaded_clinic_never_offers_a_booked_time_again(clinic, catalog, directory):
    s = to_booking(clinic, KNEE_MRI, JAMES, place="Downtown", near=True)
    o, _, _ = _book_first_option(s)
    fresh = make_clinic(catalog, directory)  # no bookings: the time is open there (so this test can fail)
    assert fresh.schedule.is_open(o.provider_id, o.location_id, 45, o.start, NOW)

    reloaded = Clinic.load(bookings_file=clinic.bookings_file, log_dir=None)
    assert not reloaded.schedule.is_open(o.provider_id, o.location_id, 45, o.start, NOW)
    # Ask for exactly that doctor, that day and that part of the day.
    s2 = to_booking(reloaded, KNEE_MRI, JAMES, doctor_name=PROV[o.provider_id]["name"],
                    days=[o.start.date().isoformat()], time_of_day="morning" if o.start.hour < 12 else "afternoon")
    for _, pid, _, start in offered(s2):
        assert not (pid == o.provider_id and overlaps(start, 45, o.start, 45)), (pid, start)


def test_reloaded_booking_blocks_overlapping_shorter_visit_with_same_doctor(clinic, catalog, directory):
    s = to_booking(clinic, KNEE_MRI, JAMES, place="Downtown", near=True)
    o, _, _ = _book_first_option(s)
    half_hour_later = o.start + timedelta(minutes=30)  # inside the 45-minute MRI
    fresh = make_clinic(catalog, directory)
    if not fresh.schedule.is_open(o.provider_id, o.location_id, 20, half_hour_later, NOW):
        pytest.skip("that half hour was already taken in the fake calendar")
    reloaded = Clinic.load(bookings_file=clinic.bookings_file, log_dir=None)
    assert not reloaded.schedule.is_open(o.provider_id, o.location_id, 20, half_hour_later, NOW)
