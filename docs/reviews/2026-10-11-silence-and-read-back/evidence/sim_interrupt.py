"""Does an interruption during a Flows tts_say leave the ActionManager stuck?"""
import asyncio, sys
from pipecat.frames.frames import (TTSSpeakFrame, TTSStartedFrame, TTSStoppedFrame, TTSAudioRawFrame,
                                   InterruptionFrame, StartFrame, EndFrame, Frame)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineWorker, PipelineParams
from pipecat.workers.runner import WorkerRunner
from pipecat.processors.frame_processor import FrameProcessor, FrameDirection
from pipecat.transports.base_output import BaseOutputTransport
from pipecat.transports.base_transport import TransportParams
from pipecat_flows.actions import ActionManager

SR = 16000
CHUNK = int(SR * 0.02) * 2  # 20 ms of 16-bit mono

class FakeTTS(FrameProcessor):
    async def process_frame(self, frame, direction):
        await super().process_frame(frame, direction)
        if isinstance(frame, TTSSpeakFrame):
            await self.push_frame(TTSStartedFrame(context_id="c1"))
            for _ in range(100):  # 2 s of audio
                await self.push_frame(TTSAudioRawFrame(audio=b"\x10\x20" * (CHUNK // 2), sample_rate=SR, num_channels=1, context_id="c1"))
            await self.push_frame(TTSStoppedFrame(context_id="c1"))
        else:
            await self.push_frame(frame, direction)

class FakeOut(BaseOutputTransport):
    async def start(self, frame: StartFrame):
        await super().start(frame)
        await self.set_transport_ready(frame)
    async def write_audio_frame(self, frame) -> bool:
        await asyncio.sleep(0.02)
        return True

class FakeFlow:  # ActionManager only needs this to pass through
    pass

async def main(interrupt: bool):
    out = FakeOut(TransportParams(audio_out_enabled=True, audio_out_sample_rate=SR))
    worker = PipelineWorker(Pipeline([FakeTTS(), out]), params=PipelineParams(audio_out_sample_rate=SR))
    am = ActionManager(worker, FakeFlow())
    runner = WorkerRunner(handle_sigint=False)
    await runner.add_workers(worker)
    run = asyncio.create_task(runner.run())
    await asyncio.sleep(0.3)
    say = asyncio.create_task(am.execute_actions([{"type": "tts_say", "text": "To confirm: ..."}]))
    if interrupt:
        await asyncio.sleep(0.7)   # caller says "yes" part-way through
        await worker.queue_frame(InterruptionFrame())
    try:
        await asyncio.wait_for(asyncio.shield(say), timeout=5)
        print(f"interrupt={interrupt}: tts_say pre-action finished; ongoing count={am._ongoing_actions_count}")
    except asyncio.TimeoutError:
        print(f"interrupt={interrupt}: tts_say pre-action STILL WAITING after 5 s; ongoing count={am._ongoing_actions_count}")
        # A second tts_say (e.g. the caller picks another option and hears a new read-back)
        say2 = asyncio.create_task(am.execute_actions([{"type": "tts_say", "text": "To confirm again"}]))
        try:
            await asyncio.wait_for(say2, timeout=5)
            print("  second tts_say finished")
        except asyncio.TimeoutError:
            print(f"  second tts_say ALSO stuck; ongoing count={am._ongoing_actions_count}")
    await worker.cancel()
    try:
        await asyncio.wait_for(run, timeout=5)
    except Exception:
        pass

asyncio.run(main(sys.argv[1] == "1"))
