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
#

from dataclasses import dataclass, field
from typing import Optional

DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # ElevenLabs "Rachel"
DEFAULT_MODEL = "gpt-4o"


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
