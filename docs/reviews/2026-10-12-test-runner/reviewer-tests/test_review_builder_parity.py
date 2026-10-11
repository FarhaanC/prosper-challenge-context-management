"""Does the typed loop (evals/agents.py OurAgent) give the AI the same thing the voice agent's
builder (agent_builder/builder.py) hands to Pipecat Flows? Pipecat isn't installed here, so the
few Pipecat names the builder imports are replaced by small stand-ins; the builder's own code
runs unchanged. Pipecat Flows 1.4.0 (reference/pipecat_flows/manager.py, _set_node) then does:
system instruction = role_message; tools = global functions + node functions; RESET replaces
the messages with task_messages; APPEND adds them.

These pass: they document what was checked and found to match.
"""

import asyncio
import enum
import json
import sys
import types
from dataclasses import dataclass, field
from datetime import datetime

import pytest


def _install_stubs():
    if "pipecat_flows" in sys.modules and getattr(sys.modules["pipecat_flows"], "_review_stub", False):
        return
    loguru = types.ModuleType("loguru")
    loguru.logger = types.SimpleNamespace(info=lambda *a, **k: None, debug=lambda *a, **k: None)
    sys.modules.setdefault("loguru", loguru)
    for name in ("pipecat", "pipecat.frames"):
        sys.modules.setdefault(name, types.ModuleType(name))
    frames = types.ModuleType("pipecat.frames.frames")

    @dataclass
    class TTSSpeakFrame:
        text: str
    frames.TTSSpeakFrame = TTSSpeakFrame
    sys.modules["pipecat.frames.frames"] = frames

    flows = types.ModuleType("pipecat_flows")
    flows._review_stub = True

    class ContextStrategy(enum.Enum):
        APPEND = "append"
        RESET = "reset"

    @dataclass
    class ContextStrategyConfig:
        strategy: ContextStrategy

    @dataclass
    class FlowsFunctionSchema:
        name: str
        description: str
        properties: dict
        required: list
        handler: object = None

    flows.ContextStrategy, flows.ContextStrategyConfig = ContextStrategy, ContextStrategyConfig
    flows.FlowsFunctionSchema, flows.FlowManager, flows.NodeConfig = FlowsFunctionSchema, object, dict
    sys.modules["pipecat_flows"] = flows


_install_stubs()


def _load_builder():
    """agent_builder/__init__.py also imports the silence and token-log wiring (more of Pipecat), so
    load only schema.py and builder.py, unchanged, under a stand-in package name."""
    import importlib.util
    from pathlib import Path

    folder = Path(AGENT_FILE).parent / "agent_builder"
    package = types.ModuleType("_review_agent_builder")
    package.__path__ = [str(folder)]
    sys.modules["_review_agent_builder"] = package
    loaded = None
    for name in ("schema", "builder"):
        spec = importlib.util.spec_from_file_location(f"_review_agent_builder.{name}", folder / f"{name}.py")
        loaded = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = loaded
        spec.loader.exec_module(loaded)
    return loaded


from evals.agents import AGENT_FILE  # noqa: E402

builder_module = _load_builder()
from call import Clinic  # noqa: E402
from clinic import Schedule  # noqa: E402
from evals.agents import AGENT_FILE, OurAgent  # noqa: E402
from evals.ai import Reply, ToolCall  # noqa: E402
from evals.budget import Usage  # noqa: E402

NOW = datetime(2026, 10, 13, 9, 0)
JAMES = {"full_name": "James Wilson", "returning": True, "date_of_birth": "1984-03-12",
         "visit_description": "knee MRI", "specialty": "Radiology", "place": "Downtown", "near": True}


class OneStepAI:
    def __init__(self):
        self.next = None
        self.requests = []

    def reply(self, messages, tools=None, one_tool_at_a_time=True):
        self.requests.append({"messages": messages, "tools": [t["function"]["name"] for t in tools or []]})
        step, self.next = self.next, None
        if step is None:
            return Reply("ok", [], Usage(1, 0, 1))
        name, args = step
        return Reply("", [ToolCall("c", name, json.dumps(args))], Usage(1, 0, 1))


def _voice_view(builder, node):
    """What Pipecat Flows would send after _set_node: (system, messages added, tool names, strategy)."""
    tools = list(builder.config.global_tools) + [f.name for f in node["functions"]]
    return (node["role_message"], [m["content"] for m in node["task_messages"]], tools,
            node["context_strategy"].strategy.value, node.get("respond_immediately", True))


@pytest.fixture
def pair(catalog, patients, tmp_path):
    builder = builder_module.AgentBuilder.from_json(AGENT_FILE)
    voice_session = Clinic(catalog, patients, Schedule(catalog)).new_call(clock=lambda: NOW)
    ai = OneStepAI()
    ours = OurAgent(ai, Clinic(catalog, patients, Schedule(catalog), bookings_file=tmp_path / "b.jsonl"), NOW)
    return builder, voice_session, ours, ai


def _voice_tool(builder, session, name, args):
    handler = builder._make_tool_function(name).handler
    return asyncio.run(handler(args, types.SimpleNamespace(state={"session": session})))


def test_ok_every_stage_move_gives_the_ai_the_same_instructions_and_tools(pair):
    builder, session, ours, ai = pair
    first = builder.build_initial_node(session)
    ours.start()
    system, task, tools, strategy, respond = _voice_view(builder, first)
    assert (system, tools, strategy, respond) == (ours.system, [t["function"]["name"] for t in ours.tools], "reset",
                                                  False)
    assert [m["content"] for m in ours.messages if m["role"] == "developer"] == task
    assert first["pre_actions"][0]["text"] == ours.messages[-1]["content"]  # the greeting, said by the code

    steps = [("start_booking", JAMES), ("choose_visit_type", {"visit_type_id": "appt_065"})]
    for name, args in steps:
        result, node = _voice_tool(builder, session, name, args)
        ai.next = (name, args)
        ours.respond("(caller)")
        request = ai.requests[-1]  # the new stage's first AI pass
        system, task, tools, strategy, respond = _voice_view(builder, node)
        assert strategy == "reset" and respond is True
        assert request["messages"][0] == {"role": "system", "content": system}
        assert [m["content"] for m in request["messages"][1:]] == task  # wiped: only the new stage's instructions
        assert request["tools"] == tools


def test_ok_the_read_back_is_said_by_the_code_and_the_ai_waits(pair):
    builder, session, ours, ai = pair
    builder.build_initial_node(session)
    ours.start()
    for name, args in [("start_booking", JAMES), ("choose_visit_type", {"visit_type_id": "appt_065"})]:
        _voice_tool(builder, session, name, args)
        ai.next = (name, args)
        ours.respond("(caller)")
    _, node = _voice_tool(builder, session, "choose_option", {"option_id": "1"})
    ai.next = ("choose_option", {"option_id": "1"})
    passes_before = len(ai.requests)
    turn = ours.respond("The first one.")
    assert len(ai.requests) == passes_before + 1  # no second pass
    assert node["respond_immediately"] is False and node["context_strategy"].strategy.value == "append"
    assert node["task_messages"] == [] and node["pre_actions"][0]["text"] == turn.said[-1]
    assert ours.messages[-1] == {"role": "assistant", "content": turn.said[-1]}
