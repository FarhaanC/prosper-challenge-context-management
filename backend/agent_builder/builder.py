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
        names = set(self._nodes_by_name)
        if not names:
            raise ValueError("Agent has no nodes.")
        problems = []
        if self.config.initial_node not in names:
            problems.append(f"initial_node '{self.config.initial_node}' is not a defined node.")
        if self.config.history not in HISTORY:
            problems.append(f"history must be one of {', '.join(HISTORY)}, not '{self.config.history}'.")
        for tool in self.config.global_tools:
            if tool not in TOOLS:
                problems.append(f"Global tool '{tool}' isn't in the tool registry.")
        for node in self.config.nodes:
            for edge in node.edges:
                if edge.target not in names:
                    problems.append(f"Edge '{edge.function}' in node '{node.name}' targets unknown node "
                                    f"'{edge.target}'.")
            for tool in node.tools:
                if tool not in TOOLS:
                    problems.append(f"Tool '{tool}' in node '{node.name}' isn't in the tool registry.")
            for message in node.task_messages:
                for placeholder in PLACEHOLDER.findall(message.get("content", "")):
                    if placeholder not in PLACEHOLDERS:
                        problems.append(f"Node '{node.name}' uses unknown placeholder {{{placeholder}}}; "
                                        f"known: {', '.join(PLACEHOLDERS)}.")
            if not self.config.parallel_tool_calls and not (node.edges or node.tools or self.config.global_tools):
                # OpenAI refuses the one-at-a-time setting on a request with no tools.
                problems.append(f"Node '{node.name}' has no tools, which parallel_tool_calls false doesn't allow.")
        # Code-decided moves: every stage a tool can move to must exist.
        for tool in sorted(set(self.config.global_tools).union(*(n.tools for n in self.config.nodes))):
            for stage in TOOLS[tool].moves_to if tool in TOOLS else ():
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
