"""Interrupt the greeting (tts_say pre-action, respond_immediately False): are the stage's instructions and tools sent?"""
import asyncio, sys
from pipecat.frames.frames import InterruptionFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineWorker, PipelineParams
from pipecat.workers.runner import WorkerRunner
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.base_transport import TransportParams
from pipecat_flows import FlowManager, FlowsFunctionSchema
from sim_interrupt import FakeTTS, FakeOut, SR

async def noop(args, fm):
    return {"ok": True}

async def main(interrupt):
    ctx = LLMContext()
    pair = LLMContextAggregatorPair(ctx)
    out = FakeOut(TransportParams(audio_out_enabled=True, audio_out_sample_rate=SR))
    worker = PipelineWorker(Pipeline([pair.user(), FakeTTS(), out, pair.assistant()]),
                            params=PipelineParams(audio_out_sample_rate=SR))
    llm = OpenAILLMService(api_key="not-used")
    fm = FlowManager(llm=llm, context_aggregator=pair, worker=worker)
    runner = WorkerRunner(handle_sigint=False)
    await runner.add_workers(worker)
    run = asyncio.create_task(runner.run())
    await asyncio.sleep(0.3)
    node = {"name": "identify", "role_message": "PERSONA",
            "task_messages": [{"role": "developer", "content": "IDENTIFY INSTRUCTIONS"}],
            "functions": [FlowsFunctionSchema(name="start_booking", description="d", properties={}, required=[], handler=noop)],
            "pre_actions": [{"type": "tts_say", "text": "Hello, you've reached the clinics."}],
            "respond_immediately": False}
    init = asyncio.create_task(fm.initialize(node))
    if interrupt:
        await asyncio.sleep(0.7)
        await worker.queue_frame(InterruptionFrame())
    await asyncio.sleep(4)
    print(f"interrupt={interrupt}: initialize done={init.done()} current_node={fm.current_node}")
    print("  context messages:", [m.get("content") for m in ctx.get_messages()])
    print("  tools:", ctx.tools if not hasattr(ctx.tools, 'standard_tools') else [t.name for t in ctx.tools.standard_tools])
    await worker.cancel()
    try: await asyncio.wait_for(run, timeout=5)
    except Exception: pass

asyncio.run(main(sys.argv[1] == "1"))
