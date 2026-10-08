"""Voice stages, area 7: the agent file and the builder (decisions 19, 46, 49; the plan's
"Changes to the agent format" and "Safety setting").

- clinic_agent.json loads; per-stage tools, global tools (answer_question, change_choice,
  hand_off in every stage), placeholders filled when a stage starts.
- History is reset on every stage move (plain "reset", decision 19).
- Parallel tool calls are off (one tool call at a time).
- Load-time checks (decision 49): every tool exists, every stage a tool can move to
  exists, every {placeholder} is one the code knows; "a typo in the agent file is an error
  at start-up, not a broken call". Bad settings are refused at load.
- The Pipecat handler wrappers move with filled instructions and stay when they should.
"""

import asyncio
import copy
import json
import re

import pytest
from pipecat_flows import ContextStrategy

from agent_builder import AgentBuilder
from voice_reference import (AGENT_FILE, BOOKING, END, IDENTIFY, JAMES, KNEE_MRI, NEW, NOW, SKIN_CHECK, VISIT_TYPE,
                             interface_tools, make_clinic, option_lines, spoken)

AGENT = json.loads(AGENT_FILE.read_text(encoding="utf-8"))
NODE_TOOLS = {n["name"]: n.get("tools", []) for n in AGENT["nodes"]}
PLACEHOLDER_SHAPE = re.compile(r"\{[^{}\s\"]*\}")


class FakeFlowManager:
    def __init__(self, session):
        self.state = {"session": session}


@pytest.fixture
def clinic(catalog, directory, tmp_path):
    return make_clinic(catalog, directory, bookings_file=tmp_path / "b.jsonl", log_dir=tmp_path / "logs")


@pytest.fixture(scope="module")
def builder():
    return AgentBuilder.from_json(AGENT_FILE)


def call(fn, args, fm):
    """Run a handler; returns (result, next_node or None)."""
    out = asyncio.run(fn.handler(dict(args), fm))
    if isinstance(out, tuple):
        return out[0], out[1]
    return out, None


class Call:
    """Plays the Flows manager: keeps the current node's functions plus the globals."""

    def __init__(self, builder, clinic, now=NOW):
        self.session = clinic.new_call(clock=lambda: now)
        self.fm = FakeFlowManager(self.session)
        self.builder = builder
        self.node = builder.build_initial_node(self.session)
        self.globals = {f.name: f for f in builder.global_functions()}

    def functions(self):
        return {**self.globals, **{f.name: f for f in self.node.get("functions", [])}}

    def __call__(self, tool, args=None):
        result, nxt = call(self.functions()[tool], args or {}, self.fm)
        if nxt is not None:
            self.node = nxt
        return result, nxt

    def text(self):
        return "\n".join(m["content"] for m in self.node["task_messages"])


# ------------------------------------------------------------------ the agent file
def test_clinic_agent_loads_with_safe_settings(builder):
    c = builder.config
    assert c.history == "reset"
    assert c.parallel_tool_calls is False, "plan: parallel tool calls are turned off"
    # round 2: turn_down_doctors is now always available too (spec note "turn_down_doctors is available in every stage", decision 53)
    assert set(c.global_tools) == {"answer_question", "change_choice", "turn_down_doctors", "hand_off"}, \
        "decisions 46, 53"


def test_global_functions_are_exactly_what_the_interface_shows(builder):
    iface = interface_tools()
    got = {f.name: f for f in builder.global_functions()}
    assert set(got) == set(AGENT["global_tools"])
    for name, f in got.items():
        desc, required, _, props = iface[name]
        assert f.description == desc
        assert sorted(f.required) == sorted(required)
        assert f.properties == props


def test_initial_node(builder, clinic):
    c = Call(builder, clinic)
    n = c.node
    assert n["name"] == "identify" and c.session.stage == IDENTIFY
    assert [f.name for f in n["functions"]] == NODE_TOOLS["identify"]
    assert n["role_message"] == AGENT["persona"]
    assert "Tuesday 6 October" in c.text()
    assert not PLACEHOLDER_SHAPE.search(c.text()), c.text()


def test_every_stage_function_is_what_the_interface_shows(builder, clinic):
    iface = interface_tools()
    c = Call(builder, clinic)
    seen = {}
    for f in c.node["functions"]:
        seen[f.name] = f
    c("start_booking", dict(NEW))
    seen.update({f.name: f for f in c.node["functions"]})
    c("choose_visit_type", {"visit_type_id": SKIN_CHECK})
    seen.update({f.name: f for f in c.node["functions"]})
    # round 2: turn_down_doctors left the booking stage's own list for the global tools
    # (spec note "Smaller changes": the booking stage's own tools are choose_option and confirm_booking)
    assert set(seen) == {"start_booking", "list_visit_types", "choose_visit_type", "choose_option",
                         "confirm_booking"}
    for name, f in seen.items():
        desc, required, _, props = iface[name]
        assert (f.description, sorted(f.required), f.properties) == (desc, sorted(required), props), name


# ------------------------------------------------------------------ handlers: move or stay
def test_start_booking_handler_moves_with_filled_instructions(builder, clinic):
    c = Call(builder, clinic)
    result, nxt = c("start_booking", {**JAMES, "visit_description": "knee MRI"})
    assert result["ok"] is True
    assert nxt is not None and nxt["name"] == VISIT_TYPE and c.session.stage == VISIT_TYPE
    assert [f.name for f in nxt["functions"]] == NODE_TOOLS["visit_type"]
    t = c.text()
    assert "James Wilson" in t and "knee MRI" in t and "Radiology" in t
    assert "Allergy/Immunology" in t and "Urology" in t, "specialties pasted in"
    assert not PLACEHOLDER_SHAPE.search(t), t
    assert nxt["context_strategy"].strategy == ContextStrategy.RESET


def test_failed_start_booking_handler_stays(builder, clinic):
    c = Call(builder, clinic)
    result, nxt = c("start_booking", {"full_name": "James Wilson", "returning": True, "date_of_birth": "1999-09-09"})
    assert result["ok"] is False and nxt is None and c.session.stage == IDENTIFY


def test_change_choice_handler_in_identify_stays(builder, clinic):
    c = Call(builder, clinic)
    # round 2: new change_choice shape (spec note "change_choice has a new shape")
    result, nxt = c("change_choice", {"days": ["Thursday"]})
    assert result["ok"] is True and nxt is None and c.session.stage == IDENTIFY


def test_choose_visit_type_handler_moves_with_options_in_the_instructions(builder, clinic):
    c = Call(builder, clinic)
    c("start_booking", {**JAMES, "place": "Downtown", "near": True})
    result, nxt = c("choose_visit_type", {"visit_type_id": KNEE_MRI})
    assert result["ok"] is True and nxt["name"] == BOOKING
    assert [f.name for f in nxt["functions"]] == NODE_TOOLS["booking"]
    lines = option_lines(c.text())
    assert set(lines) == {o.option_id for o in c.session.card.offered_options}
    for o in c.session.card.offered_options:
        assert spoken(o.start) in lines[o.option_id]
    assert nxt["context_strategy"].strategy == ContextStrategy.RESET


def test_refused_choose_visit_type_handler_stays(builder, clinic):
    c = Call(builder, clinic)
    c("start_booking", dict(NEW))
    result, nxt = c("choose_visit_type", {"visit_type_id": KNEE_MRI})
    assert result["ok"] is False and nxt is None and c.session.stage == VISIT_TYPE


def test_change_in_booking_rebuilds_booking_with_fresh_options_and_reset(builder, clinic):
    c = Call(builder, clinic)
    c("start_booking", dict(NEW))
    c("choose_visit_type", {"visit_type_id": SKIN_CHECK})
    old = set(option_lines(c.text()))
    # round 2: new change_choice shape (spec note "change_choice has a new shape")
    result, nxt = c("change_choice", {"days": ["Friday"]})
    assert result["ok"] is True and nxt is not None and nxt["name"] == BOOKING
    new = option_lines(c.text())
    assert new and not (set(new) & old)
    assert all("Friday" in line for line in new.values())
    assert nxt["context_strategy"].strategy == ContextStrategy.RESET, "history reset on the rebuild too"


def test_choose_option_handler_stays(builder, clinic):
    c = Call(builder, clinic)
    c("start_booking", dict(NEW))
    c("choose_visit_type", {"visit_type_id": SKIN_CHECK})
    first = c.session.card.offered_options[0].option_id
    result, nxt = c("choose_option", {"option_id": first})
    assert result["ok"] is True and nxt is None and c.session.stage == BOOKING


def test_confirm_handler_moves_to_an_end_node_that_ends_the_call(builder, clinic):
    c = Call(builder, clinic)
    c("start_booking", dict(JAMES))
    c("choose_visit_type", {"visit_type_id": KNEE_MRI})
    rb, _ = c("choose_option", {"option_id": c.session.card.offered_options[0].option_id})
    result, nxt = c("confirm_booking", {})
    assert result["ok"] is True and nxt["name"] == END
    assert rb["read_back"] in c.text()
    assert not nxt.get("functions"), "the end stage offers no stage tools"
    assert any(a.get("type") == "end_conversation" for a in nxt.get("post_actions", [])), "the end stage ends the call"


@pytest.mark.parametrize("where", [IDENTIFY, VISIT_TYPE, BOOKING])
def test_hand_off_handler_from_every_stage(builder, clinic, where):
    c = Call(builder, clinic)
    if where != IDENTIFY:
        c("start_booking", dict(NEW))
    if where == BOOKING:
        c("choose_visit_type", {"visit_type_id": SKIN_CHECK})
    assert "hand_off" in c.functions(), "decision 46: hand_off in every stage"
    result, nxt = c("hand_off", {"reason": "speak_to_staff"})
    assert nxt["name"] == END and "staff" in c.text().lower()
    assert any(a.get("type") == "end_conversation" for a in nxt.get("post_actions", []))


def test_stage_move_is_logged_with_the_instructions_the_ai_was_given(builder, clinic):
    c = Call(builder, clinic)
    c("start_booking", dict(NEW))
    given = c.text()
    events = [json.loads(line) for line in c.session.log_path.read_text(encoding="utf-8").splitlines()]
    stages = [e for e in events if e["event"] == "stage" and e["stage"] == VISIT_TYPE]
    assert stages, events
    logged = stages[-1]["instructions"]
    logged_text = "\n".join(m["content"] if isinstance(m, dict) else str(m) for m in logged)
    assert logged_text == given


def test_history_keep_setting_does_not_reset(clinic):
    d = copy.deepcopy(AGENT)
    d["history"] = "keep"
    b = AgentBuilder.from_dict(d)
    c = Call(b, clinic)
    _, nxt = c("start_booking", dict(NEW))
    cs = nxt.get("context_strategy")
    assert cs is None or cs.strategy != ContextStrategy.RESET


# ------------------------------------------------------------------ load-time checks
def node(d, name):
    return next(n for n in d["nodes"] if n["name"] == name)


def broken(change):
    d = copy.deepcopy(AGENT)
    change(d)
    return d


BROKEN = {
    "unknown stage tool": (lambda d: node(d, "booking")["tools"].append("find_options"), "find_options"),
    "unknown global tool": (lambda d: d["global_tools"].append("teleport"), "teleport"),
    "unknown placeholder": (lambda d: node(d, "booking")["task_messages"][0].__setitem__(
        "content", node(d, "booking")["task_messages"][0]["content"] + " {weather}"), "weather"),
    "end stage missing": (lambda d: d.__setitem__("nodes", [n for n in d["nodes"] if n["name"] != "end"]), "end"),
    "booking stage missing": (lambda d: d.__setitem__("nodes", [n for n in d["nodes"] if n["name"] != "booking"]),
                              "booking"),
    "visit_type stage missing": (lambda d: d.__setitem__(
        "nodes", [n for n in d["nodes"] if n["name"] != "visit_type"]), "visit_type"),
    "bad history": (lambda d: d.__setitem__("history", "reset_with_summary"), "history"),
    "initial node missing": (lambda d: d.__setitem__("initial_node", "greeting"), "greeting"),
    "placeholder in wrong case": (lambda d: node(d, "booking")["task_messages"][0].__setitem__(
        "content", node(d, "booking")["task_messages"][0]["content"].replace("{options}", "{Options}")), "Options"),
    "placeholder with a space": (lambda d: node(d, "booking")["task_messages"][0].__setitem__(
        "content", node(d, "booking")["task_messages"][0]["content"].replace("{booking_card}", "{booking card}")),
        "booking card"),
    "parallel_tool_calls as text": (lambda d: d.__setitem__("parallel_tool_calls", "no"), "parallel_tool_calls"),
}


@pytest.mark.parametrize("label", sorted(BROKEN))
def test_broken_agent_file_is_refused_at_load_with_a_clear_message(label):
    change, named = BROKEN[label]
    with pytest.raises(ValueError) as e:
        AgentBuilder.from_dict(broken(change))
    assert named in str(e.value), f"the message should name {named!r}: {e.value}"


def test_placeholder_in_the_persona_is_filled_or_refused(clinic):
    # INTERFACE: placeholders are allowed in task messages. One in the persona must not
    # reach the AI as literal "{today}".
    d = broken(lambda d: d.__setitem__("persona", d["persona"] + " Today is {today}."))
    try:
        b = AgentBuilder.from_dict(d)
    except ValueError:
        return
    n = Call(b, clinic).node
    assert "{today}" not in n.get("role_message", ""), "persona placeholder left unfilled"


def test_parallel_tool_calls_true_is_accepted_as_a_setting():
    b = AgentBuilder.from_dict(broken(lambda d: d.__setitem__("parallel_tool_calls", True)))
    assert b.config.parallel_tool_calls is True


def test_the_shipped_file_passes_its_own_checks_unchanged():
    AgentBuilder.from_dict(copy.deepcopy(AGENT))
