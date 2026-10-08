"""Round 2: what the AI is shown (spec note "What the AI is shown"; decision 50; triage R1, R13, K5).

- {today} includes the year: "Tuesday 6 October 2026 at 9 AM (clinic time, San Francisco)".
- A wrong-year date: "Tuesday 15 October 2024 is outside the booking window (6 October to
  20 October 2026)."
- "Place not recognised" notes are under "Fix first (don't read this to the caller...)".
- {outcome}: booked -> the read-back, then "Confirm the day, time and doctor in one short
  sentence (not the whole read-back again)..."; hand-offs -> "A member of staff will call
  the caller back about this..."; "putting through" is no longer used.
- The end stage's instructions end with "speak only. Don't call any tool...".
- The persona's "use a tool" rule is limited to before the goodbye (decision 50).
"""

import asyncio
import copy
import json
import re
from datetime import datetime

import pytest

from agent_builder import AgentBuilder
from clinic import PatientDirectory
from voice_reference import (AGENT_FILE, END, JAMES, KNEE_MRI, NEW, NOW, PATIENT, PATIENTS, SKIN_CHECK, interface_tools,
                             make_clinic, new_call, section, step, to_booking, to_visit_type)

AGENT = json.loads(AGENT_FILE.read_text(encoding="utf-8"))
END_NODE = next(n for n in AGENT["nodes"] if n["name"] == END)
PUTTING_THROUGH = re.compile(r"\bput(ting)?\b[^.]*\bthrough\b", re.I)


class FakeFlowManager:
    def __init__(self, session):
        self.state = {"session": session}


@pytest.fixture
def clinic(catalog, directory, tmp_path):
    return make_clinic(catalog, directory, bookings_file=tmp_path / "b.jsonl", log_dir=None)


# ================================================================== {today}
@pytest.mark.parametrize("now,expected", [
    (NOW, "Tuesday 6 October 2026 at 9 AM (clinic time, San Francisco)"),
    (datetime(2026, 10, 8, 14, 30), "Thursday 8 October 2026 at 2:30 PM (clinic time, San Francisco)"),
    (datetime(2027, 1, 4, 10, 0), "Monday 4 January 2027 at 10 AM (clinic time, San Francisco)"),
])
def test_today_includes_the_year(clinic, now, expected):
    assert new_call(clinic, now=now).fill("{today}") == expected


# ================================================================== the booking window message
WINDOW = "(6 October to 20 October 2026)"


@pytest.mark.parametrize("day,said", [
    ("2024-10-15", "Tuesday 15 October 2024"),
    ("2025-10-07", "Tuesday 7 October 2025"),
    ("2026-10-21", "Wednesday 21 October 2026"),
    ("2026-10-01", "Thursday 1 October 2026"),
])
@pytest.mark.parametrize("where", ["start_booking", "choose_visit_type", "change_choice"])
def test_a_date_outside_the_window_names_both_years(clinic, day, said, where):
    expected = f"{said} is outside the booking window {WINDOW}."
    if where == "start_booking":
        s, args = new_call(clinic), {**NEW, "days": [day]}
    elif where == "choose_visit_type":
        s, args = to_visit_type(clinic, NEW), {"visit_type_id": SKIN_CHECK, "days": [day]}
    else:
        s, args = to_booking(clinic), {"days": [day]}
    out = step(s, where, args)
    assert out.result["ok"] is False
    assert expected in (out.result.get("error") or ""), out.result


# ================================================================== "Fix first"
@pytest.mark.parametrize("place", ["Atlantis", "Gotham Heights"])
def test_place_not_recognised_goes_under_fix_first_not_tell_the_caller(clinic, place):
    s = to_booking(clinic, SKIN_CHECK, NEW, place=place)
    text = s.fill("{options}")
    fix = " ".join(section(text, "Fix first"))
    told = " ".join(section(text, "Tell the caller first"))
    assert place in fix, text
    assert place not in told, text
    heading = next(line for line in text.splitlines() if line.startswith("Fix first"))
    assert "don't read this to the caller" in heading.lower(), heading


# ================================================================== {outcome}
def book(clinic):
    s = to_booking(clinic, KNEE_MRI, JAMES)
    rb = step(s, "choose_option", {"option_id": s.card.offered_options[0].option_id}).result["read_back"]
    assert step(s, "confirm_booking", {}).result["ok"] is True
    return s, rb


def test_booked_outcome_is_the_read_back_then_a_short_confirmation(clinic):
    s, rb = book(clinic)
    text = s.fill("{outcome}")
    ask = "Confirm the day, time and doctor in one short sentence (not the whole read-back again)"
    assert rb in text and ask in text, text
    assert text.index(rb) < text.index(ask)
    assert not PUTTING_THROUGH.search(text)


@pytest.mark.parametrize("reason", ["reschedule", "cancel", "speak_to_staff"])
def test_hand_off_outcome_says_staff_will_call_back(clinic, reason):
    s = to_visit_type(clinic, NEW)
    step(s, "hand_off", {"reason": reason})
    text = s.fill("{outcome}")
    assert "A member of staff will call the caller back about this" in text, text
    assert not PUTTING_THROUGH.search(text), text


def test_same_name_and_birthday_outcome_says_staff_will_call_back(catalog, directory):
    twin = copy.deepcopy(PATIENT["James Wilson"])
    twin["id"] = "pat_099"
    c = make_clinic(catalog, directory, patients=PatientDirectory(copy.deepcopy(PATIENTS) + [twin]))
    s = new_call(c)
    step(s, "start_booking", dict(JAMES))
    text = s.fill("{outcome}")
    assert "staff will call" in text.lower() and not PUTTING_THROUGH.search(text), text


def test_hand_off_after_a_booking_keeps_the_booking_in_the_goodbye(clinic):
    # Triage K5: the reply says handed_off only when the status changed; "the goodbye covers both".
    s, rb = book(clinic)
    step(s, "hand_off", {"reason": "speak_to_staff"})
    text = s.fill("{outcome}")
    assert rb in text, "the booking was saved; the goodbye must not drop it"
    assert "staff will call" in text.lower(), text


def test_hand_off_description_says_staff_will_call_back():
    desc = interface_tools()["hand_off"][0]
    assert "call them back" in desc and not PUTTING_THROUGH.search(desc)


# ================================================================== the end stage and the persona
def test_end_stage_instructions_end_by_saying_speak_only_and_no_tools():
    text = "\n".join(m["content"] for m in END_NODE["task_messages"])
    tail = text[text.index("{outcome}") + len("{outcome}"):]
    assert "speak only. Don't call any tool" in tail, text


def test_built_end_node_carries_the_outcome_and_the_speak_only_line(clinic):
    b = AgentBuilder.from_json(AGENT_FILE)
    s = clinic.new_call(clock=lambda: NOW)
    fm = FakeFlowManager(s)
    node = b.build_initial_node(s)
    funcs = {f.name: f for f in [*node["functions"], *b.global_functions()]}
    _, node = asyncio.run(funcs["hand_off"].handler({"reason": "cancel"}, fm))
    text = "\n".join(m["content"] for m in node["task_messages"])
    assert "A member of staff will call the caller back about this" in text
    assert "speak only. Don't call any tool" in text
    assert text.index("A member of staff") < text.index("speak only")


def test_persona_limits_the_use_a_tool_rule_to_before_the_goodbye():
    sentences = re.split(r"(?<=[.!?])\s+", AGENT["persona"])
    tool_rules = [x for x in sentences if re.search(r"\buse a tool\b", x, re.I)]
    assert tool_rules, "the persona still tells the AI to move the call on with tools"
    assert all("goodbye" in x.lower() for x in tool_rules), tool_rules
