"""Finding options: only valid ones, the newest wish wins, and every note is true."""

from datetime import datetime

from catalog_ids import (
    ANNUAL_PHYSICAL, DANIEL_CHEN_DERM, DANIEL_SMITH_DERM, DOWNTOWN, ECHOCARDIOGRAM, KENJI_KIM_DERM, KNEE_MRI,
    MIDTOWN, MISSION_BAY, MISSION_DISTRICT, NOW, RICHMOND, SKIN_CANCER_SCREENING,
)
from clinic import BookingCard, Caller, Choices, Preferences, Schedule, check_booking, find_options
from clinic.options import (
    BAD_INPUT, DOCTOR_NAME_GUESS, PLACE_AMBIGUOUS, SAME_NAME, WISH_CONFLICT, WISH_IMPOSSIBLE,
)


def _all_valid(catalog, schedule, caller, vt, result):
    for o in result.options:
        assert check_booking(catalog, schedule, caller, vt, o.provider_id, o.location_id, o.start, NOW) == [], o


def _kinds(result):
    return [n.kind for n in result.notes]


def test_garcia_skin_check(catalog, schedule, new_caller):
    """The baseline call's first mistake: no Dr. Garcia does skin checks."""
    r = find_options(catalog, schedule, new_caller, SKIN_CANCER_SCREENING,
                     Preferences(doctor_name_heard="Dr. Garcia"), NOW)
    assert r.options and all(catalog.providers[o.provider_id].specialty == "Dermatology" for o in r.options)
    assert _kinds(r) == [WISH_IMPOSSIBLE]
    assert "don't offer Skin Cancer Screening" in r.notes[0] and "Doctors who can:" in r.notes[0]
    _all_valid(catalog, schedule, new_caller, SKIN_CANCER_SCREENING, r)


def test_misheard_name_is_flagged_as_a_guess(catalog, schedule, new_caller):  # 4
    r = find_options(catalog, schedule, new_caller, SKIN_CANCER_SCREENING,
                     Preferences(doctor_name_heard="Dr. Garsha"), NOW)
    assert DOCTOR_NAME_GUESS in _kinds(r)


def test_two_maria_garcias_are_both_offered(catalog, schedule, new_caller):
    r = find_options(catalog, schedule, new_caller, ANNUAL_PHYSICAL, Preferences(doctor_name_heard="Maria Garcia"), NOW)
    assert {o.provider_id for o in r.options} == {"prov_002", "prov_003"}
    assert SAME_NAME in _kinds(r)


def test_knee_mri_near_downtown(catalog, schedule, james):
    r = find_options(catalog, schedule, james, KNEE_MRI, Preferences(location_hint="closer to downtown"), NOW)
    assert r.options[0].location_id == DOWNTOWN                     # closest first
    assert {o.location_id for o in r.options} == {DOWNTOWN, MIDTOWN}  # near ranks, doesn't exclude
    assert not r.notes
    _all_valid(catalog, schedule, james, KNEE_MRI, r)


def test_soonest_beats_distance(catalog, schedule, new_caller):  # 13
    prefs = Preferences(location_hint="near Downtown", soonest=True)
    r = find_options(catalog, schedule, new_caller, SKIN_CANCER_SCREENING, prefs, NOW)
    starts = [o.start for o in r.options]
    assert starts == sorted(starts)


# ---- 1: the newest wish wins, and notes are true
def _card_with(caller, provider, location, vt=SKIN_CANCER_SCREENING):
    card = BookingCard(caller=caller)
    card.choices = Choices(specialty="Dermatology", visit_type_id=vt, provider_id=provider,
                           location_id=location, slot=datetime(2026, 10, 8, 10, 0))
    return card


def test_location_change_beats_the_old_doctor(catalog, schedule, new_caller):
    card = _card_with(new_caller, DANIEL_CHEN_DERM, RICHMOND)
    card.change_choice("location", "the Midtown one")
    r = find_options(catalog, schedule, new_caller, SKIN_CANCER_SCREENING, card.preferences, NOW)
    assert r.options and all((o.provider_id, o.location_id) == (KENJI_KIM_DERM, MIDTOWN) for o in r.options)
    assert _kinds(r) == [WISH_CONFLICT]
    assert r.notes[0] == "Dr. Daniel Chen isn't available at Midtown Medical Group."


def test_time_change_never_claims_nothing_is_open_when_something_is(catalog, schedule, new_caller):
    card = _card_with(new_caller, DANIEL_CHEN_DERM, RICHMOND)
    card.change_choice("time", days=["Wednesday"])
    r = find_options(catalog, schedule, new_caller, SKIN_CANCER_SCREENING, card.preferences, NOW)
    assert r.options and all(o.start.strftime("%A") == "Wednesday" for o in r.options)
    assert WISH_IMPOSSIBLE not in _kinds(r)


def test_nothing_open_note_only_when_true_across_the_catalog(catalog, schedule):
    caller = Caller("X", "pat_x", False, catalog.specialties())
    for day in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]:
        r = find_options(catalog, schedule, caller, ECHOCARDIOGRAM,
                         Preferences(preferred_provider_id="prov_000", days=[day]), NOW)
        if any(n.kind == WISH_IMPOSSIBLE and n.startswith("Nothing is open") for n in r.notes):
            pairs = [(p.id, l.id) for p in catalog.providers_offering(ECHOCARDIOGRAM) for l in [catalog.locations[i]
                     for i in p.location_ids] if "imaging" in l.capabilities]
            assert not any(s.strftime("%A") == day for pid, lid in pairs
                           for s in schedule.open_slots(pid, lid, 45, NOW)), day


def test_language_conflict_is_described_truthfully(catalog, schedule, new_caller):
    r = find_options(catalog, schedule, new_caller, SKIN_CANCER_SCREENING,
                     Preferences(doctor_name_heard="Dr. Daniel Chen", language="Spanish", latest="language"), NOW)
    # language was the latest change, so it wins: Spanish speakers, and a note about Dr. Chen
    assert r.options and all(o.provider_id in (KENJI_KIM_DERM, DANIEL_SMITH_DERM) for o in r.options)
    assert r.notes == ["Dr. Daniel Chen isn't available with a Spanish-speaking doctor."]


def test_unmet_language_keeps_options(catalog, schedule, new_caller):
    r = find_options(catalog, schedule, new_caller, SKIN_CANCER_SCREENING, Preferences(language="Klingon"), NOW)
    assert r.options and r.notes == ["None of the doctors who offer Skin Cancer Screening speaks Klingon."]


def test_ambiguous_place_asks(catalog, schedule, new_caller):
    r = find_options(catalog, schedule, new_caller, SKIN_CANCER_SCREENING, Preferences(location_hint="Mission"), NOW)
    assert PLACE_AMBIGUOUS in _kinds(r)
    assert {o.location_id for o in r.options} <= {MISSION_BAY, MISSION_DISTRICT}


# ---- 5: day and time values the code can't use are refused, not ignored
def test_unusable_day_or_time_is_refused_with_a_way_to_fix_it(catalog, schedule, new_caller):
    for prefs in [Preferences(days=["next Thursday"]), Preferences(time_of_day="lunchtime"),
                  Preferences(time_of_day="evening")]:
        r = find_options(catalog, schedule, new_caller, SKIN_CANCER_SCREENING, prefs, NOW)
        assert not r.options and _kinds(r) == [BAD_INPUT], prefs


def test_any_day_clears_the_wish(catalog, schedule, new_caller):
    card = _card_with(new_caller, DANIEL_CHEN_DERM, RICHMOND)
    card.change_choice("time", days=["Thursday"])
    card.change_choice("time", "any day")
    assert card.preferences.days == []


# ---- 11, 12: structured notes and option numbers that never repeat in a call
def test_notes_and_options_have_a_stable_shape(catalog, schedule, new_caller):
    r = find_options(catalog, schedule, new_caller, SKIN_CANCER_SCREENING, Preferences(location_hint="Mission"), NOW)
    d = r.to_dict()
    assert d["notes"][0]["kind"] == PLACE_AMBIGUOUS and d["notes"][0]["say"]
    assert set(d["options"][0]) >= {"option_id", "provider_name", "location_name", "start", "spoken"}


def test_option_numbers_keep_counting_up(catalog, schedule, new_caller):
    card = BookingCard(caller=new_caller)
    first = find_options(catalog, schedule, new_caller, SKIN_CANCER_SCREENING, Preferences(), NOW,
                         first_option_number=card.next_option_number)
    card.remember_offer(first.options)
    second = find_options(catalog, schedule, new_caller, SKIN_CANCER_SCREENING, Preferences(days=["Friday"]), NOW,
                          first_option_number=card.next_option_number)
    card.remember_offer(second.options)
    assert [o.option_id for o in first.options] == ["1", "2", "3"]
    assert [o.option_id for o in second.options] == ["4", "5", "6"]
    assert card.offered("2") is None and card.offered("5") is not None


def test_same_answer_every_run(catalog, new_caller):
    prefs = Preferences(location_hint="near Union Square")
    a = find_options(catalog, Schedule(catalog), new_caller, SKIN_CANCER_SCREENING, prefs, NOW)
    b = find_options(catalog, Schedule(catalog), new_caller, SKIN_CANCER_SCREENING, prefs, NOW)
    assert [o.to_dict() for o in a.options] == [o.to_dict() for o in b.options]
