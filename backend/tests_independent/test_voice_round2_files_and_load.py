"""Round 2: the bookings file and the agent file's load-time checks (spec note "Smaller
changes"; triage R6, R11, T9, T10, K2, K3, K4, K7).

Bookings file:
- booked_at is the call's clinic time, to the minute (never the computer's own clock).
- Damaged-line messages name the problem: "missing start", "unknown doctor id ...",
  "isn't a date and time", "isn't a number of minutes", "not a JSON record".

Agent file, refused at load with a ValueError:
- parallel_tool_calls that isn't true or false;
- global_tools / tools that aren't lists of names, with repeats, or a tool both in a stage
  and global;
- two stages with the same name;
- anything in braces that isn't a known placeholder;
- a placeholder in the persona or a role message.
The starter agent (example_flow.json) must keep loading unchanged (triage K2). Whether a
change moves the call depends on the card, not on a stage's name (triage R6).
"""

import asyncio
import copy
import json
import os
import time
from datetime import datetime

import pytest

from agent_builder import AgentBuilder
from call import BookingsFileError, read_bookings
from voice_reference import AGENT_FILE, BACKEND, JAMES, KNEE_MRI, NEW, NOW, make_clinic, new_call, step, to_booking

AGENT = json.loads(AGENT_FILE.read_text(encoding="utf-8"))


# ================================================================== booked_at
def book_with_clock(catalog, directory, path, now):
    clinic = make_clinic(catalog, directory, bookings_file=path)
    s = new_call(clinic, now=now)
    step(s, "start_booking", dict(JAMES))
    step(s, "choose_visit_type", {"visit_type_id": KNEE_MRI})
    step(s, "choose_option", {"option_id": s.card.offered_options[0].option_id})
    assert step(s, "confirm_booking", {}).result["ok"] is True
    return json.loads(path.read_text(encoding="utf-8").splitlines()[0])


@pytest.mark.parametrize("now", [datetime(2026, 10, 6, 9, 0, 37, 123456), datetime(2026, 10, 7, 15, 59, 59)])
def test_booked_at_is_the_call_clock_to_the_minute(catalog, directory, tmp_path, now):
    d = book_with_clock(catalog, directory, tmp_path / "b.jsonl", now)
    got = datetime.fromisoformat(d["booked_at"])
    assert got == now.replace(second=0, microsecond=0), d["booked_at"]


@pytest.fixture
def computer_in_dubai(monkeypatch):
    if not hasattr(time, "tzset"):
        pytest.skip("can't change the computer's time zone here")
    monkeypatch.setenv("TZ", "Asia/Dubai")
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


def test_booked_at_ignores_the_computers_time_zone(catalog, directory, tmp_path, computer_in_dubai):
    assert os.environ["TZ"] == "Asia/Dubai"
    d = book_with_clock(catalog, directory, tmp_path / "b.jsonl", NOW)
    assert datetime.fromisoformat(d["booked_at"]) == NOW, d["booked_at"]


# ================================================================== damaged-line messages
GOOD = {"booked_at": "2026-10-06T09:00:00", "caller": "James Wilson", "patient_id": "pat_001",
        "new_patient": False, "visit_type_id": "appt_065", "visit_type": "MRI - Knee",
        "provider_id": "prov_014", "provider": "Dr. Linda Ramirez", "location_id": "loc_004",
        "location": "Downtown Health Center", "start": "2026-10-07T09:30:00", "duration_min": 45,
        "read_back": "MRI - Knee with Dr. Linda Ramirez ..."}


def without(key):
    return {k: v for k, v in GOOD.items() if k != key}


DAMAGED = {
    "no start": (json.dumps(without("start")), ["missing start"]),
    "unknown doctor": (json.dumps({**GOOD, "provider_id": "prov_999"}), ["unknown doctor id", "prov_999"]),
    "start not a date": (json.dumps({**GOOD, "start": "tomorrow"}), ["isn't a date and time"]),
    "duration as words": (json.dumps({**GOOD, "duration_min": "forty-five"}), ["isn't a number of minutes"]),
    "a list": ("[1, 2]", ["not a JSON record"]),
    "a number": ("42", ["not a JSON record"]),
}


@pytest.mark.parametrize("label", sorted(DAMAGED))
def test_damaged_line_message_names_the_problem(catalog, tmp_path, label):
    line, words = DAMAGED[label]
    f = tmp_path / "b.jsonl"
    f.write_text(json.dumps(GOOD) + "\n" + line + "\n", encoding="utf-8")
    with pytest.raises(BookingsFileError) as e:
        read_bookings(f, catalog)
    msg = str(e.value)
    assert "line 2" in msg, msg
    for w in words:
        assert w in msg, (w, msg)
    assert "Traceback" not in msg and "KeyError" not in msg and "JSONDecodeError" not in msg, msg


def test_missing_doctor_id_is_named(catalog, tmp_path):
    f = tmp_path / "b.jsonl"
    f.write_text(json.dumps(without("provider_id")) + "\n", encoding="utf-8")
    with pytest.raises(BookingsFileError) as e:
        read_bookings(f, catalog)
    assert "line 1" in str(e.value) and "missing" in str(e.value) and "provider_id" in str(e.value), str(e.value)


# ================================================================== load-time checks
def node(d, name):
    return next(n for n in d["nodes"] if n["name"] == name)


def edited(change):
    d = copy.deepcopy(AGENT)
    change(d)
    return d


def add_to_task(name, extra):
    def change(d):
        m = node(d, name)["task_messages"][0]
        m["content"] += extra
    return change


BROKEN = {
    "parallel_tool_calls 1": (lambda d: d.__setitem__("parallel_tool_calls", 1), ["parallel_tool_calls"]),
    "parallel_tool_calls null": (lambda d: d.__setitem__("parallel_tool_calls", None), ["parallel_tool_calls"]),
    "parallel_tool_calls 'false'": (lambda d: d.__setitem__("parallel_tool_calls", "false"), ["parallel_tool_calls"]),
    "global_tools as text": (lambda d: d.__setitem__("global_tools", "answer_question"),
                             ["global_tools must be a list of tool names"]),
    "global_tools with a number": (lambda d: d["global_tools"].append(5), ["global_tools"]),
    "global tool twice": (lambda d: d["global_tools"].append("hand_off"), ["hand_off"]),
    "stage tools as text": (lambda d: node(d, "booking").__setitem__("tools", "choose_option"), ["tools"]),
    "stage tool twice": (lambda d: node(d, "booking")["tools"].append("choose_option"), ["choose_option"]),
    "tool in a stage and global": (lambda d: node(d, "booking")["tools"].append("hand_off"), ["hand_off"]),
    "two stages share a name": (lambda d: d["nodes"].append(copy.deepcopy(node(d, "booking"))), ["booking"]),
    "placeholder in wrong case": (add_to_task("booking", " {Options}"), ["Options"]),
    "placeholder with spaces inside": (add_to_task("booking", " { options }"), ["options"]),
    "placeholder with a dash": (add_to_task("visit_type", " {visit-types}"), ["visit-types"]),
    "format spec": (add_to_task("booking", " {options!r}"), ["options!r"]),
    "a number in braces": (add_to_task("identify", " {1}"), ["1"]),
    "json-like braces": (add_to_task("booking", ' If you see {ok: false}, fix it.'), ["ok: false"]),
    "two placeholders, one unknown": (add_to_task("identify", " {today}{weather}"), ["weather"]),
    "placeholder in the persona": (lambda d: d.__setitem__("persona", d["persona"] + " Now: {today}."),
                                   ["persona", "today"]),
    "unknown braces in the persona": (lambda d: d.__setitem__("persona", d["persona"] + " {weather}"),
                                      ["persona"]),
    # A stage's own role message is the node field "role_message" (found by trying the format;
    # INTERFACE.md doesn't name it).
    "placeholder in a role message": (lambda d: node(d, "identify").__setitem__("role_message", "It is {today}."),
                                      ["today"]),
}


@pytest.mark.parametrize("label", sorted(BROKEN))
def test_broken_agent_file_is_refused_at_load_naming_the_problem(label):
    change, named = BROKEN[label]
    with pytest.raises(ValueError) as e:
        AgentBuilder.from_dict(edited(change))
    for word in named:
        assert word in str(e.value), (word, str(e.value))


def test_the_starter_agent_still_loads_unchanged():
    AgentBuilder.from_json(BACKEND / "example_flow.json")


def test_global_and_booking_tools_are_as_the_spec_says():
    b = AgentBuilder.from_json(AGENT_FILE)
    assert [f.name for f in b.global_functions()] == ["answer_question", "change_choice", "turn_down_doctors",
                                                       "hand_off"]
    assert node(AGENT, "booking")["tools"] == ["choose_option", "confirm_booking"]


# ================================================================== a renamed first stage (triage R6)
class FM:
    def __init__(self, session):
        self.state = {"session": session}


def test_a_renamed_first_stage_still_cant_skip_identification(clinic_factory):
    d = edited(lambda d: (node(d, "identify").__setitem__("name", "greeting"), d.__setitem__("initial_node",
                                                                                            "greeting")))
    b = AgentBuilder.from_dict(d)
    s = clinic_factory().new_call(clock=lambda: NOW)
    fm = FM(s)
    first = b.build_initial_node(s)
    funcs = {f.name: f for f in [*first["functions"], *b.global_functions()]}
    for args in ({"days": ["Friday"]}, {"visit_type": "knee MRI"}, {"doctor_name": "Dr. Kenji Kim", "place": "Midtown"}):
        out = asyncio.run(funcs["change_choice"].handler(dict(args), fm))
        result, nxt = out if isinstance(out, tuple) else (out, None)
        assert result["ok"] is True and nxt is None, (args, result, nxt)
        assert s.stage == "greeting" and s.card.caller is None
    out = asyncio.run(funcs["turn_down_doctors"].handler({"doctor_name": "Dr. Kenji Kim"}, fm))
    result, nxt = out if isinstance(out, tuple) else (out, None)
    assert result["ok"] is True and nxt is None and s.stage == "greeting"


@pytest.fixture
def clinic_factory(catalog, directory):
    return lambda: make_clinic(catalog, directory)


def test_nothing_moves_a_change_on_before_identification_through_run_tool(catalog, directory):
    s = make_clinic(catalog, directory).new_call(clock=lambda: NOW)
    s.enter_stage("greeting", [])
    out = step(s, "change_choice", {"days": ["Friday"]})
    assert out.result["ok"] is True and out.next_stage is None and s.stage == "greeting"
    # And once identified, a change still records in stage 2.
    step(s, "start_booking", dict(NEW))
    assert step(s, "change_choice", {"days": ["Monday"]}).next_stage is None
    s2 = to_booking(make_clinic(catalog, directory))
    assert step(s2, "change_choice", {"days": ["Monday"]}).next_stage == "booking"
