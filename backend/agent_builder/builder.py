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
# placeholders filled from the booking card at that moment. If the tool's code
# gives a sentence to say (say_now), the code says it and the AI waits for the
# caller: no AI pass is spent repeating it (decision 66).
#
# Lines the code speaks (an agent file's "tts_say" actions, and say_now) go through
# our own "say" action, not Pipecat Flows' tts_say. Flows' tts_say waits for a
# marker to come back after the line is spoken, and if the caller talks over the
# line, the marker is thrown away and the call stays stuck: an interrupted greeting
# left stage 1 with no instructions or tools (review 2026-10-11, R2). "say" only
# queues the line, so nothing waits on it.
#

import json
from pathlib import Path
from typing import Optional, Union

from loguru import logger
from pipecat.frames.frames import TTSSpeakFrame
from pipecat_flows import ContextStrategy, ContextStrategyConfig, FlowManager, FlowsFunctionSchema, NodeConfig

from call import PLACEHOLDER, PLACEHOLDERS, TOOLS, CallSession, run_tool

from .schema import ARROW_NAME, AgentConfig, AgentFileProblems, Edge, Node

HISTORY = {"keep": ContextStrategy.APPEND, "reset": ContextStrategy.RESET}


async def say(action: dict, flow_manager: FlowManager) -> None:
    """The "say" action: queue one line for the voice (it joins the conversation) and wait for nothing."""
    await flow_manager.worker.queue_frame(TTSSpeakFrame(action["text"]))


def _spoken_by_code(actions: list) -> list:
    """An agent file's tts_say actions, said with our "say" action instead (see the top of this file)."""
    return [{"type": "say", "text": a["text"], "handler": say} if a.get("type") == "tts_say" else a
            for a in actions]


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
            raise AgentFileProblems(["The agent has no stages."])
        problems = []
        names = [n.name for n in c.nodes]
        for name in sorted({n for n in names if names.count(n) > 1}):
            problems.append(f"Two stages are called '{name}'.")
        if c.initial_node not in names:
            problems.append(f"The start stage '{c.initial_node}' doesn't exist.")
        if c.history not in HISTORY:
            problems.append(f"history must be one of {', '.join(HISTORY)}, not {c.history!r}.")
        if not isinstance(c.parallel_tool_calls, bool):
            problems.append(f"parallel_tool_calls must be true or false, not {c.parallel_tool_calls!r}.")
        problems += _tool_list_problems(c.global_tools, "The always-available tools", key="global_tools")
        problems += _placeholder_problems(c.persona, "The persona", allowed=False)
        for node in c.nodes:
            for edge in node.edges:
                if edge.target not in names:
                    problems.append(f"Arrow '{edge.function}' in stage '{node.name}' goes to '{edge.target}', "
                                    "which isn't a stage.")
            problems += _arrow_name_problems(node, c.global_tools)
            problems += _tool_list_problems(node.tools, f"Stage '{node.name}' tools")
            if _names_list(node.tools) and _names_list(c.global_tools):
                for tool in sorted(set(node.tools) & set(c.global_tools)):
                    problems.append(f"Tool '{tool}' is in stage '{node.name}' and always available; list it once.")
            problems += _placeholder_problems(node.role_message or "", f"Stage '{node.name}' role (role_message)",
                                              allowed=False)
            for message in node.task_messages:
                problems += _placeholder_problems(message.get("content", ""), f"Stage '{node.name}'")
            if c.parallel_tool_calls is False and not (node.edges or node.tools or c.global_tools):
                # OpenAI refuses the one-at-a-time setting on a request with no tools.
                problems.append(f"Stage '{node.name}' has no tools or arrows, which one tool call at a time "
                                "(parallel_tool_calls false) doesn't allow.")
        # Code-decided moves: every stage a tool can move to must exist. One sentence per missing
        # stage, naming the tools that need it, so the fix (keep that name) is clear.
        used = set(c.global_tools if _names_list(c.global_tools) else [])
        for node in c.nodes:
            used |= set(node.tools if _names_list(node.tools) else [])
        needed: dict = {}
        for tool in sorted(t for t in used if t in TOOLS):
            for stage in TOOLS[tool].moves_to:
                if stage not in names:
                    needed.setdefault(stage, []).append(tool)
        for stage, tools in sorted(needed.items()):
            problems.append(f"There's no stage called '{stage}', but the code of {', '.join(tools)} moves the call "
                            f"there: keep a stage with that name.")
        if problems:
            raise AgentFileProblems(problems)

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
            **self._role_and_functions(node),
            "task_messages": task_messages,
            "context_strategy": ContextStrategyConfig(strategy=HISTORY[self.config.history]),
        }
        if node.pre_actions:
            node_config["pre_actions"] = _spoken_by_code(node.pre_actions)
        if not node.respond_immediately:
            node_config["respond_immediately"] = False
        # Explicit post_actions win; otherwise a terminal node ends the call.
        if node.post_actions:
            node_config["post_actions"] = _spoken_by_code(node.post_actions)
        elif node.end:
            node_config["post_actions"] = [{"type": "end_conversation"}]
        return node_config

    def _say_and_wait(self, session: CallSession, text: str) -> NodeConfig:
        """Stay in the current stage, keeping its conversation, while the code says `text`.

        Pipecat Flows only lets a tool stop the AI's next pass by moving to a node, so
        this "moves" to the same stage: same tools, conversation kept (nothing new to
        read: the tool's reply is already in it), the sentence said by the code (and
        added to the conversation), and the AI waits for the caller."""
        return {
            **self._role_and_functions(self._nodes_by_name[session.stage]),
            "task_messages": [],
            "context_strategy": ContextStrategyConfig(strategy=ContextStrategy.APPEND),
            "pre_actions": [{"type": "say", "text": text, "handler": say}],
            "respond_immediately": False,
        }

    def _role_and_functions(self, node: Node) -> dict:
        """A stage's name, role and tools: the same whether the stage starts or is re-entered."""
        return {
            "name": node.name,
            "role_message": node.role_message or self.config.persona,
            "functions": [self._make_edge_function(edge) for edge in node.edges]
            + [self._make_tool_function(name) for name in node.tools],
        }

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
            if outcome.say_now:
                return outcome.result, self._say_and_wait(session, outcome.say_now)
            return outcome.result

        return FlowsFunctionSchema(
            name=tool.name,
            description=tool.description,
            properties=tool.properties,
            required=tool.required,
            handler=handler,
        )


def _names_list(value) -> bool:
    return isinstance(value, list) and all(isinstance(v, str) for v in value)


def _arrow_name_problems(node: Node, global_tools) -> list:
    """An arrow is a tool the AI calls, so its name must be one the AI service accepts, and
    can't be shared with another arrow in the stage or with a tool the stage already has."""
    problems = []
    names = [edge.function for edge in node.edges]
    taken = set(TOOLS) | set(node.tools if _names_list(node.tools) else []) | set(
        global_tools if _names_list(global_tools) else [])
    for name in names:
        if not ARROW_NAME.match(name):
            problems.append(f"Arrow '{name}' in stage '{node.name}': a name can only use letters, digits, _ and - "
                            "(no spaces), and must have 1 to 64 of them.")
        elif name in taken:
            problems.append(f"Arrow '{name}' in stage '{node.name}' has the same name as a tool; rename the arrow.")
    for name in sorted({n for n in names if names.count(n) > 1}):
        problems.append(f"Stage '{node.name}' has two arrows called '{name}'; rename one.")
    return problems


def _tool_list_problems(tools, where: str, key: str = "") -> list:
    """`key`: the file's own name for the list, said too when the whole list is the wrong kind."""
    if not _names_list(tools):
        return [f"{key} must be a list of tool names ({where.lower()})." if key else f"{where} must be a list of tool names."]
    problems = [f"{where}: '{t}' is listed twice." for t in sorted({t for t in tools if tools.count(t) > 1})]
    problems += [f"{where}: '{t}' isn't in the tool registry." for t in tools if t not in TOOLS]
    return problems


def _placeholder_problems(text: str, where: str, allowed: bool = True) -> list:
    """Anything in braces must be a known placeholder, and only task messages are filled."""
    if "{{" in (text or "") or "}}" in (text or ""):
        return [f"{where} contains doubled braces; braces are only for placeholders like {{today}}."]
    found = PLACEHOLDER.findall(text or "")
    if found and not allowed:
        return [f"{where} contains {{{found[0]}}}; placeholders only work in a stage's instructions "
                "(task messages)."]
    return [f"{where} uses unknown placeholder {{{p}}}; known: {', '.join(PLACEHOLDERS)}."
            for p in found if p not in PLACEHOLDERS]
