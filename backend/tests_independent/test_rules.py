"""The 6 booking rules: differential tests across the whole catalog, plus named cases."""

from datetime import datetime

import pytest

from clinic import can_book_visit_type, check_booking
from conftest import NOW, new_caller, returning
from reference import LOC, PROV, SPECIALTIES, VT, ref_bookable, ref_combo_ok, ref_pairs

CALLER_KINDS = [("new", True, [])]
CALLER_KINDS += [("returning-none", False, [])]
CALLER_KINDS += [(f"returning-{s}", False, [s]) for s in SPECIALTIES]
CALLER_KINDS += [("returning-all", False, list(SPECIALTIES))]


def make(is_new, refs):
    return new_caller() if is_new else returning(refs)


# ---------------------------------------------------------------- catalog shape
def test_catalog_counts(catalog):
    assert len(catalog.visit_types) == 82
    assert len(catalog.providers) == 50
    assert len(catalog.locations) == 8
    assert len(catalog.specialties()) == 21
    assert catalog.specialties() == SPECIALTIES


def test_visit_types_in_specialty_lists_every_type(catalog):
    for s in SPECIALTIES:
        expected = {k for k, v in VT.items() if v["specialty"] == s}
        assert {vt.id for vt in catalog.visit_types_in(s)} == expected


# ---------------------------------------------------------------- differential
@pytest.mark.parametrize("label,is_new,refs", CALLER_KINDS, ids=[c[0] for c in CALLER_KINDS])
def test_bookability_matches_reference_for_all_82_types(catalog, label, is_new, refs):
    caller = make(is_new, refs)
    mismatches = []
    for vt_id in VT:
        b = can_book_visit_type(catalog, caller, vt_id)
        exp = ref_bookable(is_new, refs, vt_id)
        if b.bookable != exp:
            mismatches.append((vt_id, VT[vt_id]["name"], b.bookable, exp))
            continue
        if exp:
            got = {(p.id, l.id) for p, l in b.valid_pairs}
            if got != ref_pairs(is_new, vt_id):
                mismatches.append((vt_id, "pairs", got ^ ref_pairs(is_new, vt_id)))
        else:
            assert b.reasons, f"{vt_id} refused with no reason"
    assert not mismatches


@pytest.mark.parametrize("label,is_new,refs", CALLER_KINDS[:3] + CALLER_KINDS[-1:])
def test_check_booking_rules_match_reference_every_combo(catalog, schedule, label, is_new, refs):
    """Every visit type x doctor x location. Invalid combos must be refused.
    Valid combos must be accepted at a genuinely open time."""
    caller = make(is_new, refs)
    wrong = []
    any_time = datetime(2026, 10, 8, 10, 0)
    for vt_id in VT:
        for pid in PROV:
            for lid in LOC:
                ok = ref_combo_ok(is_new, refs, vt_id, pid, lid)
                if not ok:
                    probs = check_booking(catalog, schedule, caller, vt_id, pid, lid, any_time, NOW)
                    if not probs:
                        wrong.append(("accepted invalid", vt_id, pid, lid))
                else:
                    slots = schedule.open_slots(pid, lid, VT[vt_id]["duration_min"], NOW)
                    if slots:
                        probs = check_booking(catalog, schedule, caller, vt_id, pid, lid, slots[0], NOW)
                        if probs:
                            wrong.append(("refused valid", vt_id, pid, lid, probs))
    assert not wrong, wrong[:10]


# ---------------------------------------------------------------- named rule cases
def test_rule1_doctor_not_at_location(catalog, schedule):
    # Dr. Grace Rodriguez (prov_010) works only at Richmond (loc_007)
    probs = check_booking(catalog, schedule, returning(["Orthopedics"]), "appt_034", "prov_010", "loc_004",
                          datetime(2026, 10, 8, 10), NOW)
    assert probs


def test_rule2_doctor_does_not_offer_type(catalog, schedule):
    # Dr. Carlos Garcia (Family Medicine) does not do Skin Cancer Screening
    probs = check_booking(catalog, schedule, new_caller(), "appt_027", "prov_008", "loc_002",
                          datetime(2026, 10, 8, 10), NOW)
    assert probs


def test_rule3_equipment(catalog, schedule):
    # Linda Ramirez (Radiology) works at Mission Bay (no imaging) and Downtown (imaging)
    probs = check_booking(catalog, schedule, returning(["Radiology"]), "appt_065", "prov_014", "loc_000",
                          datetime(2026, 10, 8, 10), NOW)
    assert probs


def test_rule4_referral_needed(catalog):
    b = can_book_visit_type(catalog, returning([]), "appt_065")
    assert not b.bookable
    assert any("referral" in r.lower() for r in b.reasons)


def test_rule4_referral_other_specialty_does_not_count(catalog):
    assert not can_book_visit_type(catalog, returning(["Cardiology"]), "appt_065").bookable


def test_rule4_referral_case_insensitive(catalog):
    # decision 28: referral stored as a specialty name
    assert can_book_visit_type(catalog, returning(["radiology"]), "appt_065").bookable


def test_rule5_new_patient_visit_type(catalog):
    b = can_book_visit_type(catalog, new_caller(), "appt_004")  # Follow-up Visit
    assert not b.bookable
    assert any("existing" in r.lower() or "new patient" in r.lower() for r in b.reasons)


def test_rule5_new_patient_doctor_not_accepting(catalog, schedule):
    # Dr. Wei Sato (Dermatology) not accepting new patients
    t = schedule.open_slots("prov_048", "loc_001", 30, NOW)
    probs = check_booking(catalog, schedule, new_caller(), "appt_027", "prov_048", "loc_001",
                          t[0] if t else datetime(2026, 10, 8, 10), NOW)
    assert probs


def test_decision27_returning_can_book_doctor_not_taking_new(catalog):
    b = can_book_visit_type(catalog, returning([]), "appt_027")
    assert "prov_048" in {p.id for p, _ in b.valid_pairs}


def test_rule6_no_location_refused(catalog, schedule):
    t = schedule.open_slots("prov_027", "loc_004", 30, NOW) or [datetime(2026, 10, 8, 10)]
    for loc in (None, ""):
        probs = check_booking(catalog, schedule, new_caller(), "appt_027", "prov_027", loc, t[0], NOW)
        assert probs


def test_check_booking_refuses_missing_parts(catalog, schedule):
    t = datetime(2026, 10, 8, 10)
    c = new_caller()
    assert check_booking(catalog, schedule, c, None, "prov_027", "loc_004", t, NOW)
    assert check_booking(catalog, schedule, c, "appt_027", None, "loc_004", t, NOW)
    assert check_booking(catalog, schedule, c, "appt_027", "prov_027", "loc_004", None, NOW)
    assert check_booking(catalog, schedule, c, "appt_999", "prov_027", "loc_004", t, NOW)
    assert check_booking(catalog, schedule, c, "appt_027", "prov_999", "loc_004", t, NOW)
    assert check_booking(catalog, schedule, c, "appt_027", "prov_027", "loc_999", t, NOW)


def test_check_booking_refuses_closed_time(catalog, schedule):
    c = new_caller()
    for t in [datetime(2026, 10, 10, 10),   # Saturday
              datetime(2026, 10, 7, 12, 0),  # lunch
              datetime(2026, 10, 7, 17, 0),  # closing
              datetime(2026, 10, 6, 9, 30),  # less than 2 hours' notice
              datetime(2026, 10, 5, 10, 0),  # the past
              datetime(2026, 11, 20, 10, 0)]:  # beyond 2 weeks
        assert check_booking(catalog, schedule, c, "appt_027", "prov_027", "loc_004", t, NOW), t


# ---------------------------------------------------------------- dead ends (findings doc)
NO_DOCTOR = ["appt_045", "appt_046", "appt_047", "appt_048", "appt_049", "appt_070", "appt_071", "appt_077"]
NEW_DEAD = ["appt_040", "appt_041", "appt_042", "appt_043", "appt_044", "appt_056"]


@pytest.mark.parametrize("vt_id", NO_DOCTOR)
def test_dead_end_no_doctor_for_anyone(catalog, vt_id):
    for c in (new_caller(), returning(list(SPECIALTIES))):
        b = can_book_visit_type(catalog, c, vt_id)
        assert not b.bookable
        assert any("no doctor" in r.lower() for r in b.reasons), b.reasons


@pytest.mark.parametrize("vt_id", NEW_DEAD)
def test_dead_end_for_new_patients(catalog, vt_id):
    b = can_book_visit_type(catalog, new_caller(), vt_id)
    assert not b.bookable
    assert any("new patient" in r.lower() for r in b.reasons), b.reasons


def test_obgyn_bookable_for_returning_emily_brown(catalog, directory):
    emily = directory.lookup("Emily Brown", "1988-01-19").caller
    for vt in ["appt_040", "appt_041", "appt_042", "appt_043", "appt_044"]:
        b = can_book_visit_type(catalog, emily, vt)
        assert b.bookable
        assert {(p.id, l.id) for p, l in b.valid_pairs} == {("prov_036", "loc_004")}


def test_exactly_8_and_6_dead_ends(catalog):
    every = returning(list(SPECIALTIES))
    none_at_all = [v for v in VT if not can_book_visit_type(catalog, every, v).bookable]
    assert sorted(none_at_all) == sorted(NO_DOCTOR)
    new_blocked_on_paper_ok = [v for v in VT if VT[v]["new_patients_allowed"] and v not in NO_DOCTOR
                               and not ref_pairs(True, v)]
    assert sorted(new_blocked_on_paper_ok) == sorted(NEW_DEAD)


# ---------------------------------------------------------------- baseline call cases
def test_knee_mri_new_patient_refused_with_reasons(catalog):
    b = can_book_visit_type(catalog, new_caller(), "appt_065")
    assert not b.bookable and b.valid_pairs == []
    text = " ".join(b.reasons).lower()
    assert "referral" in text
    assert "existing" in text or "new patient" in text


def test_knee_mri_returning_no_referral_refused(catalog, directory):
    emily = directory.lookup("Emily Brown", "1988-01-19").caller
    b = can_book_visit_type(catalog, emily, "appt_065")
    assert not b.bookable


def test_knee_mri_james_wilson_two_options(catalog, directory):
    james = directory.lookup("James Wilson", "1984-03-12").caller
    b = can_book_visit_type(catalog, james, "appt_065")
    assert b.bookable
    assert {(p.id, l.id) for p, l in b.valid_pairs} == {("prov_014", "loc_004"), ("prov_015", "loc_005")}


def test_new_patient_can_book_mammogram(catalog):
    # imaging, no referral, new patients allowed, radiologists accept new patients
    b = can_book_visit_type(catalog, new_caller(), "appt_068")
    assert b.bookable
    assert {l.id for _, l in b.valid_pairs} == {"loc_004", "loc_005"}
