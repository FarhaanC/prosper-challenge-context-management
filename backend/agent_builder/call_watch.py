#
# Connects one call's CallWatch (call/silence.py, decision 64) to Pipecat.
#
# Pipecat 1.4's user aggregator has a silence timer ("user idle"): it starts when
# the agent stops speaking, and stops when either side starts speaking or a tool
# runs. We listen to it, and to the end of each caller turn:
#   - silence      -> CallWatch decides: "Are you still there?" (then a shorter
#                     wait) or the goodbye and hang-up;
#   - caller words -> the next wait is the full one again;
#   - a turn with no words (noise) -> no reply will come, so the agent won't stop
#                     speaking and Pipecat would never restart the timer. We restart
#                     it ourselves (review 2026-10-11, R1).
#   - a turn with no words that cut off the agent's answer -> the caller's last
#                     words are still unanswered, so we ask the AI to answer them
#                     (decision 81, found on the 22:50 call of Sun 11).
# caller_turn_rules() says what counts as the caller starting to speak (decision 81).
# The 10-minute cap is a separate timer, stopped when the call ends however it ends.
#

import asyncio
from typing import Callable, Optional

from loguru import logger
from pipecat.frames.frames import (
    BotStoppedSpeakingFrame,
    EndFrame,
    LLMRunFrame,
    TTSSpeakFrame,
    UserIdleTimeoutUpdateFrame,
)
from pipecat.turns.user_start import TranscriptionUserTurnStartStrategy, VADUserTurnStartStrategy
from pipecat.turns.user_turn_strategies import UserTurnStrategies

from call import CallWatch, Step


def caller_turn_rules() -> UserTurnStrategies:
    """What counts as the caller starting to speak (decision 81).

    Pipecat's default listens to the voice detector and to speech-to-text, including its
    rough drafts. A rough draft can arrive a moment after the final text of the caller's
    sentence; Pipecat then thinks the caller has started speaking again and cancels the
    agent's answer. So: the voice detector, plus final text only (for speech too soft for
    the detector). When the turn ends is unchanged (Pipecat's default)."""
    return UserTurnStrategies(
        start=[VADUserTurnStartStrategy(), TranscriptionUserTurnStartStrategy(use_interim=False)])


def _unanswered(aggregator) -> bool:
    """True if the last thing in the conversation is the caller's words (no answer yet)."""
    context = getattr(aggregator, "context", None)
    messages = context.get_messages() if context is not None else []
    last = messages[-1] if messages else None
    return isinstance(last, dict) and last.get("role") == "user"


class CallWatchWiring:
    def __init__(self, watch: CallWatch, user_aggregator, worker, log: Callable[[dict], None],
                 call_finished: Callable[[], bool]):
        """user_aggregator: the call's LLMUserAggregator, made with user_idle_timeout=watch.check_in_after.
        log: writes one line to the call log. call_finished: true once the call is booked or handed off."""
        self.watch = watch
        self._worker = worker
        self._log = log
        self._call_finished = call_finished
        self._time_limit_task: Optional[asyncio.Task] = None
        user_aggregator.add_event_handler("on_user_turn_idle", self._on_silence)
        user_aggregator.add_event_handler("on_user_turn_stopped", self._on_turn_stopped)

    # ---- silence -----------------------------------------------------------
    async def _on_silence(self, aggregator) -> None:
        step = self.watch.on_silence()
        if step:
            await self._act(step, "silence")

    async def _on_turn_stopped(self, aggregator, strategy, message) -> None:
        if (message.content or "").strip():
            wait = self.watch.on_caller_spoke()
            if wait is not None:
                await self._worker.queue_frame(UserIdleTimeoutUpdateFrame(timeout=wait))
        elif _unanswered(aggregator):
            # No words, but this "turn" cancelled the agent's answer to the caller's last
            # words (a late speech-to-text draft, or a noise, just after they spoke). Nothing
            # else will ask the AI again, so the caller would hear silence until the
            # check-in (decision 81).
            self._log({"event": "reply_retried"})
            logger.info("[reply_retried] the answer to the caller's last words was cut off; asking again")
            await self._worker.queue_frame(LLMRunFrame())
        else:
            # No words, so the AI won't reply. Start Pipecat's own silence timer as if the
            # agent had just stopped speaking, so the agent speaking, the caller speaking
            # and tool calls still cancel it. (The timer belongs to the aggregator; Pipecat
            # 1.4 offers no public way to restart it.)
            await aggregator._user_idle_controller.process_frame(BotStoppedSpeakingFrame())

    # ---- the 10-minute cap -------------------------------------------------
    def start_time_limit(self) -> None:
        self._time_limit_task = asyncio.create_task(self._time_limit())

    async def _time_limit(self) -> None:
        await asyncio.sleep(self.watch.max_call_seconds)
        step = self.watch.on_time_limit(call_finished=self._call_finished())
        if step:
            await self._act(step, "time_limit")

    def stop(self) -> None:
        """The call is over: the cap must not fire into a finished call's log."""
        if self._time_limit_task:
            self._time_limit_task.cancel()
            self._time_limit_task = None

    # ---- saying it ---------------------------------------------------------
    async def _act(self, step: Step, event: str) -> None:
        """Say the step's sentence (it joins the conversation), then hang up or wait the next stretch."""
        self._log({"event": event, "said": step.say, "hang_up": step.hang_up})
        logger.info(f"[{event}] {step.say} | hang up: {step.hang_up}")
        if step.next_wait is not None:
            await self._worker.queue_frame(UserIdleTimeoutUpdateFrame(timeout=step.next_wait))
        await self._worker.queue_frames([TTSSpeakFrame(step.say)] + ([EndFrame()] if step.hang_up else []))
