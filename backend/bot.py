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
# Run:  python bot.py   then open http://localhost:7860/client
#

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import EndFrame, TTSSpeakFrame, UserIdleTimeoutUpdateFrame
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

from agent_builder import AgentBuilder
from call import CHECK_IN_AFTER, MAX_CALL_SECONDS, CallWatch, Clinic, Step

# Load .env next to this file, so the bot runs the same from the repo root or backend/.
load_dotenv(Path(__file__).parent / ".env", override=True)


# The agent this bot runs. Point this at any agent JSON (the Phase 2 Copilot
# would generate one and drop it here). example_flow.json is the starter agent.
AGENT_FLOW = Path(__file__).parent / "clinic_agent.json"

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

    context = LLMContext()
    context_aggregator = LLMContextAggregatorPair(
        context,
        # The user-idle timer counts silence from when the agent stops speaking (decision 64).
        user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer(), user_idle_timeout=CHECK_IN_AFTER),
    )

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            context_aggregator.user(),
            llm,
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

    # Silence, held calls and pocket dials (decision 64): the rules are in call/silence.py.
    watch = CallWatch()
    time_limit_task = None

    async def act(step: Step, event: str) -> None:
        """Say the step's sentence (it joins the conversation), then hang up or wait the next stretch."""
        session = flow_manager.state.get("session")
        if session is not None:
            session.log({"event": event, "said": step.say, "hang_up": step.hang_up})
        logger.info(f"[{event}] {step.say} | hang up: {step.hang_up}")
        if step.next_wait is not None:
            await worker.queue_frame(UserIdleTimeoutUpdateFrame(timeout=step.next_wait))
        await worker.queue_frames([TTSSpeakFrame(step.say)] + ([EndFrame()] if step.hang_up else []))

    @context_aggregator.user().event_handler("on_user_turn_idle")
    async def on_user_turn_idle(aggregator):
        step = watch.on_silence()
        if step:
            await act(step, "silence")

    @context_aggregator.user().event_handler("on_user_turn_started")
    async def on_user_turn_started(aggregator, strategy):
        wait = watch.on_caller_spoke()
        if wait is not None:
            await worker.queue_frame(UserIdleTimeoutUpdateFrame(timeout=wait))

    async def end_at_time_limit() -> None:
        await asyncio.sleep(MAX_CALL_SECONDS)
        step = watch.on_time_limit()
        if step:
            await act(step, "time_limit")

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        nonlocal time_limit_task
        session = CLINIC.new_call()
        flow_manager.state["session"] = session
        logger.info(f"Client connected — starting flow at initial node (call log: {session.log_path})")
        time_limit_task = asyncio.create_task(end_at_time_limit())
        await flow_manager.initialize(builder.build_initial_node(session))

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Client disconnected")
        if time_limit_task:
            time_limit_task.cancel()
        await worker.cancel()

    runner = WorkerRunner(handle_sigint=runner_args.handle_sigint)
    await runner.add_workers(worker)
    await runner.run()


async def bot(runner_args: RunnerArguments):
    """Entry point invoked by the Pipecat dev runner (and Pipecat Cloud)."""
    transport = await create_transport(runner_args, transport_params)
    builder = AgentBuilder.from_json(AGENT_FLOW)
    await run_bot(transport, runner_args, builder)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
