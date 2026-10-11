"""Builder tests for decision 81: a late speech-to-text draft must not leave the caller in silence.

Found on Farhaan's 22:50 call (Sun 11): the caller said "Yes, that is it."; the AI started
its answer; 20 ms later a rough draft from speech-to-text arrived, Pipecat took it as the
caller speaking again and cancelled the answer. The draft never became words, so the
"turn" ended empty after 5 s, nothing asked the AI again, and the caller heard 25 s of
silence until "Are you still there?".

Two fixes, two sets of tests:
  1. caller_turn_rules(): a rough draft no longer counts as the caller starting to speak
     (Pipecat's real turn controller, with its default rules as the "before").
  2. the safety net: an empty turn that leaves the caller's words unanswered asks the AI
     again; an empty turn after the agent has answered still just restarts the silence
     count (Pipecat's real silence timer and conversation record).
"""

import asyncio
from types import SimpleNamespace

from pipecat.frames.frames import (
    BotStartedSpeakingFrame, BotStoppedSpeakingFrame, EndFrame, InterimTranscriptionFrame, LLMRunFrame,
    TranscriptionFrame, TTSSpeakFrame, UserIdleTimeoutUpdateFrame, UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame, VADUserStartedSpeakingFrame,
)
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.turns.user_idle_controller import UserIdleController
from pipecat.turns.user_start import TranscriptionUserTurnStartStrategy, VADUserTurnStartStrategy
from pipecat.turns.user_stop import ExternalUserTurnStopStrategy
from pipecat.turns.user_turn_controller import UserTurnController
from pipecat.turns.user_turn_strategies import UserTurnStrategies, default_user_turn_start_strategies
from pipecat.utils.asyncio.task_manager import TaskManager, TaskManagerParams

from agent_builder import CallWatchWiring, caller_turn_rules
from call import CallWatch
from call.silence import CHECK_IN

ANSWERED = [{"role": "user", "content": "I need an appointment."},
            {"role": "assistant", "content": "Could you please tell me your full name?"}]
UNANSWERED = ANSWERED + [{"role": "user", "content": "Yes, that is it."}]


def task_manager() -> TaskManager:
    tm = TaskManager()
    tm.setup(TaskManagerParams(loop=asyncio.get_running_loop()))
    return tm


# ================================================================ 1. what starts a caller turn
def turn_starts(start_rules, frames) -> int:
    """Feeds frames to Pipecat's real turn controller; returns how many caller turns started."""
    async def run():
        # The stop rule doesn't matter here; the external one avoids loading the turn model.
        controller = UserTurnController(user_turn_strategies=UserTurnStrategies(
            start=start_rules, stop=[ExternalUserTurnStopStrategy()]))
        started = []

        async def on_started(_controller, strategy, _params):
            started.append(strategy)
        controller.add_event_handler("on_user_turn_started", on_started)
        await controller.setup(task_manager())
        for f in frames:
            await controller.process_frame(f)
        await controller.cleanup()
        return len(started)
    return asyncio.run(run())


def late_draft():
    return InterimTranscriptionFrame("Yes, that is it", "caller", "2026-10-11T22:51:48.541")


def test_the_late_draft_started_a_turn_with_pipecats_default_rules():
    """The 'before': this is what cancelled the answer on the call."""
    assert turn_starts(default_user_turn_start_strategies(), [late_draft()]) == 1


def test_our_rules_ignore_a_rough_draft():
    assert turn_starts(caller_turn_rules().start, [late_draft()]) == 0


def test_our_rules_still_start_a_turn_on_final_text_the_voice_detector_missed():
    """Speech too soft for the voice detector still counts once its final text arrives."""
    final = TranscriptionFrame("Yes, that is it.", "caller", "2026-10-11T22:51:48.516")
    assert turn_starts(caller_turn_rules().start, [final]) == 1


def test_our_rules_still_start_a_turn_on_the_voice_detector():
    assert turn_starts(caller_turn_rules().start, [VADUserStartedSpeakingFrame()]) == 1


def test_the_rules_are_the_voice_detector_plus_final_text_only():
    rules = caller_turn_rules()
    assert [type(s) for s in rules.start] == [VADUserTurnStartStrategy, TranscriptionUserTurnStartStrategy]
    assert rules.start[1]._use_interim is False
    assert rules.stop, "when a turn ends stays Pipecat's default"


def test_the_bot_uses_these_rules():
    source = open("bot.py", encoding="utf-8").read()
    assert "user_turn_strategies=caller_turn_rules()" in source


# ================================================================ 2. the safety net
class FakeAggregator:
    """The user aggregator's parts the wiring uses: Pipecat's real silence timer, the real
    conversation record, and event handlers."""

    def __init__(self, timeout: float, messages: list):
        self._user_idle_controller = UserIdleController(user_idle_timeout=timeout)
        self.context = LLMContext(messages=list(messages))
        self.handlers = {}
        self._user_idle_controller.add_event_handler("on_user_turn_idle", self._idle)

    def add_event_handler(self, name, handler):
        self.handlers[name] = handler

    async def _idle(self, controller):
        await self.handlers["on_user_turn_idle"](self)

    async def empty_turn(self):
        """A 'turn' with no words: the late draft, or a noise."""
        c = self._user_idle_controller
        await c.process_frame(UserStartedSpeakingFrame())
        await asyncio.sleep(0.02)
        await c.process_frame(UserStoppedSpeakingFrame())
        await self.handlers["on_user_turn_stopped"](self, None, SimpleNamespace(content=None))


class FakeWorker:
    def __init__(self, agg: FakeAggregator):
        self.agg, self.said, self.asked_ai, self.ended = agg, [], 0, False

    async def queue_frame(self, frame):
        await self.queue_frames([frame])

    async def queue_frames(self, frames):
        c = self.agg._user_idle_controller
        for f in frames:
            if isinstance(f, LLMRunFrame):
                self.asked_ai += 1
            elif isinstance(f, UserIdleTimeoutUpdateFrame):
                await c.process_frame(f)
            elif isinstance(f, TTSSpeakFrame):
                self.said.append(f.text)
                await c.process_frame(BotStartedSpeakingFrame())
                await c.process_frame(BotStoppedSpeakingFrame())
            elif isinstance(f, EndFrame):
                self.ended = True


def after_an_empty_turn(messages, wait=0.3):
    async def run():
        agg = FakeAggregator(0.15, messages)
        await agg._user_idle_controller.setup(task_manager())
        worker, log = FakeWorker(agg), []
        CallWatchWiring(CallWatch(0.15, 0.1, 60.0), agg, worker, log.append, lambda: False)
        await agg._user_idle_controller.process_frame(BotStoppedSpeakingFrame())  # the agent's last line ends
        await asyncio.sleep(0.05)
        await agg.empty_turn()
        await asyncio.sleep(wait)
        return worker, log
    return asyncio.run(run())


def test_an_empty_turn_that_cut_off_the_answer_asks_the_ai_again():
    worker, log = after_an_empty_turn(UNANSWERED, wait=0.1)
    assert worker.asked_ai == 1
    assert {"event": "reply_retried"} in log
    assert worker.said == [], "the AI answers; the code doesn't say anything itself"


def test_an_empty_turn_after_the_agent_answered_does_not_ask_the_ai_again():
    """A noise after the agent has spoken: nothing to answer, so the silence count runs as before."""
    worker, log = after_an_empty_turn(ANSWERED)
    assert worker.asked_ai == 0
    assert worker.said[:1] == [CHECK_IN]
    assert all(line["event"] != "reply_retried" for line in log)


def test_an_empty_turn_at_the_very_start_does_not_ask_the_ai():
    worker, _ = after_an_empty_turn([])
    assert worker.asked_ai == 0 and worker.said[:1] == [CHECK_IN]


def test_an_empty_turn_after_a_tool_result_does_not_ask_the_ai():
    """Narrow on purpose: after a tool, Flows decides when the AI runs (the tool may still be running)."""
    tool_last = UNANSWERED + [
        {"role": "assistant", "tool_calls": [{"id": "c1", "type": "function",
                                              "function": {"name": "start_booking", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "c1", "content": "{\"ok\": true}"}]
    worker, _ = after_an_empty_turn(tool_last)
    assert worker.asked_ai == 0
