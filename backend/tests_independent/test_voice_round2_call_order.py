"""Round 2: the order of a call, and the smaller tool changes (decision 55; spec notes
"The order of a call" and "Smaller changes").

- Once booked or handed off, every tool except answer_question and hand_off is refused
  and changes nothing.
- Until start_booking succeeds, list_visit_types, choose_visit_type, choose_option and
  confirm_booking are refused ("Identify the caller first...").
- Any tool, any time: a field it doesn't have is refused, naming the fields it does have.
- run_tool with an unknown tool name raises a ValueError naming the tools.
- answer_question: reply has ok (true when found); about and name must be text.
- choose_option: the number must be digits ("2" or 2); "Option 2" is refused.
- hand_off: handed_off is true only when the call's status changed.
- Triage R8: going back to choosing after a failed confirm keeps "soonest".
- Triage R9: the booking is written to the file before the time is marked taken.
"""

import copy

import pytest

from call import TOOLS, run_tool
from clinic import PatientDirectory
from voice_reference import (BOOKING, END, IDENTIFY, JAMES, KNEE_MRI, NEW, NOW, PATIENT, PATIENTS, SKIN_CHECK,
                             interface_tools, make_clinic, new_call, offered, snapshot, step, to_booking,
                             to_visit_type)
from voice_round2_reference import fields_of, refused_unchanged


@pytest.fixture
def clinic(catalog, directory, tmp_path):
    return make_clinic(catalog, directory, bookings_file=tmp_path / "b.jsonl", log_dir=None)


def booked(clinic):
    s = to_booking(clinic, KNEE_MRI, JAMES)
    step(s, "choose_option", {"option_id": s.card.offered_options[0].option_id})
    assert step(s, "confirm_booking", {}).result["ok"] is True and s.card.status == "booked"
    return s


def handed_off(clinic):
    s = to_booking(clinic)
    step(s, "choose_option", {"option_id": s.card.offered_options[0].option_id})
    assert step(s, "hand_off", {"reason": "speak_to_staff"}).result["ok"] is True
    assert s.card.status == "handed_off"
    return s


def twins_handed_off(catalog, directory):
    twin = copy.deepcopy(PATIENT["James Wilson"])
    twin["id"] = "pat_099"
    c = make_clinic(catalog, directory, patients=PatientDirectory(copy.deepcopy(PATIENTS) + [twin]))
    s = new_call(c)
    step(s, "start_booking", dict(JAMES))
    assert s.card.status == "handed_off"
    return s


# ================================================================== a finished call
AFTER_END = [
    ("start_booking", {"full_name": "Someone Else", "returning": False}),
    ("list_visit_types", {"specialty": "Dermatology"}),
    ("choose_visit_type", {"visit_type_id": SKIN_CHECK}),
    ("choose_option", {"option_id": "1"}),
    ("confirm_booking", {}),
    ("change_choice", {"days": ["Friday"], "place": "Midtown"}),
    ("change_choice", {"visit_type": "flu shot"}),
    ("change_choice", {"doctor_name": "any"}),
    ("turn_down_doctors", {"doctor_name": "Dr. Kenji Kim"}),
    ("turn_down_doctors", {"doctor_id": "prov_014"}),
    ("turn_down_doctors", {"current": True}),
    ("turn_down_doctors", {"on_offer": True}),
]
IDS = [f"{t}-{i}" for i, (t, _) in enumerate(AFTER_END)]


@pytest.mark.parametrize("ending", ["booked", "handed_off", "same name and birthday"])
@pytest.mark.parametrize("tool,args", AFTER_END, ids=IDS)
def test_a_finished_call_refuses_every_other_tool(clinic, catalog, directory, ending, tool, args):
    s = {"booked": lambda: booked(clinic), "handed_off": lambda: handed_off(clinic),
         "same name and birthday": lambda: twins_handed_off(catalog, directory)}[ending]()
    refused_unchanged(s, tool, args)
    assert s.stage == END


@pytest.mark.parametrize("ending", ["booked", "handed_off"])
def test_a_finished_call_still_answers_questions(clinic, ending):
    s = booked(clinic) if ending == "booked" else handed_off(clinic)
    before = snapshot(s)
    out = step(s, "answer_question", {"about": "doctor", "name": "Dr. Kenji Kim"})
    assert out.result["ok"] is True and out.next_stage is None and snapshot(s) == before


def test_hand_off_after_a_booking_says_it_did_not_change_the_status(clinic):
    s = booked(clinic)
    lines_before = clinic.bookings_file.read_text(encoding="utf-8")
    out = step(s, "hand_off", {"reason": "speak_to_staff"})
    assert out.result.get("handed_off") is False, out.result
    assert s.card.status == "booked"
    assert clinic.bookings_file.read_text(encoding="utf-8") == lines_before


def test_hand_off_says_handed_off_true_when_it_hands_off(clinic):
    s = to_visit_type(clinic, NEW)
    out = step(s, "hand_off", {"reason": "cancel"})
    assert out.result.get("handed_off") is True and s.card.status == "handed_off" and out.next_stage == END


def test_a_second_hand_off_does_not_claim_a_change(clinic):
    s = handed_off(clinic)
    out = step(s, "hand_off", {"reason": "cancel"})
    assert out.result.get("handed_off") is False, out.result
    assert s.card.status == "handed_off"


# ================================================================== before identification
@pytest.mark.parametrize("tool,args", [
    ("list_visit_types", {"specialty": "Dermatology"}),
    ("choose_visit_type", {"visit_type_id": SKIN_CHECK}),
    ("choose_option", {"option_id": "1"}),
    ("confirm_booking", {}),
])
def test_tools_that_need_the_caller_are_refused_before_identification(clinic, tool, args):
    s = new_call(clinic)
    msg = refused_unchanged(s, tool, args)
    assert "Identify the caller first" in msg, msg
    assert s.stage == IDENTIFY and s.card.caller is None


def test_tools_that_need_the_caller_are_refused_after_a_failed_try_too(clinic):
    s = new_call(clinic)
    step(s, "start_booking", {"full_name": "James Wilson", "returning": True, "date_of_birth": "1984-03-13"})
    msg = refused_unchanged(s, "list_visit_types", {"specialty": "Radiology"})
    assert "Identify the caller first" in msg


@pytest.mark.parametrize("tool,args", [
    ("answer_question", {"about": "location", "name": "Midtown"}),
    ("change_choice", {"days": ["Friday"]}),
    ("turn_down_doctors", {"doctor_name": "Dr. Kenji Kim"}),
])
def test_tools_that_dont_need_the_caller_work_before_identification(clinic, tool, args):
    s = new_call(clinic)
    out = step(s, tool, args)
    assert out.result["ok"] is True and out.next_stage is None and s.stage == IDENTIFY


# ================================================================== fields a tool doesn't have
EXTRA = {
    "start_booking": ({**NEW}, "doctor"),
    "list_visit_types": ({"specialty": "Dermatology"}, "name"),
    "choose_visit_type": ({"visit_type_id": SKIN_CHECK}, "visit_description"),
    "choose_option": ({"option_id": "1"}, "confirm"),
    "confirm_booking": ({}, "yes"),
    "turn_down_doctors": ({"doctor_name": "Dr. Kenji Kim"}, "name"),
    "change_choice": ({"days": ["Friday"]}, "visit_description"),
    "answer_question": ({"about": "location", "name": "Midtown"}, "detail"),
    "hand_off": ({"reason": "cancel"}, "note"),
}


def call_ready_for(clinic, tool):
    if tool == "start_booking":
        return new_call(clinic)
    if tool in ("list_visit_types", "choose_visit_type"):
        return to_visit_type(clinic, NEW)
    s = to_booking(clinic)
    if tool == "confirm_booking":
        step(s, "choose_option", {"option_id": s.card.offered_options[0].option_id})
    return s


@pytest.mark.parametrize("tool", sorted(EXTRA))
def test_every_tool_refuses_a_field_it_doesnt_have_and_names_its_fields(clinic, tool):
    args, extra = EXTRA[tool]
    s = call_ready_for(clinic, tool)
    if tool == "choose_option":
        args = {"option_id": s.card.offered_options[0].option_id}
    msg = refused_unchanged(s, tool, {**args, extra: "x"})
    assert extra in msg, msg
    for field in fields_of(tool):
        assert field in msg, (tool, field, msg)


def test_the_extra_field_check_covers_every_tool():
    assert set(EXTRA) == set(interface_tools()) == set(TOOLS)


def test_unknown_tool_name_raises_a_value_error_naming_the_tools(clinic):
    s = new_call(clinic)
    with pytest.raises(ValueError) as e:
        run_tool(s, "find_options", {})
    for name in TOOLS:
        assert name in str(e.value), (name, str(e.value))


# ================================================================== answer_question
def test_answer_question_says_ok_true_when_found(clinic):
    s = new_call(clinic)
    out = step(s, "answer_question", {"about": "visit_type", "name": "MRI - Knee"})
    assert out.result["ok"] is True


def test_answer_question_says_ok_false_when_not_found(clinic):
    s = new_call(clinic)
    before = snapshot(s)
    out = step(s, "answer_question", {"about": "doctor", "name": "Dr. Nobody Atall"})
    assert out.result["ok"] is False and snapshot(s) == before


@pytest.mark.parametrize("args", [{"about": 5, "name": "Midtown"}, {"about": "location", "name": 5},
                                  {"about": "location", "name": ["Midtown"]}, {"about": ["doctor"], "name": "x"},
                                  {"about": "weather", "name": "Midtown"}, {"about": "location"}, {"name": "Midtown"}])
def test_answer_question_refuses_values_that_arent_text(clinic, args):
    s = new_call(clinic)
    refused_unchanged(s, "answer_question", args)


# ================================================================== choose_option numbers
@pytest.mark.parametrize("as_sent", [lambda n: n, lambda n: int(n)], ids=["text", "number"])
def test_choose_option_takes_the_number_as_text_or_a_number(clinic, as_sent):
    s = to_booking(clinic)
    o = s.card.offered_options[1]
    out = step(s, "choose_option", {"option_id": as_sent(o.option_id)})
    assert out.result["ok"] is True and s.card.choices.slot == o.start


@pytest.mark.parametrize("make", [lambda n: f"Option {n}", lambda n: f"option {n}", lambda n: f"#{n}",
                                  lambda n: f"{n}.", lambda n: float(n), lambda n: True, lambda n: [n]],
                         ids=["Option 2", "option 2", "#2", "2.", "2.0", "true", "a list"])
def test_choose_option_refuses_anything_but_digits(clinic, make):
    s = to_booking(clinic)
    refused_unchanged(s, "choose_option", {"option_id": make(s.card.offered_options[0].option_id)})


# ================================================================== triage R8 and R9
def test_failed_confirm_keeps_soonest_and_the_latest_change(clinic):
    a = to_booking(clinic, SKIN_CHECK, NEW, time_of_day="afternoon", soonest=True)
    b = to_booking(clinic)
    assert step(b, "change_choice", {"time_of_day": "afternoon", "soonest": True}).result["ok"] is True
    assert b.card.preferences.latest == "time"
    oa = a.card.offered_options[0]
    ob = next((o for o in b.card.offered_options if (o.provider_id, o.start) == (oa.provider_id, oa.start)), None)
    assert ob is not None, "both calls are offered the same first time"
    step(a, "choose_option", {"option_id": oa.option_id})
    step(b, "choose_option", {"option_id": ob.option_id})
    assert step(a, "confirm_booking", {}).result["ok"] is True
    out = step(b, "confirm_booking", {})
    assert out.result["ok"] is False and b.stage == BOOKING
    assert b.card.preferences.soonest is True, "triage R8: going back to choosing keeps 'as soon as possible'"
    assert b.card.preferences.latest == "time", "triage R8: ... and the caller's latest change"
    starts = [st for *_, st in offered(b)]
    assert starts == sorted(starts)


def test_a_failed_file_write_holds_no_time(catalog, directory, tmp_path):
    folder = tmp_path / "not_a_file"
    folder.mkdir()
    clinic = make_clinic(catalog, directory, bookings_file=folder, log_dir=None)
    s = to_booking(clinic)
    o = s.card.offered_options[0]
    step(s, "choose_option", {"option_id": o.option_id})
    with pytest.raises(Exception):
        step(s, "confirm_booking", {})
    assert clinic.schedule.is_open(o.provider_id, o.location_id, 30, o.start, NOW), \
        "triage R9: a booking that wasn't saved must not hold the time"
    assert s.card.status == "in_progress"
