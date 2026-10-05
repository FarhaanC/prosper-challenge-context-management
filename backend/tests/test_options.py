"""Finding options: only valid ones, honest notes for wishes we can't meet."""

from clinic import Caller, Preferences, Schedule, check_booking, find_options
from conftest import (
    ANNUAL_PHYSICAL, DOWNTOWN, KNEE_MRI, MIDTOWN, MISSION_BAY, MISSION_DISTRICT, NOW,
    SKIN_CANCER_SCREENING,
)


def _all_valid(catalog, schedule, caller, vt, result):
    for o in result.options:
        assert check_booking(catalog, schedule, caller, vt, o.provider_id, o.location_id, o.start, NOW) == [], o


def test_garcia_skin_check(catalog, schedule, new_caller):
    """The baseline call's first mistake: no Dr. Garcia does skin checks."""
    r = find_options(catalog, schedule, new_caller, SKIN_CANCER_SCREENING,
                     Preferences(visit_description="skin check", doctor_name_heard="Dr. Garsha"), NOW)
    assert r.options, "should still offer dermatologists"
    assert all("Garcia" not in o.provider_name for o in r.options)
    assert all(catalog.providers[o.provider_id].specialty == "Dermatology" for o in r.options)
    assert len(r.notes) == 1 and "Garcia" in r.notes[0] and "don't offer Skin Cancer Screening" in r.notes[0]
    _all_valid(catalog, schedule, new_caller, SKIN_CANCER_SCREENING, r)


def test_two_maria_garcias_are_both_offered(catalog, schedule, new_caller):
    r = find_options(catalog, schedule, new_caller, ANNUAL_PHYSICAL,
                     Preferences(doctor_name_heard="Maria Garcia"), NOW)
    assert {o.provider_id for o in r.options} == {"prov_002", "prov_003"}
    assert any("There are 2 doctors" in n for n in r.notes)


def test_knee_mri_near_downtown(catalog, schedule, james):
    r = find_options(catalog, schedule, james, KNEE_MRI, Preferences(location_hint="near Downtown"), NOW)
    assert r.options[0].location_id == DOWNTOWN            # closest first
    assert {o.location_id for o in r.options} == {DOWNTOWN, MIDTOWN}  # the only two valid places
    _all_valid(catalog, schedule, james, KNEE_MRI, r)


def test_knee_mri_refused_for_new_patient_with_reason(catalog, schedule, new_caller):
    r = find_options(catalog, schedule, new_caller, KNEE_MRI, Preferences(), NOW)
    assert not r.bookable and not r.options
    assert any("referral" in n for n in r.notes)


def test_day_and_time_wishes(catalog, schedule, new_caller):
    r = find_options(catalog, schedule, new_caller, SKIN_CANCER_SCREENING,
                     Preferences(days=["Thursday"], time_of_day="morning"), NOW)
    assert r.options and not r.notes
    assert all(o.start.strftime("%A") == "Thursday" and o.start.hour < 12 for o in r.options)

    # Clinics are closed at weekends: say so, then offer the nearest other times.
    r = find_options(catalog, schedule, new_caller, SKIN_CANCER_SCREENING, Preferences(days=["Saturday"]), NOW)
    assert r.options and any("Nothing is open" in n for n in r.notes)


def test_language_wish(catalog, schedule, new_caller):
    r = find_options(catalog, schedule, new_caller, SKIN_CANCER_SCREENING, Preferences(language="Spanish"), NOW)
    assert r.options
    assert all("Spanish" in catalog.providers[o.provider_id].languages for o in r.options)


def test_ambiguous_place_asks(catalog, schedule, new_caller):
    r = find_options(catalog, schedule, new_caller, SKIN_CANCER_SCREENING, Preferences(location_hint="Mission"), NOW)
    assert any("could mean" in n for n in r.notes)
    assert {o.location_id for o in r.options} <= {MISSION_BAY, MISSION_DISTRICT}


def test_same_answer_every_run(catalog, new_caller):
    prefs = Preferences(location_hint="near Union Square")
    a = find_options(catalog, Schedule(catalog), new_caller, SKIN_CANCER_SCREENING, prefs, NOW)
    b = find_options(catalog, Schedule(catalog), new_caller, SKIN_CANCER_SCREENING, prefs, NOW)
    assert [o.to_dict() for o in a.options] == [o.to_dict() for o in b.options]


def test_every_option_ever_offered_passes_every_rule(catalog, schedule, james):
    """The core guarantee, checked across the whole catalog: for every visit type,
    for a new and a returning caller, nothing we offer breaks a rule."""
    callers = [Caller("New Person"), james, Caller("All Referrals", "pat_x", False, catalog.specialties())]
    offered = 0
    for caller in callers:
        for vt in catalog.visit_types:
            r = find_options(catalog, schedule, caller, vt, Preferences(), NOW)
            assert len(r.options) <= 3
            assert len({(o.provider_id, o.start) for o in r.options}) == len(r.options)
            _all_valid(catalog, schedule, caller, vt, r)
            offered += len(r.options)
    assert offered > 100  # sanity: we actually offered plenty
