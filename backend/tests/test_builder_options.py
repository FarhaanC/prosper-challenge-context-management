"""Finding options: only valid ones, the newest wish wins, and every note is true."""

from datetime import datetime

from catalog_ids import (
    ANNUAL_PHYSICAL, DANIEL_CHEN_DERM, DANIEL_SMITH_DERM, DOWNTOWN, KENJI_KIM_DERM, KNEE_MRI,
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
    assert "don't offer Skin Cancer Screening" in r.notes[0].say and "Doctors who can:" in r.notes[0].say
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
    assert r.notes[0].say == "Dr. Daniel Chen isn't available at Midtown Medical Group."


def test_time_change_never_claims_nothing_is_open_when_something_is(catalog, schedule, new_caller):
    card = _card_with(new_caller, DANIEL_CHEN_DERM, RICHMOND)
    card.change_choice("time", days=["Wednesday"])
    r = find_options(catalog, schedule, new_caller, SKIN_CANCER_SCREENING, card.preferences, NOW)
    assert r.options and all(o.start.strftime("%A") == "Wednesday" for o in r.options)
    assert WISH_IMPOSSIBLE not in _kinds(r)


def test_nothing_open_note_appears_when_true_and_only_then(catalog, schedule, new_caller):
    """Replaces a round-1 test that could never fail (round-2 review, T1)."""
    # Clinics are closed at weekends: the note must appear...
    r = find_options(catalog, schedule, new_caller, SKIN_CANCER_SCREENING, Preferences(days=["Saturday"]), NOW)
    assert [n.kind for n in r.notes] == [WISH_IMPOSSIBLE] and r.notes[0].say.startswith("Nothing is open on Saturday")
    # ...and across the catalog, whenever it appears, nobody really has that day free.
    caller = Caller("X", "pat_x", False, catalog.specialties())
    claims = 0
    for vt in catalog.visit_types:
        for day in ["Monday", "Wednesday", "Saturday"]:
            r = find_options(catalog, schedule, caller, vt, Preferences(days=[day]), NOW)
            if any(n.kind == WISH_IMPOSSIBLE and n.say.startswith("Nothing is open") for n in r.notes):
                claims += 1
                for p in catalog.providers_offering(vt):
                    for lid in p.location_ids:
                        assert not any(s.strftime("%A") == day for s in schedule.open_slots(
                            p.id, lid, catalog.visit_types[vt].duration_min, NOW)), (vt, day, p.id)
    assert claims > 0


def test_language_conflict_is_described_truthfully(catalog, schedule, new_caller):
    r = find_options(catalog, schedule, new_caller, SKIN_CANCER_SCREENING,
                     Preferences(doctor_name_heard="Dr. Daniel Chen", language="Spanish", latest="language"), NOW)
    # language was the latest change, so it wins: Spanish speakers, and a note about Dr. Chen
    assert r.options and all(o.provider_id in (KENJI_KIM_DERM, DANIEL_SMITH_DERM) for o in r.options)
    assert [n.say for n in r.notes] == ["Dr. Daniel Chen isn't available with a Spanish-speaking doctor."]


def test_unmet_language_keeps_options(catalog, schedule, new_caller):
    r = find_options(catalog, schedule, new_caller, SKIN_CANCER_SCREENING, Preferences(language="Klingon"), NOW)
    assert r.options and [n.say for n in r.notes] == [
        "None of the doctors available to you for Skin Cancer Screening speaks Klingon."]


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


# ---- round 2 (docs/reviews/2026-10-06-rules-module/triage.md, round 2 section)
def test_r2_1_location_change_beats_a_doctor_the_caller_only_named(catalog, schedule, new_caller):
    """The realistic order: "skin check with Dr. Chen", then "the Midtown one" before
    picking anything. Goes through change_choice, as a real call does."""
    card = BookingCard(caller=new_caller, preferences=Preferences(doctor_name_heard="Dr. Daniel Chen"))
    card.choices = Choices(specialty="Dermatology", visit_type_id=SKIN_CANCER_SCREENING)
    card.change_choice("location", "the Midtown one")
    r = find_options(catalog, schedule, new_caller, SKIN_CANCER_SCREENING, card.preferences, NOW)
    assert r.options and all(o.location_id == MIDTOWN for o in r.options)
    assert [n.say for n in r.notes] == ["Dr. Daniel Chen isn't available at Midtown Medical Group."]


def test_r2_2_time_of_day_change_keeps_the_day(catalog, schedule, new_caller):
    card = _card_with(new_caller, DANIEL_CHEN_DERM, RICHMOND)
    card.change_choice("time", "Thursday")
    card.change_choice("time", "afternoon")
    assert (card.preferences.days, card.preferences.time_of_day) == (["Thursday"], "afternoon")
    r = find_options(catalog, schedule, new_caller, SKIN_CANCER_SCREENING, card.preferences, NOW)
    assert r.options and all(o.start.strftime("%A") == "Thursday" and o.start.hour >= 12 for o in r.options)
    card.change_choice("time", "any time")
    assert (card.preferences.days, card.preferences.time_of_day) == ([], "")


def test_r2_2_thursday_morning_in_one_go(new_caller):
    card = _card_with(new_caller, DANIEL_CHEN_DERM, RICHMOND)
    card.change_choice("time", "Thursday morning")
    assert (card.preferences.days, card.preferences.time_of_day) == (["Thursday"], "morning")


def test_r2_7_language_note_only_counts_doctors_available_to_this_caller(catalog, schedule, new_caller):
    # Dr. Wei Sato offers skin screening and speaks Hindi, but isn't taking new patients.
    r = find_options(catalog, schedule, new_caller, SKIN_CANCER_SCREENING, Preferences(language="hindi"), NOW)
    assert [n.say for n in r.notes] == ["None of the doctors available to you for Skin Cancer Screening speaks Hindi."]


def test_r2_8_someone_else_is_not_the_same_doctor_again(catalog, schedule, new_caller):
    card = _card_with(new_caller, DANIEL_CHEN_DERM, RICHMOND)
    card.change_choice("doctor", "")
    r = find_options(catalog, schedule, new_caller, SKIN_CANCER_SCREENING, card.preferences, NOW)
    assert r.options and DANIEL_CHEN_DERM not in {o.provider_id for o in r.options}


def test_r2_10_dates_outside_the_booking_window_are_refused(catalog, schedule, new_caller):
    for day in ["2026-10-01", "2026-12-25", "20261013"]:
        r = find_options(catalog, schedule, new_caller, SKIN_CANCER_SCREENING, Preferences(days=[day]), NOW)
        assert not r.options and _kinds(r) == [BAD_INPUT], day


def test_r2_3_near_an_ambiguous_place_asks_but_does_not_narrow(catalog, schedule, new_caller):
    r = find_options(catalog, schedule, new_caller, SKIN_CANCER_SCREENING,
                     Preferences(location_hint="near Market Street"), NOW)
    assert _kinds(r) == [PLACE_AMBIGUOUS]
    assert len({o.location_id for o in r.options}) > 1


def test_r2_3_anywhere_is_no_wish(catalog, schedule, new_caller):
    for hint in ["anywhere", "no preference", "don't mind"]:
        r = find_options(catalog, schedule, new_caller, SKIN_CANCER_SCREENING, Preferences(location_hint=hint), NOW)
        assert r.options and not r.notes, hint


def test_r2_9_an_arabic_speaking_doctor(catalog, schedule, new_caller):
    r = find_options(catalog, schedule, new_caller, SKIN_CANCER_SCREENING,
                     Preferences(doctor_name_heard="Dr. Kenji Kim", language="Arabic", latest="language"), NOW)
    assert any("an Arabic-speaking doctor" in n.say for n in r.notes)


def test_r2_6_notes_are_plain_records(catalog, schedule, new_caller):
    import copy
    import json
    import pickle
    r = find_options(catalog, schedule, new_caller, SKIN_CANCER_SCREENING, Preferences(location_hint="Mission"), NOW)
    note = r.notes[0]
    assert copy.deepcopy(note) == note and pickle.loads(pickle.dumps(note)) == note
    assert json.loads(json.dumps(r.to_dict()))["notes"][0]["kind"] == PLACE_AMBIGUOUS
