"""The rules: 'can this caller book this?', the final check, and alternatives."""

from datetime import datetime

import pytest

from catalog_ids import (
    DOWNTOWN, HANNAH_NGUYEN, KNEE_MRI, LINDA_RAMIREZ_RADIOLOGY, MIDTOWN, MISSION_BAY, NO_DOCTOR_TYPES, NOW,
    OBGYN_TYPES, SKIN_CANCER_SCREENING, WEI_SATO_DERM,
)
from clinic import Caller, SlotTaken, alternatives_for, can_book_visit_type, check_booking


def test_knee_mri_refused_for_new_patient(catalog, new_caller):
    b = can_book_visit_type(catalog, new_caller, KNEE_MRI)
    assert not b.bookable
    assert any("existing patients" in r for r in b.reasons)
    assert any("referral to Radiology" in r for r in b.reasons)


def test_knee_mri_refused_without_referral(catalog, emily):
    b = can_book_visit_type(catalog, emily, KNEE_MRI)
    assert b.reasons == ["MRI - Knee needs a referral to Radiology, and there isn't one on file."]


def test_knee_mri_has_exactly_two_valid_pairs(catalog, james):
    b = can_book_visit_type(catalog, james, KNEE_MRI)
    # Both radiologists also work at Mission Bay, which has no imaging: excluded.
    assert {(p.id, loc.id) for p, loc in b.valid_pairs} == {(LINDA_RAMIREZ_RADIOLOGY, DOWNTOWN), (HANNAH_NGUYEN, MIDTOWN)}


def test_obgyn_closed_to_new_patients_open_to_returning(catalog, new_caller, emily):
    for vt in OBGYN_TYPES:
        b = can_book_visit_type(catalog, new_caller, vt)
        assert not b.bookable and "taking new patients" in b.reasons[0], vt
        assert can_book_visit_type(catalog, emily, vt).bookable, vt


def test_dead_end_visit_types(catalog, james):
    for vt in NO_DOCTOR_TYPES:
        assert can_book_visit_type(catalog, james, vt).reasons[0].startswith("No doctor here currently offers")


@pytest.mark.parametrize("bad", ["appt_999", "", None, "MRI - Knee"])
def test_unknown_visit_type_is_refused_not_crashed(catalog, new_caller, bad):  # 7
    b = can_book_visit_type(catalog, new_caller, bad)
    assert not b.bookable and "isn't a visit type" in b.reasons[0]


def test_alternative_when_refused_is_a_primary_care_visit(catalog, new_caller, emily):  # 13
    new_alt = alternatives_for(catalog, new_caller, KNEE_MRI)
    assert [vt.name for vt in new_alt] == ["New Patient Consultation"]
    returning_alt = alternatives_for(catalog, emily, KNEE_MRI)
    assert [vt.name for vt in returning_alt] == ["Follow-up Visit"]


def _slot(schedule, provider_id, location_id, duration):
    return schedule.open_slots(provider_id, location_id, duration, NOW)[0]


def test_final_check_catches_each_rule(catalog, schedule, james, new_caller):
    good = _slot(schedule, LINDA_RAMIREZ_RADIOLOGY, DOWNTOWN, 45)
    assert check_booking(catalog, schedule, james, KNEE_MRI, LINDA_RAMIREZ_RADIOLOGY, DOWNTOWN, good, NOW) == []

    def problems(caller, vt, pid, lid):
        return " ".join(check_booking(catalog, schedule, caller, vt, pid, lid, good, NOW))

    assert "imaging" in problems(james, KNEE_MRI, LINDA_RAMIREZ_RADIOLOGY, MISSION_BAY)            # rule 3
    assert "doesn't work at" in problems(james, KNEE_MRI, LINDA_RAMIREZ_RADIOLOGY, MIDTOWN)        # rule 1
    assert "doesn't offer" in problems(james, KNEE_MRI, "prov_002", MISSION_BAY)                    # rule 2
    p = problems(new_caller, KNEE_MRI, LINDA_RAMIREZ_RADIOLOGY, DOWNTOWN)
    assert "referral" in p and "existing patients" in p                                              # rules 4, 5
    assert "isn't taking new patients" in problems(new_caller, SKIN_CANCER_SCREENING, WEI_SATO_DERM, "loc_001")  # rule 5
    assert check_booking(catalog, schedule, james, KNEE_MRI, LINDA_RAMIREZ_RADIOLOGY, None, good, NOW) == [
        "No location has been chosen."]                                                              # rule 6


def test_final_check_refuses_closed_and_double_booked_times(catalog, schedule, james):
    saturday = datetime(2026, 10, 10, 10, 0)
    assert check_booking(catalog, schedule, james, KNEE_MRI, LINDA_RAMIREZ_RADIOLOGY, DOWNTOWN, saturday, NOW) == [
        "That time is no longer available."]
    start = _slot(schedule, LINDA_RAMIREZ_RADIOLOGY, DOWNTOWN, 45)
    schedule.book(LINDA_RAMIREZ_RADIOLOGY, start, 45)
    assert check_booking(catalog, schedule, james, KNEE_MRI, LINDA_RAMIREZ_RADIOLOGY, DOWNTOWN, start, NOW) == [
        "That time is no longer available."]
    with pytest.raises(SlotTaken):  # 13: booking the same time twice is refused at the source too
        schedule.book(LINDA_RAMIREZ_RADIOLOGY, start, 45)


def test_returning_patient_may_see_a_doctor_closed_to_new_patients(catalog):  # decision 27
    returning = Caller("X", "pat_x", False, [])
    pairs = can_book_visit_type(catalog, returning, SKIN_CANCER_SCREENING).valid_pairs
    assert WEI_SATO_DERM in {p.id for p, _ in pairs}
