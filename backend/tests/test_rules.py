"""The rules: 'can this caller book this?' and the final full check."""

from datetime import datetime

from clinic import can_book_visit_type, check_booking
from conftest import (
    DOWNTOWN, HANNAH_NGUYEN, KNEE_MRI, LINDA_RAMIREZ_RADIOLOGY, MIDTOWN, MISSION_BAY,
    NO_DOCTOR_TYPES, NOW, OBGYN_TYPES, SKIN_CANCER_SCREENING,
)


def test_knee_mri_refused_for_new_patient(catalog, new_caller):
    b = can_book_visit_type(catalog, new_caller, KNEE_MRI)
    assert not b.bookable
    assert any("existing patients" in r for r in b.reasons)
    assert any("referral to Radiology" in r for r in b.reasons)


def test_knee_mri_refused_without_referral(catalog, emily):
    b = can_book_visit_type(catalog, emily, KNEE_MRI)
    assert not b.bookable
    assert b.reasons == ["It needs a referral to Radiology, and there isn't one on file."]


def test_knee_mri_has_exactly_two_valid_options(catalog, james):
    b = can_book_visit_type(catalog, james, KNEE_MRI)
    assert b.bookable
    pairs = {(p.id, loc.id) for p, loc in b.valid_pairs}
    # Both radiologists also work at Mission Bay, which has no imaging: excluded.
    assert pairs == {(LINDA_RAMIREZ_RADIOLOGY, DOWNTOWN), (HANNAH_NGUYEN, MIDTOWN)}


def test_obgyn_not_bookable_for_new_patients(catalog, new_caller, emily):
    for vt in OBGYN_TYPES:
        b = can_book_visit_type(catalog, new_caller, vt)
        assert not b.bookable, vt
        assert b.reasons == ["No doctor who offers this is taking new patients right now."]
        # ...but a returning patient can book them.
        assert can_book_visit_type(catalog, emily, vt).bookable, vt


def test_dead_end_visit_types(catalog, james):
    for vt in NO_DOCTOR_TYPES:
        b = can_book_visit_type(catalog, james, vt)
        assert not b.bookable
        assert b.reasons[0] == "No doctor here currently offers this."


def test_every_visit_type_bookable_iff_a_doctor_offers_it(catalog):
    """With every referral and as a returning patient, the only blocker left is 'nobody offers it'."""
    from clinic import Caller
    everything = Caller("Test", "pat_x", False, catalog.specialties())
    for vt_id in catalog.visit_types:
        assert can_book_visit_type(catalog, everything, vt_id).bookable == bool(catalog.providers_offering(vt_id)), vt_id


def _slot(schedule, provider_id, location_id, duration):
    return schedule.open_slots(provider_id, location_id, duration, NOW)[0]


def test_final_check_catches_each_rule(catalog, schedule, james, new_caller):
    good_start = _slot(schedule, LINDA_RAMIREZ_RADIOLOGY, DOWNTOWN, 45)
    assert check_booking(catalog, schedule, james, KNEE_MRI, LINDA_RAMIREZ_RADIOLOGY, DOWNTOWN, good_start, NOW) == []

    # Rule 3: right doctor, location she works at, but no imaging there.
    p = check_booking(catalog, schedule, james, KNEE_MRI, LINDA_RAMIREZ_RADIOLOGY, MISSION_BAY, good_start, NOW)
    assert any("imaging" in x for x in p)
    # Rule 1: a location she doesn't work at.
    p = check_booking(catalog, schedule, james, KNEE_MRI, LINDA_RAMIREZ_RADIOLOGY, MIDTOWN, good_start, NOW)
    assert any("doesn't work at" in x for x in p)
    # Rule 2: a doctor who doesn't offer it (Dr. Maria Garcia, Pediatrics).
    p = check_booking(catalog, schedule, james, KNEE_MRI, "prov_002", MISSION_BAY, good_start, NOW)
    assert any("doesn't offer" in x for x in p)
    # Rules 4 and 5: a new patient.
    p = check_booking(catalog, schedule, new_caller, KNEE_MRI, LINDA_RAMIREZ_RADIOLOGY, DOWNTOWN, good_start, NOW)
    assert any("referral" in x for x in p) and any("existing patients" in x for x in p)
    # Rule 5 (doctor half): Dr. Wei Sato offers skin checks but isn't taking new patients.
    p = check_booking(catalog, schedule, new_caller, SKIN_CANCER_SCREENING, "prov_048", "loc_001", good_start, NOW)
    assert any("isn't taking new patients" in x for x in p)
    # Rule 6: no location settled.
    assert check_booking(catalog, schedule, james, KNEE_MRI, LINDA_RAMIREZ_RADIOLOGY, None, good_start, NOW) == [
        "No location has been chosen."
    ]


def test_final_check_refuses_closed_or_double_booked_times(catalog, schedule, james):
    closed = datetime(2026, 10, 10, 10, 0)  # a Saturday
    p = check_booking(catalog, schedule, james, KNEE_MRI, LINDA_RAMIREZ_RADIOLOGY, DOWNTOWN, closed, NOW)
    assert p == ["That time is no longer available."]

    start = _slot(schedule, LINDA_RAMIREZ_RADIOLOGY, DOWNTOWN, 45)
    schedule.book(LINDA_RAMIREZ_RADIOLOGY, start, 45)
    p = check_booking(catalog, schedule, james, KNEE_MRI, LINDA_RAMIREZ_RADIOLOGY, DOWNTOWN, start, NOW)
    assert p == ["That time is no longer available."]
