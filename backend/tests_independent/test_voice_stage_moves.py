"""Voice stages, area 3: which tool moves where, and when it must stay.

Sources: the plan's stages and change_choice table; decision 43 (every change goes
through change_choice; in the booking stage every change rebuilds the stage with fresh
options); 46 (hand_off in every stage); 47 (in stages 1 and 2 change_choice records the
change without moving: it can't skip the identity check); INTERFACE.md "Can move to".
"""

from datetime import date

import pytest

from call import TOOLS
from voice_reference import (BOOKING, END, IDENTIFY, JAMES, KNEE_MRI, NEW, PROV, SKIN_CHECK, VISIT_TYPE,
                             interface_tools, make_clinic, new_call, offered, ref_pairs, snapshot, step,
                             to_booking, to_visit_type)

THURSDAY = 3


@pytest.fixture
def clinic(catalog, directory, tmp_path):
    return make_clinic(catalog, directory, bookings_file=tmp_path / "b.jsonl", log_dir=None)


# ------------------------------------------------------------------ the registry
def test_registry_has_exactly_the_nine_tools():
    assert set(TOOLS) == set(interface_tools())


@pytest.mark.parametrize("name", sorted(interface_tools()))
def test_registry_destinations_match_the_interface(name):
    _, _, moves, _ = interface_tools()[name]
    assert sorted(TOOLS[name].moves_to) == sorted(moves)


# ------------------------------------------------------------------ stage 1
# round 2: change_choice sends the wish fields themselves, not what/new_value (spec note "change_choice has a new shape", decision 51)
@pytest.mark.parametrize("args", [
    {"visit_type": "skin check"},
    {"doctor_name": "Dr. Kenji Kim"},
    {"place": "Midtown"},
    {"days": ["Thursday"]},
    {"language": "Spanish"},
])
def test_change_choice_in_identify_records_without_moving(clinic, args):
    s = new_call(clinic)
    out = step(s, "change_choice", args)
    assert out.result["ok"] is True
    assert out.next_stage is None and s.stage == IDENTIFY, "decision 47: can't skip the identity check"
    assert s.card.caller is None


def test_wish_recorded_in_identify_is_used_later(clinic):
    s = new_call(clinic)
    # round 2: new change_choice shape, days sent on their own (spec note "change_choice has a new shape")
    step(s, "change_choice", {"days": ["Thursday"]})
    step(s, "start_booking", dict(NEW))
    step(s, "choose_visit_type", {"visit_type_id": SKIN_CHECK})
    assert s.card.preferences.days == ["Thursday"]
    assert offered(s) and all(st.weekday() == THURSDAY for *_, st in offered(s))


@pytest.mark.parametrize("tool,args", [
    ("choose_visit_type", {"visit_type_id": SKIN_CHECK}),
    ("list_visit_types", {"specialty": "Dermatology"}),
    ("choose_option", {"option_id": "1"}),
    ("confirm_booking", {}),
    ("turn_down_doctors", {"on_offer": True}),
])
def test_no_tool_skips_identification(clinic, tool, args):
    # These tools belong to later stages; called before anyone is identified they must
    # neither move the call on nor crash.
    s = new_call(clinic)
    before = snapshot(s)
    out = step(s, tool, args)
    assert out.next_stage in (None, IDENTIFY)
    assert out.result.get("ok") is False
    assert snapshot(s) == before


def test_hand_off_from_identify(clinic):
    s = new_call(clinic)
    out = step(s, "hand_off", {"reason": "reschedule"})
    assert out.next_stage == END and s.card.status == "handed_off"


def test_failed_identity_stays_in_identify(clinic):
    s = new_call(clinic)
    out = step(s, "start_booking", {"full_name": "James Wilson", "returning": True, "date_of_birth": "1999-01-01"})
    assert out.next_stage is None and s.stage == IDENTIFY


# ------------------------------------------------------------------ stage 2
# round 2: new change_choice shape (spec note "change_choice has a new shape", decision 51)
@pytest.mark.parametrize("args", [
    {"visit_type": "flu shot"},
    {"doctor_name": "Dr. Kenji Kim"},
    {"place": "Downtown", "near": True},
    {"time_of_day": "afternoon"},
    {"language": "Spanish"},
])
def test_change_choice_in_visit_type_records_without_moving(clinic, args):
    s = to_visit_type(clinic, NEW)
    out = step(s, "change_choice", args)
    assert out.result["ok"] is True and out.next_stage is None and s.stage == VISIT_TYPE


def test_list_visit_types_stays(clinic):
    s = to_visit_type(clinic, NEW)
    assert step(s, "list_visit_types", {"specialty": "Cardiology"}).next_stage is None


def test_accepted_choose_moves_to_booking_with_options_already_found(clinic):
    s = to_visit_type(clinic, NEW)
    out = step(s, "choose_visit_type", {"visit_type_id": SKIN_CHECK})
    assert out.next_stage == BOOKING
    assert s.card.choices.visit_type_id == SKIN_CHECK and s.card.choices.specialty == "Dermatology"
    assert 1 <= len(offered(s)) <= 3, "plan: the code immediately fetches the first options"
    for _, pid, lid, _ in offered(s):
        assert (pid, lid) in ref_pairs(True, SKIN_CHECK)


@pytest.mark.parametrize("stage", [VISIT_TYPE, BOOKING])
def test_hand_off_from_later_stages(clinic, stage):
    s = to_visit_type(clinic, NEW) if stage == VISIT_TYPE else to_booking(clinic)
    if stage == BOOKING:
        step(s, "choose_option", {"option_id": s.card.offered_options[0].option_id})
    out = step(s, "hand_off", {"reason": "speak_to_staff"})
    assert out.next_stage == END and s.stage == END and s.card.status == "handed_off"
    assert not clinic.bookings_file.exists() or clinic.bookings_file.read_text() == "", "nothing is booked"


# ------------------------------------------------------------------ stage 3: change_choice table
def _chosen(s):
    step(s, "choose_option", {"option_id": s.card.offered_options[0].option_id})
    c = s.card.choices
    assert c.provider_id and c.location_id and c.slot
    return c.provider_id, c.location_id, c.slot


def test_change_visit_type_in_booking_goes_to_stage_2_and_clears_what_depended_on_it(clinic):
    s = to_booking(clinic)
    old_numbers = [o[0] for o in offered(s)]
    _chosen(s)
    # round 2: a different visit goes in the visit_type field (spec note "change_choice has a new shape")
    out = step(s, "change_choice", {"visit_type": "knee MRI"})
    assert out.result["ok"] is True and out.next_stage == VISIT_TYPE and s.stage == VISIT_TYPE
    c = s.card.choices
    assert (c.specialty, c.visit_type_id, c.provider_id, c.location_id, c.slot) == ("", "", "", "", None)
    assert not s.card.offered_options
    for n in old_numbers:
        assert step(s, "choose_option", {"option_id": n}).result["ok"] is False
    assert step(s, "confirm_booking", {}).result["ok"] is False
    assert s.card.status == "in_progress"


# round 2: new change_choice shape, one wish field per case (spec note "change_choice has a new shape")
@pytest.mark.parametrize("args,check", [
    ({"days": ["Thursday"]}, lambda pid, lid, st: st.weekday() == THURSDAY),
    ({"time_of_day": "afternoon"}, lambda pid, lid, st: st.hour >= 12),
    ({"doctor_name": "Dr. Daniel Smith"}, lambda pid, lid, st: pid == "prov_035"),
    ({"place": "Midtown"}, lambda pid, lid, st: lid == "loc_005"),
    ({"language": "Spanish"},
     lambda pid, lid, st: "Spanish" in PROV[pid]["languages"]),
])
def test_change_in_booking_rebuilds_booking_with_fresh_options(clinic, args, check):
    s = to_booking(clinic)
    old = offered(s)
    _chosen(s)
    out = step(s, "change_choice", args)
    assert out.result["ok"] is True
    assert out.next_stage == BOOKING and s.stage == BOOKING, "decision 43: every change rebuilds the stage"
    c = s.card.choices
    assert c.visit_type_id == SKIN_CHECK, "the visit type doesn't depend on a doctor/place/time change"
    assert c.slot is None, "the chosen time is cleared"
    new = offered(s)
    assert new and min(int(o[0]) for o in new) > max(int(o[0]) for o in old)
    for _, pid, lid, st in new:
        assert (pid, lid) in ref_pairs(True, SKIN_CHECK)
        assert check(pid, lid, st), (args, PROV[pid]["name"], lid, st)
    assert step(s, "confirm_booking", {}).result["ok"] is False, "nothing chosen after a change"


def test_change_time_keeps_the_doctor_and_place_as_wishes(clinic):
    # Decision 26: the old doctor and place become wishes, honoured if they still fit.
    s = to_booking(clinic)
    pid, lid, slot = _chosen(s)
    # round 2: new change_choice shape, days on their own (spec note "change_choice has a new shape")
    step(s, "change_choice", {"days": [date(2026, 10, 7).isoformat(), date(2026, 10, 8).isoformat(),
                                       date(2026, 10, 9).isoformat(), "Monday", "Tuesday"]})
    p = s.card.preferences
    assert p.preferred_provider_id == pid and p.preferred_location_id == lid


def test_rejected_choose_in_stage_2_stays_put(clinic):
    s = to_visit_type(clinic, NEW)
    out = step(s, "choose_visit_type", {"visit_type_id": KNEE_MRI})
    assert out.result["ok"] is False and out.next_stage is None and s.stage == VISIT_TYPE


def test_choose_option_stays_in_booking(clinic):
    s = to_booking(clinic)
    out = step(s, "choose_option", {"option_id": s.card.offered_options[0].option_id})
    assert out.next_stage is None and s.stage == BOOKING


def test_answer_question_never_moves(clinic):
    for s in (new_call(clinic), to_visit_type(clinic, NEW), to_booking(clinic)):
        stage = s.stage
        before = snapshot(s)
        out = step(s, "answer_question", {"about": "location", "name": "Midtown"})
        assert out.next_stage is None and s.stage == stage
        assert snapshot(s) == before


def test_successful_confirm_moves_to_end(clinic):
    s = to_booking(clinic, KNEE_MRI, JAMES)
    _chosen(s)
    out = step(s, "confirm_booking", {})
    assert out.next_stage == END and s.card.status == "booked"
