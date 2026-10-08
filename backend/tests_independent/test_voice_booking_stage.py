"""Voice stages, area 5: turn_down_doctors, confirm_booking edge cases, hand_off, and the
end of the call.

Sources: decision 37 (turn_down_doctors: ids, on_offer, current; several doctors match a
name -> their ids, call again with doctor_id; fresh options follow); INTERFACE
confirm_booking ("Call only after the caller said yes... If the time was taken meanwhile,
fresh options are found"); decision 46 (hand_off in every stage); the plan's end stage
("says goodbye ... and ends the call"); the clinic module's own rule that a turned-down
doctor is offered again only when nobody else can do it.
"""

import json

import pytest

from voice_reference import (BOOKING, CHENS, END, JAMES, KNEE_MRI, NEW, PROV, SKIN_CHECK, make_clinic, new_call,
                             offered, ref_pairs, section, snapshot, step, to_booking, to_visit_type)


@pytest.fixture
def clinic(catalog, directory, tmp_path):
    return make_clinic(catalog, directory, bookings_file=tmp_path / "b.jsonl", log_dir=None)


def saved_lines(clinic):
    f = clinic.bookings_file
    return f.read_text(encoding="utf-8").splitlines() if f.exists() else []


def choose_first(s):
    o = s.card.offered_options[0]
    assert step(s, "choose_option", {"option_id": o.option_id}).result["ok"] is True
    return o


# ------------------------------------------------------------------ turn_down_doctors
def test_turn_down_on_offer_leaves_out_every_doctor_on_offer(clinic):
    # James (returning) has four dermatologists for a skin check, so someone is left over.
    s = to_booking(clinic, SKIN_CHECK, JAMES)
    old = offered(s)
    out = step(s, "turn_down_doctors", {"on_offer": True})
    assert out.result["ok"] is True and out.next_stage == BOOKING
    gone = {pid for _, pid, _, _ in old}
    others = {p for p, _ in ref_pairs(False, SKIN_CHECK)} - gone
    assert others, "reference: someone else can do a skin check"
    new = offered(s)
    assert new and all(pid not in gone for _, pid, _, _ in new), (gone, new)
    assert min(int(o[0]) for o in new) > max(int(o[0]) for o in old)
    card_text = s.fill("{booking_card}")
    for pid in gone:
        assert PROV[pid]["name"] in card_text, "the card shows who was turned down"


def test_turn_down_current_after_choosing(clinic):
    s = to_booking(clinic)
    o = choose_first(s)
    out = step(s, "turn_down_doctors", {"current": True})
    assert out.result["ok"] is True and out.next_stage == BOOKING
    assert s.card.choices.provider_id == "" and s.card.choices.slot is None
    assert all(pid != o.provider_id for _, pid, _, _ in offered(s))


def test_turn_down_ambiguous_name_asks_which_one_then_takes_an_id(clinic):
    s = to_booking(clinic)
    before = snapshot(s)
    out = step(s, "turn_down_doctors", {"doctor_name": "Dr. Chen"})
    assert out.result["ok"] is False and out.next_stage is None
    assert snapshot(s) == before, "asking which one changes nothing"
    ids = {d["doctor_id"] for d in out.result["which_one"]}
    assert CHENS <= ids, f"every Dr. Chen must be listed: missing {CHENS - ids}"
    for d in out.result["which_one"]:
        assert d["name"] == PROV[d["doctor_id"]]["name"] and d["specialty"] == PROV[d["doctor_id"]]["specialty"]
    out = step(s, "turn_down_doctors", {"doctor_id": "prov_001"})
    assert out.result["ok"] is True and out.next_stage == BOOKING
    assert all(pid != "prov_001" for _, pid, _, _ in offered(s))


def test_turn_down_by_unique_name(clinic):
    s = to_booking(clinic)
    out = step(s, "turn_down_doctors", {"doctor_name": "Dr. Kenji Kim"})
    assert out.result["ok"] is True
    assert all(pid != "prov_027" for _, pid, _, _ in offered(s))


def test_turned_down_doctor_stays_out_after_later_changes(clinic):
    s = to_booking(clinic)
    step(s, "turn_down_doctors", {"doctor_id": "prov_027"})
    # round 2: new change_choice shape (spec note "change_choice has a new shape"); each must be accepted,
    # or this test would pass without testing anything
    assert step(s, "change_choice", {"days": ["Thursday", "Friday"]}).result["ok"] is True
    assert step(s, "change_choice", {"place": "Midtown"}).result["ok"] is True
    # Midtown: of the new-patient dermatologists only Kenji Kim works there, and he's turned down.
    assert offered(s) and all(pid != "prov_027" for _, pid, _, _ in offered(s))


def test_turning_down_everyone_who_can_still_offers_them_with_a_note(clinic):
    s = to_booking(clinic, KNEE_MRI, JAMES)
    step(s, "turn_down_doctors", {"doctor_id": "prov_014"})
    step(s, "turn_down_doctors", {"doctor_id": "prov_015"})
    assert {(p, l) for _, p, l, _ in offered(s)} <= ref_pairs(False, KNEE_MRI)
    assert offered(s), "nobody else can do it, so they're offered anyway"
    told = " ".join(section(s.fill("{options}"), "Tell the caller first"))
    assert "MRI - Knee" in told and "only" in told


def test_change_of_visit_type_starts_the_turned_down_list_again(clinic):
    s = to_booking(clinic, KNEE_MRI, JAMES)
    step(s, "turn_down_doctors", {"doctor_id": "prov_014"})
    # round 2: new change_choice shape (spec note "change_choice has a new shape")
    assert step(s, "change_choice", {"visit_type": "x-ray"}).result["ok"] is True
    assert s.card.preferences.not_provider_ids == []


# ------------------------------------------------------------------ confirm_booking
def test_confirm_with_nothing_chosen_is_refused(clinic):
    s = to_booking(clinic)
    before = snapshot(s)
    out = step(s, "confirm_booking", {})
    assert out.result["ok"] is False and out.next_stage is None
    assert snapshot(s) == before and saved_lines(clinic) == []


def test_confirming_twice_saves_once(clinic):
    s = to_booking(clinic, KNEE_MRI, JAMES)
    choose_first(s)
    assert step(s, "confirm_booking", {}).result["ok"] is True
    before = snapshot(s)
    out = step(s, "confirm_booking", {})
    assert out.result["ok"] is False and out.next_stage is None
    assert snapshot(s) == before
    assert len(saved_lines(clinic)) == 1


def test_time_taken_meanwhile_gives_fresh_options_and_saves_nothing(clinic):
    a = to_booking(clinic)
    b = to_booking(clinic)
    oa = choose_first(a)
    ob = next(o for o in b.card.offered_options if (o.provider_id, o.start) == (oa.provider_id, oa.start))
    step(b, "choose_option", {"option_id": ob.option_id})
    assert step(a, "confirm_booking", {}).result["ok"] is True
    old_numbers = [o[0] for o in offered(b)]
    out = step(b, "confirm_booking", {})
    assert out.result["ok"] is False
    assert out.next_stage == BOOKING and b.stage == BOOKING
    assert b.card.status == "in_progress"
    assert b.card.choices.slot is None and b.card.choices.visit_type_id == SKIN_CHECK
    new = offered(b)
    assert new, "fresh options are found"
    assert all(not (pid == oa.provider_id and st == oa.start) for _, pid, _, st in new)
    assert min(int(o[0]) for o in new) > max(int(n) for n in old_numbers)
    assert len(saved_lines(clinic)) == 1
    assert "no longer available" in s_text(b).lower() or "taken" in s_text(b).lower()


def s_text(s):
    return s.fill("{options}")


def test_confirm_after_a_change_is_refused(clinic):
    s = to_booking(clinic)
    choose_first(s)
    # round 2: new change_choice shape (spec note "change_choice has a new shape")
    assert step(s, "change_choice", {"time_of_day": "afternoon"}).result["ok"] is True
    out = step(s, "confirm_booking", {})
    assert out.result["ok"] is False and saved_lines(clinic) == []


def test_confirm_saves_exactly_the_option_read_back(clinic):
    s = to_booking(clinic)
    o = s.card.offered_options[2]
    rb = step(s, "choose_option", {"option_id": o.option_id}).result["read_back"]
    step(s, "confirm_booking", {})
    saved = json.loads(saved_lines(clinic)[0])
    assert (saved["provider_id"], saved["location_id"], saved["start"]) == \
           (o.provider_id, o.location_id, o.start.isoformat())
    assert saved["read_back"] == rb


# ------------------------------------------------------------------ hand_off and the end
@pytest.mark.parametrize("reason,word", [("reschedule", "reschedule"), ("cancel", "cancel"),
                                         ("speak_to_staff", "staff")])
def test_hand_off_outcome_says_why(clinic, reason, word):
    s = to_visit_type(clinic, NEW)
    out = step(s, "hand_off", {"reason": reason})
    assert out.next_stage == END
    outcome = s.fill("{outcome}").lower()
    assert word in outcome and "staff" in outcome


def test_hand_off_after_a_booking_keeps_the_booking(clinic):
    s = to_booking(clinic, KNEE_MRI, JAMES)
    choose_first(s)
    step(s, "confirm_booking", {})
    step(s, "hand_off", {"reason": "speak_to_staff"})
    assert s.card.status == "booked", "the saved booking must not be undone"
    assert len(saved_lines(clinic)) == 1


# round 2: new change_choice shape, so the refusal comes from the finished call and not from an
# unknown "what" field (spec note "change_choice has a new shape"; "The order of a call", decision 55)
@pytest.mark.parametrize("args", [
    {"days": ["Thursday"]},
    {"visit_type": "flu shot"},
    {"doctor_name": "Dr. Kenji Kim"},
])
@pytest.mark.parametrize("ending", ["booked", "handed_off"])
def test_change_choice_after_the_call_ended_is_refused(clinic, args, ending):
    s = to_booking(clinic)
    if ending == "booked":
        choose_first(s)
        step(s, "confirm_booking", {})
    else:
        step(s, "hand_off", {"reason": "speak_to_staff"})
    before = snapshot(s)
    out = step(s, "change_choice", args)
    assert out.result["ok"] is False and out.next_stage is None
    assert snapshot(s) == before


AFTER_END = [
    ("choose_visit_type", {"visit_type_id": "appt_028"}),
    ("choose_option", {"option_id": "2"}),
    ("turn_down_doctors", {"current": True}),
    ("confirm_booking", {}),
    ("start_booking", {"full_name": "Someone Else", "returning": False}),
]


@pytest.mark.parametrize("tool,args", AFTER_END, ids=[t for t, _ in AFTER_END])
def test_nothing_reopens_a_booked_call(clinic, tool, args):
    s = to_booking(clinic)
    choose_first(s)
    step(s, "confirm_booking", {})
    before = snapshot(s)
    out = step(s, tool, args)
    assert out.next_stage in (None, END), f"{tool} moved a finished call to {out.next_stage}"
    assert snapshot(s) == before, f"{tool} changed a finished call"


@pytest.mark.parametrize("tool,args", AFTER_END, ids=[t for t, _ in AFTER_END])
def test_nothing_reopens_a_handed_off_call(clinic, tool, args):
    s = new_call(clinic)
    step(s, "hand_off", {"reason": "cancel"})
    before = snapshot(s)
    out = step(s, tool, args)
    assert out.next_stage in (None, END), f"{tool} moved a finished call to {out.next_stage}"
    assert snapshot(s) == before, f"{tool} changed a finished call"


def test_answer_question_still_works_after_the_end(clinic):
    s = new_call(clinic)
    step(s, "hand_off", {"reason": "cancel"})
    out = step(s, "answer_question", {"about": "location", "name": "Midtown"})
    assert out.result["found"] is True
    assert out.result["results"][0]["name"] == "Midtown Medical Group"


def test_answer_question_lists_every_doctor_sharing_a_name(clinic):
    s = to_booking(clinic)
    before = snapshot(s)
    out = step(s, "answer_question", {"about": "doctor", "name": "Dr. Maria Garcia"})
    assert out.next_stage is None and snapshot(s) == before
    got = sorted((r["specialty"]) for r in out.result["results"])
    assert got == sorted(PROV[p]["specialty"] for p in ("prov_002", "prov_003"))
