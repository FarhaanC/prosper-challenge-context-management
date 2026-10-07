"""Finding options: only valid ones, the newest wish wins, and every note is true."""

from datetime import datetime

import pytest

from catalog_ids import (
    ANNUAL_PHYSICAL, DANIEL_CHEN_DERM, DANIEL_SMITH_DERM, DOWNTOWN, KENJI_KIM_DERM, KNEE_MRI,
    MIDTOWN, MISSION_BAY, MISSION_DISTRICT, MOLE_REMOVAL, NEW_PATIENT_CONSULTATION, NOW, RICHMOND, SKIN_CANCER_SCREENING, WELL_WOMAN_EXAM,
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
    r = find_options(catalog, schedule, james, KNEE_MRI, Preferences(location_hint="Downtown", near=True), NOW)
    assert r.options[0].location_id == DOWNTOWN                     # closest first
    assert {o.location_id for o in r.options} == {DOWNTOWN, MIDTOWN}  # near ranks, doesn't exclude
    assert not r.notes
    _all_valid(catalog, schedule, james, KNEE_MRI, r)


def test_soonest_beats_distance(catalog, schedule, new_caller):  # 13
    prefs = Preferences(location_hint="Downtown", near=True, soonest=True)
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
    card.change_choice("location", "Midtown")
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
    card = BookingCard(caller=new_caller, preferences=Preferences(doctor_name_heard="Dr. Daniel Chen"))
    card.choices = Choices(specialty="Dermatology", visit_type_id=SKIN_CANCER_SCREENING)
    card.change_choice("language", "Spanish")  # R3-5: a language change counts as the latest change
    r = find_options(catalog, schedule, new_caller, SKIN_CANCER_SCREENING, card.preferences, NOW)
    # language was the latest change, so it wins: Spanish speakers, and a note about Dr. Chen
    assert r.options and all(o.provider_id in (KENJI_KIM_DERM, DANIEL_SMITH_DERM) for o in r.options)
    assert [n.say for n in r.notes] == ["Dr. Daniel Chen isn't available with a Spanish-speaking doctor."]


def test_unmet_language_keeps_options(catalog, schedule, new_caller):
    r = find_options(catalog, schedule, new_caller, SKIN_CANCER_SCREENING, Preferences(language="Klingon"), NOW)
    assert r.options and [n.say for n in r.notes] == [  # round 5: a language not in our records says so
        "None of our doctors is listed as speaking Klingon. "
        "Our doctors speak Arabic, English, Hindi, Mandarin, Portuguese, Spanish and Vietnamese."]


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
    prefs = Preferences(location_hint="Union Square", near=True)
    a = find_options(catalog, Schedule(catalog), new_caller, SKIN_CANCER_SCREENING, prefs, NOW)
    b = find_options(catalog, Schedule(catalog), new_caller, SKIN_CANCER_SCREENING, prefs, NOW)
    assert [o.to_dict() for o in a.options] == [o.to_dict() for o in b.options]


# ---- round 2 (docs/reviews/2026-10-06-rules-module/triage.md, round 2 section)
def test_r2_1_location_change_beats_a_doctor_the_caller_only_named(catalog, schedule, new_caller):
    """The realistic order: "skin check with Dr. Chen", then "the Midtown one" before
    picking anything. Goes through change_choice, as a real call does."""
    card = BookingCard(caller=new_caller, preferences=Preferences(doctor_name_heard="Dr. Daniel Chen"))
    card.choices = Choices(specialty="Dermatology", visit_type_id=SKIN_CANCER_SCREENING)
    card.change_choice("location", "Midtown")
    r = find_options(catalog, schedule, new_caller, SKIN_CANCER_SCREENING, card.preferences, NOW)
    assert r.options and all(o.location_id == MIDTOWN for o in r.options)
    assert [n.say for n in r.notes] == ["Dr. Daniel Chen isn't available at Midtown Medical Group."]


def test_r2_2_time_of_day_change_keeps_the_day(catalog, schedule, new_caller):
    card = _card_with(new_caller, DANIEL_CHEN_DERM, RICHMOND)
    card.change_choice("time", "Thursday")
    card.change_choice("time", time_of_day="afternoon")   # round 5: plain fields; the day is kept
    assert (card.preferences.days, card.preferences.time_of_day) == (["Thursday"], "afternoon")
    r = find_options(catalog, schedule, new_caller, SKIN_CANCER_SCREENING, card.preferences, NOW)
    assert r.options and all(o.start.strftime("%A") == "Thursday" and o.start.hour >= 12 for o in r.options)
    card.change_choice("time", days=[], time_of_day="")
    assert (card.preferences.days, card.preferences.time_of_day) == ([], "")


def test_r2_2_thursday_morning_in_one_go(new_caller):
    card = _card_with(new_caller, DANIEL_CHEN_DERM, RICHMOND)
    card.change_choice("time", days=["Thursday"], time_of_day="morning")
    assert (card.preferences.days, card.preferences.time_of_day) == (["Thursday"], "morning")


def test_r2_7_language_note_only_counts_doctors_available_to_this_caller(catalog, schedule, new_caller):
    # Dr. Wei Sato offers skin screening and speaks Hindi, but isn't taking new patients.
    r = find_options(catalog, schedule, new_caller, SKIN_CANCER_SCREENING, Preferences(language="hindi"), NOW)
    assert [n.say for n in r.notes] == ["None of the doctors available to you for Skin Cancer Screening speaks Hindi."]


def test_r2_8_someone_else_is_not_the_same_doctor_again(catalog, schedule, new_caller):
    card = _card_with(new_caller, DANIEL_CHEN_DERM, RICHMOND)
    card.turn_down_doctors(catalog, current=True)   # round 4: the AI says who, the code doesn't read phrases
    r = find_options(catalog, schedule, new_caller, SKIN_CANCER_SCREENING, card.preferences, NOW)
    assert r.options and DANIEL_CHEN_DERM not in {o.provider_id for o in r.options}


def test_r2_10_dates_outside_the_booking_window_are_refused(catalog, schedule, new_caller):
    for day in ["2026-10-01", "2026-12-25", "20261013"]:
        r = find_options(catalog, schedule, new_caller, SKIN_CANCER_SCREENING, Preferences(days=[day]), NOW)
        assert not r.options and _kinds(r) == [BAD_INPUT], day


def test_r2_3_near_an_ambiguous_place_asks_but_does_not_narrow(catalog, schedule, new_caller):
    r = find_options(catalog, schedule, new_caller, SKIN_CANCER_SCREENING,
                     Preferences(location_hint="Market Street", near=True), NOW)
    assert _kinds(r) == [PLACE_AMBIGUOUS]
    assert len({o.location_id for o in r.options}) > 1


def test_r2_3_anywhere_is_no_wish(catalog, schedule, new_caller):
    for hint in ["anywhere", "no preference", "don't mind"]:
        r = find_options(catalog, schedule, new_caller, SKIN_CANCER_SCREENING, Preferences(location_hint=hint), NOW)
        assert r.options and not r.notes, hint


def test_r2_14_an_arabic_speaking_doctor(catalog, schedule, new_caller):
    card = BookingCard(caller=new_caller, preferences=Preferences(doctor_name_heard="Dr. Kenji Kim"))
    card.choices = Choices(specialty="Dermatology", visit_type_id=SKIN_CANCER_SCREENING)
    card.change_choice("language", "Arabic")
    r = find_options(catalog, schedule, new_caller, SKIN_CANCER_SCREENING, card.preferences, NOW)
    assert any("an Arabic-speaking doctor" in n.say for n in r.notes)


def test_r2_6_notes_are_plain_records(catalog, schedule, new_caller):
    import copy
    import json
    import pickle
    r = find_options(catalog, schedule, new_caller, SKIN_CANCER_SCREENING, Preferences(location_hint="Mission"), NOW)
    note = r.notes[0]
    assert copy.deepcopy(note) == note and pickle.loads(pickle.dumps(note)) == note
    assert json.loads(json.dumps(r.to_dict()))["notes"][0]["kind"] == PLACE_AMBIGUOUS


# ---- round 3 (triage.md, round 3 section)
def _offer(catalog, schedule, card, vt=SKIN_CANCER_SCREENING):
    r = find_options(catalog, schedule, card.caller, vt, card.preferences, NOW,
                     first_option_number=card.next_option_number)
    card.remember_offer(r.options)
    return r


def _dermatology_card(caller, **prefs):
    card = BookingCard(caller=caller, preferences=Preferences(**prefs))
    card.choices = Choices(specialty="Dermatology", visit_type_id=SKIN_CANCER_SCREENING)
    return card


def test_r3_1_someone_else_while_hearing_the_options(catalog, schedule, new_caller):
    card = _dermatology_card(new_caller, doctor_name_heard="Dr. Daniel Chen")
    first = _offer(catalog, schedule, card)
    assert {o.provider_id for o in first.options} == {DANIEL_CHEN_DERM}
    card.turn_down_doctors(catalog, on_offer=True)   # "someone else, please" while hearing the options
    second = _offer(catalog, schedule, card)
    assert second.options and DANIEL_CHEN_DERM not in {o.provider_id for o in second.options}
    assert not second.notes


def test_r3_1_someone_else_after_a_time_change(catalog, schedule, new_caller):
    card = _card_with(new_caller, DANIEL_CHEN_DERM, RICHMOND)
    card.change_choice("time", "Thursday")
    card.turn_down_doctors(catalog, current=True)    # Dr. Chen is now only carried over; still "current"
    r = _offer(catalog, schedule, card)
    assert r.options and DANIEL_CHEN_DERM not in {o.provider_id for o in r.options}


def test_r3_1_naming_a_turned_down_doctor_brings_them_back_truthfully(catalog, schedule, new_caller):
    card = _card_with(new_caller, KENJI_KIM_DERM, MIDTOWN)
    card.turn_down_doctors(catalog, current=True)
    card.change_choice("doctor", "Dr. Kenji Kim")   # "actually, he's fine"
    r = _offer(catalog, schedule, card)
    assert r.options and {o.provider_id for o in r.options} == {KENJI_KIM_DERM}
    assert not r.notes


def test_r3_1_a_place_only_a_turned_down_doctor_serves_says_so(catalog, schedule, new_caller):
    card = _card_with(new_caller, KENJI_KIM_DERM, MIDTOWN)
    card.turn_down_doctors(catalog, current=True)
    card.change_choice("location", "Midtown")
    r = _offer(catalog, schedule, card)
    assert [n.say for n in r.notes] == [
        "Midtown Medical Group is only possible with Dr. Kenji Kim, whom you turned down."]
    assert KENJI_KIM_DERM not in {o.provider_id for o in r.options}


def test_r3_1_not_doctor_x(catalog, schedule, new_caller):
    card = _dermatology_card(new_caller)
    card.turn_down_doctors(catalog, provider_ids=[DANIEL_CHEN_DERM])   # "not Dr. Daniel Chen"
    r = _offer(catalog, schedule, card)
    assert r.options and DANIEL_CHEN_DERM not in {o.provider_id for o in r.options}
    assert "not: Dr. Daniel Chen" in card.summary(catalog)


def test_r3_3_surname_list_says_how_many_more(catalog, schedule, new_caller):
    r = find_options(catalog, schedule, new_caller, ANNUAL_PHYSICAL, Preferences(doctor_name_heard="Dr. Dan Chen"), NOW)
    guess = next(n for n in r.notes if n.kind == DOCTOR_NAME_GUESS)
    assert "and 4 more" in guess.say


def test_r5_time_is_plain_values_the_ai_fills_in(catalog, schedule, new_caller):
    # Round 5 (Farhaan's decision): the AI turns "this afternoon" into plain values.
    card = _card_with(new_caller, DANIEL_CHEN_DERM, RICHMOND)
    card.change_choice("time", days=["today"], time_of_day="afternoon")          # "this afternoon"
    assert (card.preferences.days, card.preferences.time_of_day) == (["today"], "afternoon")
    card.change_choice("time", days=["Thursday", "Friday"], time_of_day="morning")  # "Thursday or Friday morning"
    r = find_options(catalog, schedule, new_caller, SKIN_CANCER_SCREENING, card.preferences, NOW)
    assert r.options and all(o.start.strftime("%A") in ("Thursday", "Friday") and o.start.hour < 12
                             for o in r.options)
    card.change_choice("time", days=["I don't mind"], time_of_day="any")          # no-preference words count as ""
    assert (card.preferences.days, card.preferences.time_of_day) == ([], "")


@pytest.mark.parametrize("days", [["this afternoon"], ["Thursday morning"], ["Thursday or Friday"],
                                  ["next Thursday"], ["Thursday works"]])
def test_r5_time_phrases_are_refused_with_how_to_pass_them(catalog, schedule, new_caller, days):
    r = find_options(catalog, schedule, new_caller, SKIN_CANCER_SCREENING, Preferences(days=days), NOW)
    assert not r.options and [n.kind for n in r.notes] == [BAD_INPUT]
    assert "Pass each day on its own" in r.notes[0].say


def test_r3_9_two_word_language_and_grammar(catalog, schedule, new_caller):
    r = find_options(catalog, schedule, new_caller, ANNUAL_PHYSICAL, Preferences(language="Mandarin Chinese"), NOW)
    assert r.options and all("Mandarin" in catalog.providers[o.provider_id].languages for o in r.options)
    from clinic.options import _a
    assert _a("Ukrainian-speaking") == "a Ukrainian-speaking" and _a("Urdu-speaking") == "an Urdu-speaking"


def test_r3_9_nothing_open_today_reads_naturally(catalog, schedule, new_caller):
    late = datetime(2026, 10, 6, 16, 30)
    r = find_options(catalog, schedule, new_caller, SKIN_CANCER_SCREENING, Preferences(days=["today"]), late)
    assert r.notes[0].say == "Nothing is open today for Skin Cancer Screening; here are other options."


# ---- round 4 (triage.md, round 4 section): the AI says exactly who is turned down,
# and the code follows it; the code never reads "someone else" or "not Dr. X".
def _choose(card, option):
    card.choices.provider_id, card.choices.location_id, card.choices.slot = (
        option.provider_id, option.location_id, option.start)


def _referred_for_everything(catalog):
    return Caller(name="Test Caller", patient_id="test", is_new_patient=False,
                  referrals_on_file=catalog.specialties())


@pytest.mark.parametrize("instruction, problem", [
    ({}, "Say which doctors"),
    ({"current": True}, "no current doctor"),
    ({"on_offer": True}, "No options are on offer"),
    ({"provider_ids": ["prov_999"]}, "prov_999"),
])
def test_r4_an_unclear_turn_down_is_refused_and_changes_nothing(catalog, new_caller, instruction, problem):
    card = _dermatology_card(new_caller, doctor_name_heard="Dr. Daniel Chen")
    before = card.to_dict()
    with pytest.raises(ValueError, match=problem):
        card.turn_down_doctors(catalog, **instruction)
    assert card.to_dict() == before


@pytest.mark.parametrize("said", ["someone else", "not Dr. Daniel Chen", "No, not Dr. Chen", "anyone but Dr. Chen",
                                  "another doctor", "the other one", "Dr. Chen please"])
def test_r5_phrases_are_never_read_as_instructions(catalog, schedule, new_caller, said):
    # The AI's mistake: a sentence passed as a name. Round 5 check, must-fix 2: matching it
    # by spelling turned "not Dr. Chen" into a wish FOR Dr. Chen, and "another" into Dr. Andre.
    card = _card_with(new_caller, DANIEL_CHEN_DERM, RICHMOND)
    card.turn_down_doctors(catalog, current=True)
    card.change_choice("doctor", said)
    assert card.preferences.not_provider_ids == [DANIEL_CHEN_DERM]   # nobody brought back by it either
    r = _offer(catalog, schedule, card)
    assert not r.options and [n.kind for n in r.notes] == [BAD_INPUT]
    assert "To turn doctors down, use turn_down_doctors" in r.notes[0].say


def test_r5_a_place_sentence_is_refused_too(catalog, schedule, new_caller):
    r = find_options(catalog, schedule, new_caller, SKIN_CANCER_SCREENING,
                     Preferences(location_hint="anywhere but Downtown"), NOW)
    assert not r.options and [n.kind for n in r.notes] == [BAD_INPUT]


def test_r4_turning_down_the_doctors_on_offer(catalog, schedule, new_caller):
    card = _dermatology_card(new_caller, language="Arabic")   # only Dr. Daniel Chen
    on_offer = {o.provider_id for o in _offer(catalog, schedule, card).options}
    assert on_offer == {DANIEL_CHEN_DERM}
    assert card.turn_down_doctors(catalog, on_offer=True) == "booking"
    assert card.preferences.not_provider_ids == [DANIEL_CHEN_DERM]
    r = _offer(catalog, schedule, card)
    assert r.options and DANIEL_CHEN_DERM not in {o.provider_id for o in r.options}
    assert [n.say for n in r.notes] == ["Arabic is only possible with Dr. Daniel Chen, whom you turned down."]


def test_r4_turning_down_everyone_on_offer_when_nobody_else_can(catalog, schedule, new_caller):
    card = _dermatology_card(new_caller)
    on_offer = {o.provider_id for o in _offer(catalog, schedule, card).options}
    assert on_offer == {DANIEL_CHEN_DERM, DANIEL_SMITH_DERM, KENJI_KIM_DERM}   # every skin doctor
    card.turn_down_doctors(catalog, on_offer=True)
    r = _offer(catalog, schedule, card)
    assert r.options and [n.kind for n in r.notes] == ["no_other_doctor"]


def test_r4_a_doctor_named_back_and_chosen_stays_back(catalog, schedule, new_caller):
    # round-4 check, finding 1: turn down -> "actually Dr. Chen is fine" -> choose him -> "Thursday?"
    card = _dermatology_card(new_caller, doctor_name_heard="Dr. Daniel Chen")
    _choose(card, _offer(catalog, schedule, card).options[0])
    card.turn_down_doctors(catalog, current=True)
    _offer(catalog, schedule, card)
    card.change_choice("doctor", "Dr. Daniel Chen")
    _choose(card, _offer(catalog, schedule, card).options[0])
    card.change_choice("time", "Thursday")
    r = _offer(catalog, schedule, card)
    assert r.options and {o.provider_id for o in r.options} == {DANIEL_CHEN_DERM} and not r.notes
    assert card.preferences.not_provider_ids == [] and "not:" not in card.summary(catalog)


def test_r4_a_surname_alone_does_not_bring_back_a_turned_down_doctor(catalog, schedule, new_caller):
    card = _dermatology_card(new_caller)
    card.turn_down_doctors(catalog, provider_ids=[DANIEL_CHEN_DERM])
    card.change_choice("doctor", "Dr. Chen")   # seven doctors are called Chen
    r = _offer(catalog, schedule, card)
    assert r.options and DANIEL_CHEN_DERM not in {o.provider_id for o in r.options}
    assert [n.say for n in r.notes] == [
        "The only doctor matching 'Dr. Chen' who can do this is Dr. Daniel Chen, whom you turned down. "
        "Check whether the caller wants that doctor after all."]
    assert "not: Dr. Daniel Chen" in card.summary(catalog)


def test_r4_turned_down_day_note_names_only_doctors_with_that_day(catalog, schedule):
    # round-4 check, finding 2: Dr. Kim has nothing that Wednesday, so he mustn't be named
    prefs = Preferences(days=["2026-10-07"], not_provider_ids=[DANIEL_CHEN_DERM, KENJI_KIM_DERM])
    r = find_options(catalog, schedule, _referred_for_everything(catalog), MOLE_REMOVAL, prefs, NOW)
    assert [n.say for n in r.notes] == [
        "Wednesday 7 October is only possible with Dr. Daniel Chen, whom you turned down."]


def test_r4_no_other_doctor_names_only_doctors_who_can(catalog, schedule):
    caller = _referred_for_everything(catalog)
    card = BookingCard(caller=caller)
    card.choices = Choices(specialty="OB/GYN", visit_type_id=WELL_WOMAN_EXAM)
    nguyens = [p.id for p in catalog.providers.values() if p.name.endswith(" Nguyen")]
    assert len(nguyens) > 1
    card.turn_down_doctors(catalog, provider_ids=nguyens)   # "not Dr. Nguyen"
    r = find_options(catalog, schedule, caller, WELL_WOMAN_EXAM, card.preferences, NOW)
    assert [n.say for n in r.notes] == [
        "No other doctor can do Annual Well-Woman Exam for you; Dr. Linda Nguyen (OB/GYN) is the only option."]


def test_r4_no_other_doctor_plural(catalog, schedule, new_caller):
    everyone = [DANIEL_CHEN_DERM, DANIEL_SMITH_DERM, KENJI_KIM_DERM]
    r = find_options(catalog, schedule, new_caller, SKIN_CANCER_SCREENING,
                     Preferences(not_provider_ids=everyone), NOW)
    assert [n.say for n in r.notes] == [
        "No other doctor can do Skin Cancer Screening for you; "
        "Dr. Daniel Chen (Dermatology), Dr. Kenji Kim (Dermatology) and Dr. Daniel Smith (Dermatology) "
        "are the only options."]


@pytest.mark.parametrize("value", ["any language", "not Spanish", "no Spanish please", "Spanish English"])
def test_r4_language_must_be_one_language_name(catalog, schedule, new_caller, value):
    card = _dermatology_card(new_caller)
    card.change_choice("language", value)
    r = _offer(catalog, schedule, card)
    assert [n.kind for n in r.notes] == [BAD_INPUT] and "one language name" in r.notes[0].say
    card.change_choice("language", "")   # how the AI clears it
    assert card.preferences.language == "" and not _offer(catalog, schedule, card).notes


@pytest.mark.parametrize("days, time_of_day", [
    (["Thursday", "Friday"], "morning or afternoon"),   # round 4 check, finding 6
    (["Thursday morning", "Friday afternoon"], ""),     # round 5 check, should-fix 3
    (["Thursday afternoon"], "morning"),
])
def test_r4_morning_or_afternoon_is_refused_not_guessed(catalog, schedule, new_caller, days, time_of_day):
    r = find_options(catalog, schedule, new_caller, SKIN_CANCER_SCREENING,
                     Preferences(days=days, time_of_day=time_of_day), NOW)
    assert not r.options and r.notes and all(n.kind == BAD_INPUT for n in r.notes)


def test_r4_a_named_date_is_not_followed_by_the_booking_window(catalog, schedule, new_caller):
    r = find_options(catalog, schedule, new_caller, SKIN_CANCER_SCREENING, Preferences(days=["2026-10-10"]), NOW)
    assert r.notes[0].say == "Nothing is open on Saturday 10 October for Skin Cancer Screening; here are other options."


# ---- round 5 (triage.md, round 5 section)
def test_r5_no_crash_when_nothing_is_open_and_someone_was_turned_down(catalog, new_caller):
    # Round 5 check, must-fix 1: book every open time of the skin doctors first.
    schedule = Schedule(catalog)
    for pid, t, minutes in list(_every_open_skin_slot(catalog, schedule)):
        schedule.book(pid, t, minutes)
    for prefs in (Preferences(not_provider_ids=[DANIEL_CHEN_DERM]), Preferences(doctor_name_heard="Dr. Garcia")):
        r = find_options(catalog, schedule, new_caller, SKIN_CANCER_SCREENING, prefs, NOW)
        assert not r.options and r.notes[-1].kind == "no_times"
        assert not any(n.say.endswith(": .") or "Doctors who can: ." in n.say for n in r.notes)


def _every_open_skin_slot(catalog, schedule):
    vt = catalog.visit_types[SKIN_CANCER_SCREENING]
    for p in catalog.providers_offering(SKIN_CANCER_SCREENING):
        for lid in p.location_ids:
            for t in schedule.open_slots(p.id, lid, vt.duration_min, NOW):
                yield p.id, t, vt.duration_min


def test_r5_choosing_a_turned_down_doctor_takes_them_off_the_list(catalog, schedule, new_caller):
    # Round 5 check, should-fix 4: turn everyone down, then pick from the "no other doctor" offer.
    card = _dermatology_card(new_caller)
    _offer(catalog, schedule, card)
    card.turn_down_doctors(catalog, on_offer=True)
    picked = card.choose_option(_offer(catalog, schedule, card).options[0].option_id)
    assert picked.provider_id not in card.preferences.not_provider_ids
    assert "not: " + picked.provider_name not in card.summary(catalog)
    card.change_choice("doctor", "")   # even a doctor change doesn't put them back on the list
    assert picked.provider_id not in card.preferences.not_provider_ids


def test_r5_choose_option_refuses_an_option_not_on_offer(catalog, schedule, new_caller):
    card = _dermatology_card(new_caller)
    _offer(catalog, schedule, card)
    with pytest.raises(ValueError, match="isn't on offer"):
        card.choose_option("99")


def test_r5_long_no_other_doctor_list_is_cut_short(catalog, schedule, new_caller):
    # Round 5 check, should-fix 5: say three names and "and N more", like "Doctors who can".
    vt = NEW_PATIENT_CONSULTATION
    everyone = [p.id for p in catalog.providers_offering(vt)]
    r = find_options(catalog, schedule, new_caller, vt, Preferences(not_provider_ids=everyone), NOW)
    note = next(n.say for n in r.notes if n.kind == "no_other_doctor")
    assert " more are the only options." in note and note.count("Dr. ") == 3


def test_r5_plural_grammar_for_several_turned_down_doctors(catalog, schedule, new_caller):
    garcias = [p.id for p in catalog.providers.values() if p.name.endswith(" Garcia")]
    r = find_options(catalog, schedule, new_caller, ANNUAL_PHYSICAL,
                     Preferences(not_provider_ids=garcias, doctor_name_heard="Dr. Garcia"), NOW)
    note = next(n.say for n in r.notes if "turned down" in n.say)
    assert note.startswith("The only doctors matching 'Dr. Garcia' who can do this are ")
    assert note.endswith("Check whether the caller wants one of them after all.")


@pytest.mark.parametrize("said, shown", [("Chinese", "Chinese"), ("español", "Español"), ("ASL", "ASL")])
def test_r5_a_language_we_have_no_record_of_gets_a_true_note(catalog, schedule, new_caller, said, shown):
    r = find_options(catalog, schedule, new_caller, ANNUAL_PHYSICAL, Preferences(language=said), NOW)
    assert r.options and [n.say for n in r.notes] == [
        f"None of our doctors is listed as speaking {shown}. "
        "Our doctors speak Arabic, English, Hindi, Mandarin, Portuguese, Spanish and Vietnamese."]


def test_r5_no_preference_words_count_as_empty_for_language(catalog, schedule, new_caller):
    r = find_options(catalog, schedule, new_caller, ANNUAL_PHYSICAL, Preferences(language="don't mind"), NOW)
    assert r.options and not r.notes


def test_r5_turn_down_accepts_one_id_on_its_own(catalog, new_caller):
    card = _dermatology_card(new_caller)
    card.turn_down_doctors(catalog, provider_ids=DANIEL_CHEN_DERM)
    assert card.preferences.not_provider_ids == [DANIEL_CHEN_DERM]


# ---- round 6 (triage.md, round 6 section)
@pytest.mark.parametrize("said", ["Spanish French", "Spanish only", "only Spanish", "Cantonese Mandarin",
                                  "Spanish Klingon"])
def test_r6_a_language_mixed_with_other_words_is_refused_not_guessed(catalog, schedule, new_caller, said):
    r = find_options(catalog, schedule, new_caller, ANNUAL_PHYSICAL, Preferences(language=said), NOW)
    assert not r.options and [n.kind for n in r.notes] == [BAD_INPUT]


@pytest.mark.parametrize("said, kept", [("Mandarin Chinese", "Mandarin"), ("spanish", "Spanish"),
                                        ("Haitian Creole", "Haitian Creole")])
def test_r6_one_language_name_is_fine(catalog, schedule, new_caller, said, kept):
    r = find_options(catalog, schedule, new_caller, ANNUAL_PHYSICAL, Preferences(language=said), NOW)
    assert r.options and not [n for n in r.notes if n.kind == BAD_INPUT]
    assert all(kept in n.say for n in r.notes)


def _catalog_with_extra_doctors(copies: int):
    """The real catalog plus `copies` more Dr. Daniel Chens in Dermatology, each at one other clinic."""
    import copy as copying

    from clinic import Catalog
    from clinic.catalog import DATA_DIR
    import json
    raw = json.loads((DATA_DIR / "catalog.json").read_text(encoding="utf-8"))
    extras = json.loads((DATA_DIR / "location_extras.json").read_text(encoding="utf-8"))
    chen = next(p for p in raw["providers"] if p["id"] == DANIEL_CHEN_DERM)
    for k, loc in zip(range(copies), [MIDTOWN, MISSION_BAY, MISSION_DISTRICT, "loc_002", "loc_003"]):
        twin = copying.deepcopy(chen)
        twin.update(id=f"prov_twin_{k}", location_ids=[loc])
        raw["providers"].append(twin)
    return Catalog(raw, extras)


def test_r6_same_name_same_specialty_doctors_can_be_told_apart():
    from clinic.options import _who_can
    big = _catalog_with_extra_doctors(1)
    chens = [(big.providers[pid], big.locations[lid]) for pid in (DANIEL_CHEN_DERM, "prov_twin_0")
             for lid in big.providers[pid].location_ids]
    assert _who_can(chens) == ("Dr. Daniel Chen (Dermatology, Downtown Health Center / Richmond Care Center) and "
                               "Dr. Daniel Chen (Dermatology, Midtown Medical Group)")   # both, not just the first


def test_r6_the_same_name_note_reads_three_and_says_how_many_more(new_caller):
    big = _catalog_with_extra_doctors(4)
    r = find_options(big, Schedule(big), new_caller, SKIN_CANCER_SCREENING,
                     Preferences(doctor_name_heard="Dr. Daniel Chen"), NOW)
    note = next(n.say for n in r.notes if n.kind == SAME_NAME)
    assert note.startswith("There are 5 doctors matching 'Dr. Daniel Chen'") and "; and 2 more." in note


def test_r6_near_is_a_plain_yes_no(catalog, schedule, new_caller):
    card = _dermatology_card(new_caller)
    card.change_choice("location", "Downtown", near=True)
    assert (card.preferences.location_hint, card.preferences.near) == ("Downtown", True)
    assert "place: near Downtown" in card.summary(catalog)
    r = _offer(catalog, schedule, card)
    assert len({o.location_id for o in r.options}) > 1   # near ranks by distance; it doesn't restrict
    card.change_choice("location", "Downtown")           # near left out: that place only
    assert {o.location_id for o in _offer(catalog, schedule, card).options} == {DOWNTOWN}
    with pytest.raises(ValueError, match="near goes with a location"):
        card.change_choice("doctor", "Dr. Kenji Kim", near=True)


@pytest.mark.parametrize("what, said", [("doctor", "I don't mind"), ("location", "anywhere"), ("language", "whatever")])
def test_r6_no_preference_words_are_stored_as_empty(catalog, new_caller, what, said):
    card = _dermatology_card(new_caller)
    card.change_choice(what, said)
    p = card.preferences
    assert (p.doctor_name_heard, p.location_hint, p.language) == ("", "", "")
    assert said not in card.summary(catalog)


@pytest.mark.parametrize("day, ok", [("Thursdays", True), ("tues", True), ("thu", True), ("SUN", True),
                                     ("thus", False), ("frid", False), ("wednes", False)])
def test_r6_only_real_weekday_words(catalog, schedule, new_caller, day, ok):
    r = find_options(catalog, schedule, new_caller, SKIN_CANCER_SCREENING, Preferences(days=[day]), NOW)
    assert (BAD_INPUT not in [n.kind for n in r.notes]) == ok


@pytest.mark.parametrize("what", ["provider", "place", "slot", "reason"])
def test_r6_only_the_five_change_names(new_caller, what):
    card = _dermatology_card(new_caller)
    before = card.to_dict()
    with pytest.raises(ValueError, match="visit_type, doctor, location, time or language"):
        card.change_choice(what, "x")
    assert card.to_dict() == before


# ---- round 7 (triage.md, round 7 section)
def test_r7_near_must_be_a_real_yes_or_no(new_caller):
    card = _dermatology_card(new_caller)
    with pytest.raises(ValueError, match="near must be true or false"):
        card.change_choice("location", "Downtown", near="false")


def test_r7_same_name_doctors_are_told_apart_in_every_list(new_caller):
    # Round 7 check, should-fix 2: the "can't do this" reasons and "Doctors with that surname".
    big = _catalog_with_extra_doctors(1)
    twin = big.providers["prov_twin_0"]
    assert twin.name == "Dr. Daniel Chen" and twin.specialty == "Dermatology"
    r = find_options(big, Schedule(big), new_caller, ANNUAL_PHYSICAL, Preferences(doctor_name_heard="Dr. Daniel Chen"),
                     NOW)
    note = next(n.say for n in r.notes if n.kind == WISH_IMPOSSIBLE)
    assert "Dr. Daniel Chen (Dermatology, Downtown Health Center / Richmond Care Center)" in note
    assert "Dr. Daniel Chen (Dermatology, Midtown Medical Group)" in note
    r = find_options(big, Schedule(big), new_caller, SKIN_CANCER_SCREENING, Preferences(doctor_name_heard="Dr. Dan Chen"),
                     NOW)
    guess = next(n.say for n in r.notes if n.kind == DOCTOR_NAME_GUESS)
    # the twin is past the first three names, but the first Dr. Daniel Chen still gets his places
    assert "Dr. Daniel Chen (Dermatology, Downtown Health Center / Richmond Care Center)" in guess


def test_r7_a_long_list_of_places_reads_three_then_or_n_more():
    from clinic.options import _a_few
    assert _a_few(["A", "B"], word="or") == "A or B"
    assert _a_few(["A", "B", "C", "D", "E"], word="or") == "A, B, C or 2 more"
