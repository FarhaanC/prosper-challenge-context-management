#
# Token counts per AI reply, for the call log (decision 45) and the editor's inspector.
#
# Pipecat sends a usage note (a MetricsFrame) down the pipeline right after each AI
# reply, when usage metrics are on (bot.py turns them on). This step sits right
# after the AI service, writes one call-log line per note, and passes every frame on.
#

from typing import Callable

from pipecat.frames.frames import Frame, MetricsFrame
from pipecat.metrics.metrics import LLMUsageMetricsData
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor


class TokenLog(FrameProcessor):
    def __init__(self, log: Callable[[dict], None]):
        super().__init__()
        self._log = log

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, MetricsFrame):
            for data in frame.data:
                if isinstance(data, LLMUsageMetricsData):
                    usage = data.value
                    self._log({"event": "ai_turn", "input_tokens": usage.prompt_tokens,
                               "output_tokens": usage.completion_tokens,
                               "cached_input_tokens": usage.cache_read_input_tokens or 0})
        await self.push_frame(frame, direction)
