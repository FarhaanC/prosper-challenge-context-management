#
# Voice pipeline — Prosper AI Software Engineer Challenge
#
# The runnable voice agent: WebRTC transport + ElevenLabs STT/TTS + OpenAI LLM,
# driven by a Pipecat Flows node graph. This file is generic — it loads an agent
# definition (JSON) via AgentBuilder and runs it. Swapping the agent is a data
# change (edit/replace the JSON), not a code change.
#
#   clinic_agent.json  ->  AgentBuilder  ->  Pipecat Flows graph  ->  FlowManager
#
# Each call gets its own CallSession (booking card, options on offer, call log in
# call_logs/) and its own CallWatch (silence check-in and hang-up, 10-minute cap:
# decision 64). The clinic data, and the schedule with every saved booking
# (bookings.jsonl), are loaded once and shared by every call.
#
# Run:  python bot.py   then open http://localhost:7860/client (a call)
#                        or http://localhost:7860/editor (the editor, once built)
#

import os
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.elevenlabs.stt import ElevenLabsRealtimeSTTService
from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transcriptions.language import Language
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.workers.runner import WorkerRunner
from pipecat_flows import FlowManager

from agent_builder import AgentBuilder, CallWatchWiring, TokenLog
from call import CallWatch, Clinic

# Load .env next to this file, so the bot runs the same from the repo root or backend/.
load_dotenv(Path(__file__).parent / ".env", override=True)


# The agent this bot runs. Point this at any agent JSON (the Phase 2 Copilot
# would generate one and drop it here). example_flow.json is the starter agent.
AGENT_FLOW = Path(__file__).parent / "clinic_agent.json"

# The editor's built page (frontend/, `npm run build`), served at /editor.
EDITOR_FILES = Path(__file__).parent.parent / "frontend" / "dist"

# Loaded once: catalog, fake patients, and the schedule with every saved booking.
CLINIC = Clinic.load()


transport_params = {
    "webrtc": lambda: TransportParams(audio_in_enabled=True, audio_out_enabled=True),
}


async def run_bot(
    transport: BaseTransport, runner_args: RunnerArguments, builder: AgentBuilder
) -> None:
    config = builder.config
    logger.info(f"Starting '{config.name}' with {len(config.nodes)} nodes")

    # English only: left to guess, the speech-to-text heard a spoken name as Russian (first voice calls).
    stt = ElevenLabsRealtimeSTTService(
        api_key=os.environ["ELEVENLABS_API_KEY"],
        settings=ElevenLabsRealtimeSTTService.Settings(language=Language.EN),
    )
    tts = ElevenLabsTTSService(
        api_key=os.environ["ELEVENLABS_API_KEY"],
        settings=ElevenLabsTTSService.Settings(voice=config.voice_id),
    )
    # parallel_tool_calls off: one tool call per reply, so two calls can't both move the call.
    extra = {} if config.parallel_tool_calls else {"parallel_tool_calls": False}
    llm = OpenAILLMService(
        api_key=os.environ["OPENAI_API_KEY"],
        settings=OpenAILLMService.Settings(model=config.model, extra=extra),
    )

    # This call's log and state live in its session, made when the caller connects.
    def log(entry: dict) -> None:
        session = flow_manager.state.get("session")
        if session is not None:
            session.log(entry)

    def call_finished() -> bool:
        session = flow_manager.state.get("session")
        return session is not None and session.card.status != "in_progress"

    # Silence check-in, hang-up and the 10-minute cap (decision 64): rules in call/silence.py.
    watch = CallWatch()
    context = LLMContext()
    context_aggregator = LLMContextAggregatorPair(
        context,
        # Pipecat's silence timer, counted from when the agent stops speaking.
        user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer(),
                                            user_idle_timeout=watch.check_in_after),
    )

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            context_aggregator.user(),
            llm,
            TokenLog(log),  # input and output tokens per AI reply, into the call log (decision 45)
            tts,
            transport.output(),
            context_aggregator.assistant(),
        ]
    )

    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(enable_metrics=True, enable_usage_metrics=True),
        idle_timeout_secs=runner_args.pipeline_idle_timeout_secs,
    )

    flow_manager = FlowManager(
        llm=llm,
        context_aggregator=context_aggregator,
        worker=worker,
        transport=transport,
        global_functions=builder.global_functions(),
    )

    silence = CallWatchWiring(watch, context_aggregator.user(), worker, log, call_finished)

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        session = CLINIC.new_call()
        flow_manager.state["session"] = session
        logger.info(f"Client connected — starting flow at initial node (call log: {session.log_path})")
        silence.start_time_limit()
        await flow_manager.initialize(builder.build_initial_node(session))

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Client disconnected")
        await worker.cancel()

    runner = WorkerRunner(handle_sigint=runner_args.handle_sigint)
    await runner.add_workers(worker)
    try:
        await runner.run()
    finally:
        silence.stop()  # however the call ended: caller hung up, goodbye, silence or time limit


async def bot(runner_args: RunnerArguments):
    """Entry point invoked by the Pipecat dev runner (and Pipecat Cloud)."""
    transport = await create_transport(runner_args, transport_params)
    builder = AgentBuilder.from_json(AGENT_FLOW)
    await run_bot(transport, runner_args, builder)


if __name__ == "__main__":
    from fastapi.staticfiles import StaticFiles
    from pipecat.runner.run import app, main

    from editor_api import editor_routes

    # The editor (Phase 1) is served by this same program: http://localhost:7860/editor
    app.include_router(editor_routes(AGENT_FLOW, catalog=CLINIC.catalog))
    if EDITOR_FILES.exists():
        app.mount("/editor", StaticFiles(directory=EDITOR_FILES, html=True), name="editor")
    else:
        logger.warning(f"The editor isn't built yet ({EDITOR_FILES}): in frontend/, run npm install, then npm run build.")
    main()
