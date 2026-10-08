"""Round 2: turn_down_doctors in every stage (decision 53; spec note "turn_down_doctors is
available in every stage").

- A global tool now, no longer in the booking stage's own list.
- Before options are on offer it works by doctor_name (or doctor_id), and records without
  moving, as change_choice does: before identification, and in the visit_type stage.
- It can move to visit_type (stay) or booking.
- The turned-down doctors are honoured once options are found.

Who can do a skin check comes from catalog.json (reference.py).
"""

import pytest

from voice_reference import (BOOKING, CHENS, IDENTIFY, JAMES, NEW, PROV, SKIN_CHECK, VISIT_TYPE, make_clinic,
                             new_call, offered, ref_pairs, step, to_visit_type)
from voice_round2_reference import refused_unchanged

KIM, SMITH, DANIEL_CHEN = "prov_027", "prov_035", "prov_001"


@pytest.fixture
def clinic(catalog, directory, tmp_path):
    return make_clinic(catalog, directory, bookings_file=tmp_path / "b.jsonl", log_dir=None)


def at(clinic, where):
    return new_call(clinic) if where == IDENTIFY else to_visit_type(clinic, NEW)


@pytest.mark.parametrize("where", [IDENTIFY, VISIT_TYPE])
@pytest.mark.parametrize("args,pid", [({"doctor_name": "Dr. Kenji Kim"}, KIM), ({"doctor_id": KIM}, KIM),
                                      ({"doctor_name": "Dr. Daniel Smith"}, SMITH)],
                         ids=["by name", "by id", "another name"])
def test_turn_down_before_options_records_without_moving(clinic, where, args, pid):
    s = at(clinic, where)
    out = step(s, "turn_down_doctors", args)
    assert out.result["ok"] is True, out.result
    assert out.next_stage is None and s.stage == where, "records without moving, as change_choice does"
    assert pid in s.card.preferences.not_provider_ids
    if where == IDENTIFY:
        assert s.card.caller is None


@pytest.mark.parametrize("where", [IDENTIFY, VISIT_TYPE])
def test_turned_down_before_options_is_honoured_by_the_first_options(clinic, where):
    s = at(clinic, where)
    step(s, "turn_down_doctors", {"doctor_name": "Dr. Kenji Kim"})
    if where == IDENTIFY:
        step(s, "start_booking", dict(NEW))
    out = step(s, "choose_visit_type", {"visit_type_id": SKIN_CHECK})
    assert out.result["ok"] is True and s.stage == BOOKING
    others = {p for p, _ in ref_pairs(True, SKIN_CHECK)} - {KIM}
    assert others, "reference: other doctors can do a skin check for a new patient"
    assert offered(s) and all(pid != KIM for _, pid, _, _ in offered(s))
    assert PROV[KIM]["name"] in s.fill("{booking_card}"), "the card shows who was turned down"


def test_two_doctors_turned_down_before_identification_leave_the_third(clinic):
    s = new_call(clinic)
    step(s, "turn_down_doctors", {"doctor_name": "Dr. Kenji Kim"})
    step(s, "turn_down_doctors", {"doctor_id": DANIEL_CHEN})
    step(s, "start_booking", dict(NEW))
    step(s, "choose_visit_type", {"visit_type_id": SKIN_CHECK})
    assert {p for p, _ in ref_pairs(True, SKIN_CHECK)} == {KIM, DANIEL_CHEN, SMITH}
    assert offered(s) and all(pid == SMITH for _, pid, _, _ in offered(s))


@pytest.mark.parametrize("where", [IDENTIFY, VISIT_TYPE])
def test_ambiguous_name_before_options_asks_which_one_and_changes_nothing(clinic, where):
    s = at(clinic, where)
    before_stage = s.stage
    out = step(s, "turn_down_doctors", {"doctor_name": "Dr. Chen"})
    assert out.result["ok"] is False and out.next_stage is None and s.stage == before_stage
    ids = {d["doctor_id"] for d in out.result["which_one"]}
    assert CHENS <= ids
    assert s.card.preferences.not_provider_ids == []


@pytest.mark.parametrize("where", [IDENTIFY, VISIT_TYPE])
@pytest.mark.parametrize("args", [{"on_offer": True}, {"current": True}, {"doctor_name": "Dr. Nobody Atall"},
                                  {"doctor_name": "someone else"}, {"doctor_id": "prov_999"}, {},
                                  {"doctor_name": "Dr. Kenji Kim", "reason": "rude"}],
                         ids=["on_offer", "current", "unknown name", "a sentence", "unknown id", "nothing",
                              "unknown field"])
def test_turn_down_before_options_refuses_what_it_cant_follow(clinic, where, args):
    s = at(clinic, where)
    refused_unchanged(s, "turn_down_doctors", args)


def test_turn_down_in_stage_2_keeps_the_wishes_already_said(clinic):
    s = to_visit_type(clinic, JAMES, days=["Thursday"], doctor_name="Dr. Daniel Smith")
    step(s, "turn_down_doctors", {"doctor_id": KIM})
    p = s.card.preferences
    assert p.days == ["Thursday"]
    assert KIM in p.not_provider_ids
