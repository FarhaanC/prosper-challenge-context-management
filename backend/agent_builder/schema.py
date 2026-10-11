#
# Agent schema — the declarative contract the Phase 2 Copilot reads and writes.
#
# Design rule: stay as close to Pipecat Flows' own vocabulary as possible. A node
# carries Pipecat's native fields (`role_message`, `task_messages`, `pre/post_actions`)
# verbatim. What we add is data a Copilot or the editor can write, which
# `AgentBuilder` turns into the Python objects Pipecat wants:
#   - `edges`: transitions as a string `target`, not a Python closure;
#   - `tools` (per node) and `global_tools` (every node): tool NAMES from the tool
#     registry (call/tools.py). A tool's code decides whether to stay or move;
#   - `{placeholders}` in task messages, filled when the node is entered
#     (call/session.py lists them);
#   - `history`: "keep" (Pipecat's default) or "reset" (wipe the conversation on
#     every move; the new node's instructions carry what matters);
#   - `parallel_tool_calls`: false lets the AI call one tool at a time, so two
#     calls in one reply can't both try to move the call.
# Keys the format doesn't know are refused at load (shape_problems).
#

import re
from dataclasses import dataclass, field
from typing import Optional

DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # ElevenLabs "Rachel"
DEFAULT_MODEL = "gpt-4o"


class AgentFileProblems(ValueError):
    """An agent file the voice agent can't run. `problems` lists every problem, one sentence
    each, in the editor's words (stage, arrow, tool); the message lists them too."""

    def __init__(self, problems: list):
        self.problems = list(problems)
        super().__init__("The agent file has problems:\n- " + "\n- ".join(self.problems))


# An arrow becomes a tool the AI can call, and OpenAI only accepts these names.
ARROW_NAME = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


# The keys each level of an agent file may have. Anything else is refused at load, so a
# misspelt key ("tool" for "tools") is an error at start-up, not a stage that can't act.
AGENT_KEYS = {"name", "initial_node", "nodes", "persona", "voice_id", "model", "global_tools", "history",
              "parallel_tool_calls"}
NODE_KEYS = {"name", "task_messages", "role_message", "edges", "tools", "pre_actions", "post_actions", "end",
             "respond_immediately"}
EDGE_KEYS = {"function", "description", "target", "properties", "required"}


def shape_problems(d) -> list:
    """Unknown keys and values of the wrong kind, found before anything is built.
    (What the values mean, such as tool names and placeholders, is checked by AgentBuilder.)"""
    if not isinstance(d, dict):
        return ["The agent file must be a JSON object."]
    problems = [f"Unknown key '{k}' in the agent file." for k in sorted(set(d) - AGENT_KEYS)]
    for key in ("name", "initial_node"):
        if not isinstance(d.get(key), str):
            problems.append(f"'{key}' must be text.")
    for key in ("persona", "voice_id", "model", "history"):
        if key in d and not isinstance(d[key], str):
            problems.append(f"'{key}' must be text.")
    nodes = d.get("nodes")
    if not isinstance(nodes, list):
        return problems + ["The stages ('nodes') must be a list."]
    for i, n in enumerate(nodes):
        if not isinstance(n, dict):
            problems.append(f"Stage #{i} must be an object.")
            continue
        where = f"Stage '{n.get('name', f'#{i}')}'"
        problems += [f"{where}: unknown key '{k}'." for k in sorted(set(n) - NODE_KEYS)]
        if not isinstance(n.get("name"), str):
            problems.append(f"{where}: 'name' must be text.")
        if n.get("role_message") is not None and not isinstance(n["role_message"], str):
            problems.append(f"{where}: 'role_message' must be text.")
        messages = n.get("task_messages", [])
        if not (isinstance(messages, list) and all(isinstance(m, dict) and isinstance(m.get("content"), str)
                                                   for m in messages)):
            problems.append(f"{where}: 'task_messages' must be a list of messages, each with text 'content'.")
        if not isinstance(n.get("respond_immediately", True), bool):
            problems.append(f"{where}: 'respond_immediately' must be true or false.")
        for key in ("edges", "pre_actions", "post_actions"):
            if not isinstance(n.get(key, []), list):
                problems.append(f"{where}: '{key}' must be a list.")
        for j, e in enumerate(n.get("edges", []) if isinstance(n.get("edges", []), list) else []):
            if not isinstance(e, dict):
                problems.append(f"{where}: arrow #{j} must be an object.")
                continue
            problems += [f"{where}, arrow #{j}: unknown key '{k}'." for k in sorted(set(e) - EDGE_KEYS)]
            missing = [k for k in ("function", "description", "target") if not isinstance(e.get(k), str)]
            if missing:
                problems.append(f"{where}, arrow #{j}: its {', '.join(missing)} must be text.")
    return problems


@dataclass
class Edge:
    """A transition out of a node, exposed to the LLM as a callable tool."""

    function: str            # tool name the LLM calls to take this edge
    description: str         # when the model should call it
    target: str              # node to transition to (by name)
    # Fields to collect on this edge, as JSON-schema properties.
    properties: dict = field(default_factory=dict)
    required: list = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "Edge":
        return cls(
            function=d["function"],
            description=d["description"],
            target=d["target"],
            properties=d.get("properties", {}),
            required=d.get("required", []),
        )


@dataclass
class Node:
    """A single conversational state. Fields mirror Pipecat Flows' NodeConfig."""

    name: str
    task_messages: list = field(default_factory=list)   # this node's objectives
    role_message: Optional[str] = None                  # overrides the global persona
    edges: list = field(default_factory=list)           # list[Edge]; transitions out
    tools: list = field(default_factory=list)           # tool names from the registry; code decides moves
    pre_actions: list = field(default_factory=list)
    post_actions: list = field(default_factory=list)
    end: bool = False                                   # terminal -> ends the call
    respond_immediately: bool = True                    # False: the AI waits for the caller (Pipecat's own field)

    @classmethod
    def from_dict(cls, d: dict) -> "Node":
        return cls(
            name=d["name"],
            task_messages=d.get("task_messages", []),
            role_message=d.get("role_message"),
            edges=[Edge.from_dict(e) for e in d.get("edges", [])],
            tools=d.get("tools", []),
            pre_actions=d.get("pre_actions", []),
            post_actions=d.get("post_actions", []),
            end=d.get("end", False),
            respond_immediately=d.get("respond_immediately", True),
        )


@dataclass
class AgentConfig:
    """A complete agent: identity + the conversation graph."""

    name: str
    initial_node: str
    nodes: list                          # list[Node]
    persona: str = ""                    # global role_message, applied to every node
    voice_id: str = DEFAULT_VOICE_ID
    model: str = DEFAULT_MODEL
    global_tools: list = field(default_factory=list)    # tool names available in every node
    history: str = "keep"                # "keep" | "reset": what happens to the conversation on a move
    parallel_tool_calls: bool = True     # False: one tool call per AI reply

    @classmethod
    def from_dict(cls, d: dict) -> "AgentConfig":
        problems = shape_problems(d)
        if problems:
            raise AgentFileProblems(problems)
        return cls(
            name=d["name"],
            initial_node=d["initial_node"],
            nodes=[Node.from_dict(n) for n in d["nodes"]],
            persona=d.get("persona", ""),
            voice_id=d.get("voice_id", DEFAULT_VOICE_ID),
            model=d.get("model", DEFAULT_MODEL),
            global_tools=d.get("global_tools", []),
            history=d.get("history", "keep"),
            parallel_tool_calls=d.get("parallel_tool_calls", True),
        )
