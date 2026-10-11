import asyncio
from pipecat.frames.frames import BotStoppedSpeakingFrame, UserIdleTimeoutUpdateFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineWorker
from pipecat.workers.runner import WorkerRunner
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair, LLMUserAggregatorParams
from pipecat.processors.frame_processor import FrameProcessor

class PassThrough(FrameProcessor):  # stands in for transport.input and the STT
    async def process_frame(self, frame, direction):
        await super().process_frame(frame, direction)
        await self.push_frame(frame, direction)

async def main():
    pair = LLMContextAggregatorPair(LLMContext(), user_params=LLMUserAggregatorParams(user_idle_timeout=0.2))
    worker = PipelineWorker(Pipeline([PassThrough(), PassThrough(), pair.user()]))
    fired = []
    @pair.user().event_handler("on_user_turn_idle")
    async def idle(agg):
        fired.append(round(asyncio.get_running_loop().time() - t0, 2))
    runner = WorkerRunner(handle_sigint=False); await runner.add_workers(worker)
    run = asyncio.create_task(runner.run()); await asyncio.sleep(0.3)
    t0 = asyncio.get_running_loop().time()
    await worker.queue_frame(UserIdleTimeoutUpdateFrame(timeout=0.6))
    await worker.queue_frame(BotStoppedSpeakingFrame())
    await asyncio.sleep(1.2)
    print("idle fired at", fired, "(0.6 expected if the update reached the aggregator, 0.2 if not)")
    await worker.cancel()
    try: await asyncio.wait_for(run, 5)
    except Exception: pass
asyncio.run(main())
