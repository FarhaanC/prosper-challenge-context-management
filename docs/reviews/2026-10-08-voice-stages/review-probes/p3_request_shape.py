"""Probe 3: build the OpenAI service exactly as bot.py does, apply the persona update that
Pipecat Flows sends on every stage move, and build the request for the end stage's context
(globals only). Shows: parallel_tool_calls survives the persona update, and the end stage
request carries tools (so OpenAI accepts parallel_tool_calls), i.e. the AI CAN call a tool there.
No network: only the request dict is built.
"""
import asyncio
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "backend"))

from pipecat.adapters.schemas.tools_schema import ToolsSchema  # noqa: E402
from pipecat.processors.aggregators.llm_context import LLMContext  # noqa: E402
from pipecat.services.openai.llm import OpenAILLMService  # noqa: E402
from pipecat.services.settings import LLMSettings  # noqa: E402

from agent_builder import AgentBuilder  # noqa: E402
from call import Clinic  # noqa: E402
from clinic import Catalog, PatientDirectory, Schedule  # noqa: E402

AGENT = Path(__file__).resolve().parents[4] / "backend" / "clinic_agent.json"
b = AgentBuilder.from_json(AGENT)
config = b.config
extra = {} if config.parallel_tool_calls else {"parallel_tool_calls": False}
llm = OpenAILLMService(api_key="sk-dummy", settings=OpenAILLMService.Settings(model=config.model, extra=extra))


async def main():
    await llm._update_settings(LLMSettings(system_instruction=config.persona))  # what Flows sends per node
    cat = Catalog.load()
    s = Clinic(cat, PatientDirectory.load(), Schedule(cat)).new_call(clock=lambda: datetime(2026, 10, 6, 9))
    s.outcome = "The caller asked to speak to a person. Tell the caller you're putting them through ..."
    end = b._make_node(b._nodes_by_name["end"], s)
    tools = [f.to_function_schema() for f in b.global_functions() + end["functions"]]
    ctx = LLMContext(messages=end["task_messages"], tools=ToolsSchema(standard_tools=tools))
    adapter = llm.get_llm_adapter()
    params = llm.build_chat_completion_params(adapter.get_llm_invocation_params(
        ctx, system_instruction=llm._settings.system_instruction, convert_developer_to_user=False))
    print("parallel_tool_calls in request:", params.get("parallel_tool_calls"))
    print("tools offered in the END stage:", [t["function"]["name"] for t in params["tools"]])
    print("end node post_actions:", end.get("post_actions"))


asyncio.run(main())
