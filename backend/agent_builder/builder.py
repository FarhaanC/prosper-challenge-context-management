#
# AgentBuilder — loads a declarative agent (JSON / dict) and compiles its node
# graph into Pipecat Flows objects.
#
#   JSON  ->  AgentConfig (validated)  ->  Pipecat Flows NodeConfig graph
#
# This is the seam between "agent as data" (what the Phase 2 Copilot produces)
# and "agent as a running conversation" (what bot.py executes). Keeping the
# compile + validation here means bot.py never touches the graph internals.
#
# Tools (call/tools.py) are plain Python. Here each one is wrapped for Pipecat:
# the wrapper runs the tool on this call's session (kept in flow_manager.state),
# and if the tool's code says "move to stage X", builds node X with its
# placeholders filled from the booking card at that moment.
#

import json
from pathlib import Path
from typing import Optional, Union

from loguru import logger
from pipecat_flows import ContextStrategy, ContextStrategyConfig, FlowManager, FlowsFunctionSchema, NodeConfig

from call import PLACEHOLDER, PLACEHOLDERS, TOOLS, CallSession, run_tool

from .schema import AgentConfig, Edge, Node

HISTORY = {"keep": ContextStrategy.APPEND, "reset": ContextStrategy.RESET}


class AgentBuilder:
    """Builds a runnable Pipecat Flows graph from a declarative AgentConfig."""

    def __init__(self, config: AgentConfig):
        self.config = config
        self._nodes_by_name = {n.name: n for n in config.nodes}
        self._validate()

    # ---- loading -----------------------------------------------------------
    @classmethod
    def from_dict(cls, data: dict) -> "AgentBuilder":
        return cls(AgentConfig.from_dict(data))

    @classmethod
    def from_json(cls, path: Union[str, Path]) -> "AgentBuilder":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(data)

    # ---- validation --------------------------------------------------------
    def _validate(self) -> None:
        """Every problem in the agent file, listed at once, at start-up rather than mid-call."""
        c = self.config
        if not c.nodes:
            raise ValueError("Agent has no nodes.")
        problems = []
        names = [n.name for n in c.nodes]
        for name in sorted({n for n in names if names.count(n) > 1}):
            problems.append(f"Two nodes are called '{name}'.")
        if c.initial_node not in names:
            problems.append(f"initial_node '{c.initial_node}' is not a defined node.")
        if c.history not in HISTORY:
            problems.append(f"history must be one of {', '.join(HISTORY)}, not {c.history!r}.")
        if not isinstance(c.parallel_tool_calls, bool):
            problems.append(f"parallel_tool_calls must be true or false, not {c.parallel_tool_calls!r}.")
        problems += _tool_list_problems(c.global_tools, "global_tools")
        problems += _placeholder_problems(c.persona, "The persona", allowed=False)
        for node in c.nodes:
            for edge in node.edges:
                if edge.target not in names:
                    problems.append(f"Edge '{edge.function}' in node '{node.name}' targets unknown node "
                                    f"'{edge.target}'.")
            problems += _tool_list_problems(node.tools, f"Node '{node.name}' tools")
            if isinstance(node.tools, list) and isinstance(c.global_tools, list):
                for tool in sorted(set(node.tools) & set(c.global_tools)):
                    problems.append(f"Tool '{tool}' is in node '{node.name}' and in global_tools; list it once.")
            problems += _placeholder_problems(node.role_message or "", f"Node '{node.name}' role_message",
                                              allowed=False)
            for message in node.task_messages:
                problems += _placeholder_problems(message.get("content", ""), f"Node '{node.name}'")
            if c.parallel_tool_calls is False and not (node.edges or node.tools or c.global_tools):
                # OpenAI refuses the one-at-a-time setting on a request with no tools.
                problems.append(f"Node '{node.name}' has no tools, which parallel_tool_calls false doesn't allow.")
        # Code-decided moves: every stage a tool can move to must exist.
        used = set(c.global_tools if isinstance(c.global_tools, list) else [])
        for node in c.nodes:
            used |= set(node.tools if isinstance(node.tools, list) else [])
        for tool in sorted(t for t in used if t in TOOLS):
            for stage in TOOLS[tool].moves_to:
                if stage not in names:
                    problems.append(f"Tool '{tool}' can move to stage '{stage}', which isn't a node.")
        if problems:
            raise ValueError("The agent file has problems:\n- " + "\n- ".join(problems))

    # ---- compilation -------------------------------------------------------
    def build_initial_node(self, session: Optional[CallSession] = None) -> NodeConfig:
        """Return the entry NodeConfig; downstream nodes are built lazily on transition.
        An agent with tools or placeholders needs this call's session."""
        return self._make_node(self._nodes_by_name[self.config.initial_node], session)

    def global_functions(self) -> list:
        """The always-available tools, for FlowManager(global_functions=...)."""
        return [self._make_tool_function(name) for name in self.config.global_tools]

    def _make_node(self, node: Node, session: Optional[CallSession]) -> NodeConfig:
        task_messages = node.task_messages
        if session is not None:
            task_messages = [{**m, "content": session.fill(m.get("content", ""))} for m in node.task_messages]
            session.enter_stage(node.name, [m["content"] for m in task_messages])
        node_config: NodeConfig = {
            "name": node.name,
            "role_message": node.role_message or self.config.persona,
            "task_messages": task_messages,
            "functions": [self._make_edge_function(edge) for edge in node.edges]
            + [self._make_tool_function(name) for name in node.tools],
            "context_strategy": ContextStrategyConfig(strategy=HISTORY[self.config.history]),
        }
        if node.pre_actions:
            node_config["pre_actions"] = node.pre_actions
        # Explicit post_actions win; otherwise a terminal node ends the call.
        if node.post_actions:
            node_config["post_actions"] = node.post_actions
        elif node.end:
            node_config["post_actions"] = [{"type": "end_conversation"}]
        return node_config

    def _make_edge_function(self, edge: Edge) -> FlowsFunctionSchema:
        async def handler(args: dict, flow_manager: FlowManager):
            # Persist what the caller gave us so later nodes can use it.
            flow_manager.state.update(args)
            logger.info(f"[{edge.function}] -> {edge.target} | collected: {args}")
            next_node = self._make_node(self._nodes_by_name[edge.target], flow_manager.state.get("session"))
            return {"status": "success", **args}, next_node

        return FlowsFunctionSchema(
            name=edge.function,
            description=edge.description,
            properties=edge.properties,
            required=edge.required,
            handler=handler,
        )

    def _make_tool_function(self, name: str) -> FlowsFunctionSchema:
        tool = TOOLS[name]

        async def handler(args: dict, flow_manager: FlowManager):
            session = flow_manager.state["session"]
            outcome = run_tool(session, name, args)
            logger.info(f"[{name}] {args} -> {outcome.result} | next stage: {outcome.next_stage or 'stay'}")
            if outcome.next_stage:
                return outcome.result, self._make_node(self._nodes_by_name[outcome.next_stage], session)
            return outcome.result

        return FlowsFunctionSchema(
            name=tool.name,
            description=tool.description,
            properties=tool.properties,
            required=tool.required,
            handler=handler,
        )


def _tool_list_problems(tools, where: str) -> list:
    if not (isinstance(tools, list) and all(isinstance(t, str) for t in tools)):
        return [f"{where} must be a list of tool names."]
    problems = [f"{where}: '{t}' is listed twice." for t in sorted({t for t in tools if tools.count(t) > 1})]
    problems += [f"{where}: '{t}' isn't in the tool registry." for t in tools if t not in TOOLS]
    return problems


def _placeholder_problems(text: str, where: str, allowed: bool = True) -> list:
    """Anything in braces must be a known placeholder, and only task messages are filled."""
    if "{{" in (text or "") or "}}" in (text or ""):
        return [f"{where} contains doubled braces; braces are only for placeholders like {{today}}."]
    found = PLACEHOLDER.findall(text or "")
    if found and not allowed:
        return [f"{where} contains {{{found[0]}}}; placeholders only work in task messages."]
    return [f"{where} uses unknown placeholder {{{p}}}; known: {', '.join(PLACEHOLDERS)}."
            for p in found if p not in PLACEHOLDERS]
