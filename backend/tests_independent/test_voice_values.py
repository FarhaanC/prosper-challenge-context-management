"""Voice stages, area 4: what comes in from the AI (decisions 37-40, 42, 47).

38: each day entry is one weekday, "today", "tomorrow" or a date; the time of day is
"morning" or "afternoon"; anything else is refused with a note saying how to send it.
39: near is a yes/no passed with a place name. 37: "someone else" / "not Dr. X" are never
read from a name field. 40: names are matched forgivingly; "no preference" words count as
empty; words no name has ("not") are refused; anything else is refused, never guessed.
42: two-word language values are refused unless they're one language name.

A refused call must change NOTHING: not the card, not the stage, not the options on offer.
"""

import pytest

from voice_reference import (BOOKING, IDENTIFY, NEW, PROV, SKIN_CHECK, VISIT_TYPE, make_clinic, new_call, offered,
                             snapshot, step, to_booking, to_visit_type)


@pytest.fixture
def clinic(catalog, directory, tmp_path):
    return make_clinic(catalog, directory, bookings_file=tmp_path / "b.jsonl", log_dir=None)


def refused_without_change(s, tool, args):
    before = snapshot(s)
    out = step(s, tool, args)
    assert out.result.get("ok") is False, (tool, args, out.result)
    assert out.next_stage is None, (tool, args, out.next_stage)
    msg = out.result.get("error") or out.result.get("say") or ""
    assert msg.strip(), f"a refusal must say how to send the value: {out.result}"
    assert snapshot(s) == before, f"a refused {tool} changed the call: {args}"
    return msg


# The same unusable wish values, sent through each tool that takes wishes.
BAD_WISHES = [
    ("days as text", {"days": "Thursday"}),
    ("day and time in one entry", {"days": ["Thursday morning"]}),
    ("two days in one entry", {"days": ["Thursday or Friday"]}),
    ("a phrase as a day", {"days": ["next week"]}),
    ("a time of day as a day", {"days": ["morning"]}),
    ("a date outside the window", {"days": ["2027-01-01"]}),
    ("a date in the past", {"days": ["2026-10-01"]}),
    ("a day that isn't text", {"days": [5]}),
    ("evening", {"time_of_day": "evening"}),
    ("morning or afternoon", {"time_of_day": "morning or afternoon"}),
    ("someone else as a doctor", {"doctor_name": "someone else"}),
    ("not Dr. Chen as a doctor", {"doctor_name": "not Dr. Chen"}),
    ("anyone but Dr. Kim", {"doctor_name": "anyone but Dr. Kim"}),
    ("a different doctor", {"doctor_name": "a different doctor"}),
    ("near without a place", {"near": True}),
    ("near as text", {"place": "Downtown", "near": "true"}),
    ("a place sentence", {"place": "anywhere but Downtown"}),
    ("soonest as text", {"soonest": "yes"}),
    ("a language sentence", {"language": "not Spanish"}),
    ("two languages", {"language": "Spanish French"}),
    ("a doctor name that isn't text", {"doctor_name": 7}),
]


@pytest.mark.parametrize("label,wish", BAD_WISHES, ids=[b[0] for b in BAD_WISHES])
def test_start_booking_refuses_unusable_wishes_and_changes_nothing(clinic, label, wish):
    s = new_call(clinic)
    refused_without_change(s, "start_booking", {**NEW, **wish})
    assert s.stage == IDENTIFY and s.card.caller is None


@pytest.mark.parametrize("label,wish", BAD_WISHES, ids=[b[0] for b in BAD_WISHES])
def test_choose_visit_type_refuses_unusable_wishes_and_changes_nothing(clinic, label, wish):
    s = to_visit_type(clinic, NEW)
    refused_without_change(s, "choose_visit_type", {"visit_type_id": SKIN_CHECK, **wish})
    assert s.stage == VISIT_TYPE and not s.card.offered_options


def test_refusal_messages_say_how_to_send_the_value(clinic):
    s = new_call(clinic)
    msg = refused_without_change(s, "start_booking", {**NEW, "days": ["Thursday morning"]})
    assert "morning" in msg.lower() and "time of day" in msg.lower()
    msg = refused_without_change(s, "start_booking", {**NEW, "doctor_name": "someone else"})
    assert "turn_down_doctors" in msg, "decision 37: point the AI at turn_down_doctors"
    msg = refused_without_change(s, "start_booking", {**NEW, "near": True})
    assert "place" in msg.lower()


@pytest.mark.parametrize("args", [
    {"full_name": "Farhan Jida", "returning": "no"},
    {"full_name": "Farhan Jida", "returning": "false"},
    {"full_name": "Farhan Jida", "returning": 0},
    {"full_name": "Farhan Jida"},
    {"returning": False},
    {"full_name": 123, "returning": False},
    {"full_name": "", "returning": False},
    {"full_name": "James Wilson", "returning": True, "date_of_birth": 19840312},
])
def test_start_booking_refuses_bad_identity_values(clinic, args):
    s = new_call(clinic)
    before = snapshot(s)
    out = step(s, "start_booking", args)
    assert out.result.get("ok") is False and out.next_stage is None
    assert s.card.caller is None
    if "status" not in out.result:  # an identity step legitimately counts tries; a value error doesn't
        assert snapshot(s) == before


# ------------------------------------------------------------------ change_choice values
# round 2: every case rewritten in the new change_choice shape (spec note "change_choice has a new
# shape", decision 51). In the old shape all of these were refused just because "what" is now an
# unknown field, so they no longer tested the value. Each keeps its old purpose:
# - "time as a phrase" now puts the phrase in time_of_day (the old new_value for a time is gone);
# - "time with nothing" becomes a call with no fields ("nothing sent" is refused);
# - "near without a place" sends place "" (an empty value counts as not sent);
# - "unknown kind" becomes an unknown field; "no kind" is unchanged (new_value is now an unknown field).
BAD_CHANGES = [
    ("someone else", {"doctor_name": "someone else"}),
    ("not Dr. Kim", {"doctor_name": "not Dr. Kim"}),
    ("time as a phrase", {"time_of_day": "Thursday morning"}),
    ("day and time in one entry", {"days": ["Thursday morning"]}),
    ("days as text", {"days": "Thursday"}),
    ("evening", {"time_of_day": "evening"}),
    ("time with nothing", {}),
    ("date outside window", {"days": ["2027-01-01"]}),
    ("place sentence", {"place": "anywhere but Downtown"}),
    ("near as text", {"place": "Downtown", "near": "yes"}),
    ("near with a time change", {"days": ["Friday"], "near": True}),
    ("near without a place", {"place": "", "near": True}),
    ("language sentence", {"language": "not Spanish"}),
    ("two languages", {"language": "Spanish French"}),
    ("unknown kind", {"mood": "happy"}),
    ("no kind", {"new_value": "Dr. Kim"}),
    ("value not text", {"doctor_name": 42}),
]


@pytest.mark.parametrize("label,args", BAD_CHANGES, ids=[b[0] for b in BAD_CHANGES])
def test_change_choice_in_booking_refuses_and_keeps_the_options_on_offer(clinic, label, args):
    s = to_booking(clinic)
    first = s.card.offered_options[0].option_id
    refused_without_change(s, "change_choice", args)
    assert s.stage == BOOKING
    out = step(s, "choose_option", {"option_id": first})
    assert out.result["ok"] is True, "after a refused change the options on offer still stand"


def test_change_choice_doctor_does_not_silently_drop_a_day_sent_with_it(clinic):
    # INTERFACE: "Send what, plus only the fields for that kind". A day sent with a doctor
    # change must be refused, or honoured; dropping it silently loses the caller's wish.
    # round 2: new change_choice shape. Decision 51 settles the either/or: every field sent is
    # applied, so both the doctor and the day must now be on the card (spec note "Several fields
    # can go in one call").
    s = to_booking(clinic)
    out = step(s, "change_choice", {"doctor_name": "Dr. Kenji Kim", "days": ["Thursday"]})
    assert out.result.get("ok") is True, out.result
    assert s.card.preferences.days == ["Thursday"], "the day wish was silently dropped"
    assert s.card.preferences.doctor_name_heard == "Dr. Kenji Kim"


def test_unknown_field_is_not_silently_dropped(clinic):
    # Decision 40: anything that isn't a plain instruction is refused, never guessed.
    # "doctor" instead of "doctor_name" must not vanish without a word.
    s = new_call(clinic)
    out = step(s, "start_booking", {**NEW, "doctor": "Dr. Kenji Kim"})
    assert out.result.get("ok") is False or s.card.preferences.doctor_name_heard, out.result


# ------------------------------------------------------------------ accepted plain values
@pytest.mark.parametrize("days", [["Thursday", "Friday"], ["today"], ["tomorrow"], ["2026-10-13"], ["thursday"]])
def test_plain_days_accepted_and_honoured(clinic, days):
    s = to_booking(clinic, SKIN_CHECK, NEW, days=days)
    assert s.card.preferences.days == days
    allowed = {"thursday": {3}, "friday": {4}}
    for _, _, _, st in offered(s):
        if days == ["today"]:
            assert st.date().isoformat() == "2026-10-06"
        elif days == ["tomorrow"]:
            assert st.date().isoformat() == "2026-10-07"
        elif days == ["2026-10-13"]:
            assert st.date().isoformat() == "2026-10-13"
        else:
            ok = set().union(*(allowed[d.lower()] for d in days))
            assert st.weekday() in ok


def test_morning_honoured(clinic):
    s = to_booking(clinic, SKIN_CHECK, NEW, time_of_day="morning")
    assert offered(s) and all(st.hour < 12 for *_, st in offered(s))


@pytest.mark.parametrize("word", ["any", "no preference", "I don't mind"])
def test_no_preference_words_count_as_empty(clinic, word):
    s = new_call(clinic)
    out = step(s, "start_booking", {**NEW, "doctor_name": word, "language": word})
    assert out.result["ok"] is True
    p = s.card.preferences
    assert p.doctor_name_heard == "" and p.language == ""


# ------------------------------------------------------------------ ids and numbers
@pytest.mark.parametrize("vid", ["appt_999", 27, "Skin Cancer Screening", "", None, ["appt_027"]])
def test_choose_visit_type_refuses_anything_but_a_catalog_id(clinic, vid):
    s = to_visit_type(clinic, NEW)
    refused_without_change(s, "choose_visit_type", {"visit_type_id": vid})


@pytest.mark.parametrize("oid", ["4", "0", "one", "", None, "Option 1", "-1"])
def test_choose_option_refuses_numbers_not_on_offer(clinic, oid):
    s = to_booking(clinic)
    refused_without_change(s, "choose_option", {"option_id": oid})


def test_choose_option_refuses_a_stale_number_after_fresh_options(clinic):
    s = to_booking(clinic)
    stale = [o[0] for o in offered(s)]
    # round 2: new change_choice shape (spec note "change_choice has a new shape")
    assert step(s, "change_choice", {"days": ["Friday"]}).result["ok"] is True
    for n in stale:
        refused_without_change(s, "choose_option", {"option_id": n})


def test_refused_choose_option_keeps_an_earlier_choice(clinic):
    s = to_booking(clinic)
    step(s, "choose_option", {"option_id": s.card.offered_options[1].option_id})
    chosen = (s.card.choices.provider_id, s.card.choices.slot)
    refused_without_change(s, "choose_option", {"option_id": "99"})
    assert (s.card.choices.provider_id, s.card.choices.slot) == chosen


@pytest.mark.parametrize("args", [
    {}, {"doctor_id": "prov_999"}, {"on_offer": "yes"}, {"current": "true"},
    {"doctor_name": "someone else"}, {"doctor_name": "not Dr. Kim"}, {"doctor_name": "Dr. Nobody Atall"},
    {"current": True},  # nothing chosen yet
])
def test_turn_down_doctors_refuses_unusable_instructions(clinic, args):
    s = to_booking(clinic)
    refused_without_change(s, "turn_down_doctors", args)


@pytest.mark.parametrize("reason", [None, "", "complaint", "Speak to staff", 1])
def test_hand_off_refuses_unknown_reasons(clinic, reason):
    s = new_call(clinic)
    args = {} if reason is None else {"reason": reason}
    refused_without_change(s, "hand_off", args)


@pytest.mark.parametrize("specialty", ["", "Astrology", 5])
def test_list_visit_types_unknown_specialty_is_refused(clinic, specialty):
    s = to_visit_type(clinic, NEW)
    refused_without_change(s, "list_visit_types", {"specialty": specialty})


def test_wishes_travel_with_choose_visit_type(clinic):
    # Decision 47: choose_visit_type takes the same wish fields, used for the first options.
    s = to_visit_type(clinic, NEW)
    out = step(s, "choose_visit_type", {"visit_type_id": SKIN_CHECK, "days": ["Thursday"],
                                        "time_of_day": "afternoon", "language": "Spanish"})
    assert out.result["ok"] is True and s.stage == BOOKING
    p = s.card.preferences
    assert p.days == ["Thursday"] and p.time_of_day == "afternoon" and p.language == "Spanish"
    for _, pid, _, st in offered(s):
        assert st.weekday() == 3 and st.hour >= 12 and "Spanish" in PROV[pid]["languages"]
