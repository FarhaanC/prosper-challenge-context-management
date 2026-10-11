"""Builder tests for decisions 64, 66 and 67 (agreed after the voice calls), and the
fixes from their independent review (docs/reviews/2026-10-11-silence-and-read-back/).

64: silence check-in, hang-up and the 10-minute cap (call/silence.py; Pipecat side in
    agent_builder/call_watch.py).
66: the code says the read-back after choose_option; the AI waits for the caller.
67: in the booking stage the AI says a short line before searching again.

The silence and "talking over the agent" tests drive Pipecat's real parts (its silence
timer, Flows' action runner, a real pipeline with a stand-in voice), with short timings.
"""

import asyncio
import json
from types import SimpleNamespace

import pytest
from pipecat.frames.frames import (
    BotStartedSpeakingFrame, BotStoppedSpeakingFrame, EndFrame, InterruptionFrame, StartFrame, TTSAudioRawFrame,
    TTSSpeakFrame, TTSStartedFrame, TTSStoppedFrame, UserIdleTimeoutUpdateFrame, UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair
from pipecat.processors.frame_processor import FrameProcessor
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.base_output import BaseOutputTransport
from pipecat.transports.base_transport import TransportParams
from pipecat.turns.user_idle_controller import UserIdleController
from pipecat.utils.asyncio.task_manager import TaskManager, TaskManagerParams
from pipecat.workers.runner import WorkerRunner
from pipecat_flows import ContextStrategy, FlowManager

from agent_builder import AgentBuilder, CallWatchWiring
from call import TOOLS, CallWatch, Clinic, Outcome, run_tool
from call.silence import (
    CHECK_IN, CHECK_IN_AFTER, HANG_UP_AFTER, MAX_CALL_SECONDS, SILENCE_GOODBYE, TIME_LIMIT_GOODBYE,
)
from catalog_ids import NOW, SKIN_CANCER_SCREENING
from clinic import BOOKING, Schedule

AGENT_FILE = "clinic_agent.json"


def agent_dict() -> dict:
    with open(AGENT_FILE, encoding="utf-8") as f:
        return json.load(f)


class FakeFlowManager:
    def __init__(self, session):
        self.state = {"session": session}


def at_booking(catalog, patients, tmp_path):
    """A new caller in the booking stage, driven through the real Pipecat wrappers."""
    clinic = Clinic(catalog, patients, Schedule(catalog), bookings_file=tmp_path / "b.jsonl", log_dir=tmp_path / "logs")
    b = AgentBuilder.from_json(AGENT_FILE)
    s = clinic.new_call(clock=lambda: NOW)
    node = b.build_initial_node(s)

    def call(name, args):
        f = next(f for f in node["functions"] + b.global_functions() if f.name == name)
        return asyncio.run(f.handler(args, FakeFlowManager(s)))

    _, node = call("start_booking", {"full_name": "Farhan Jida", "returning": False})
    _, node = call("choose_visit_type", {"visit_type_id": SKIN_CANCER_SCREENING})
    return b, s, node, call


def log_lines(s) -> list:
    return [json.loads(line) for line in s.log_path.read_text(encoding="utf-8").splitlines()]


# ================================================================ 64: the rules (plain Python)
def test_the_numbers_are_the_agreed_ones():
    w = CallWatch()
    assert (CHECK_IN_AFTER, HANG_UP_AFTER, MAX_CALL_SECONDS) == (20, 15, 600)
    assert (w.check_in_after, w.hang_up_after, w.max_call_seconds) == (20, 15, 600)


def test_silence_checks_in_then_says_goodbye_and_hangs_up():
    w = CallWatch()
    first = w.on_silence()
    assert first.say == CHECK_IN == "Are you still there?"
    assert first.hang_up is False and first.next_wait == HANG_UP_AFTER
    second = w.on_silence()
    assert second.say == SILENCE_GOODBYE and second.hang_up is True
    assert w.on_silence() is None, "nothing more once it has hung up"


def test_words_after_a_check_in_start_the_full_count_again():
    w = CallWatch()
    assert w.on_caller_spoke() is None, "no check-in pending: the wait hasn't changed"
    w.on_silence()
    assert w.on_caller_spoke() == CHECK_IN_AFTER
    assert w.on_silence().say == CHECK_IN, "a fresh silence gets a fresh check-in, not the goodbye"


def test_the_time_limit_ends_the_call_once_and_not_a_finished_call():
    assert CallWatch().on_time_limit(call_finished=True) is None, "a booked call is already saying goodbye"
    w = CallWatch()
    step = w.on_time_limit(call_finished=False)
    assert step.say == TIME_LIMIT_GOODBYE and step.hang_up is True
    assert w.on_time_limit(call_finished=False) is None and w.on_silence() is None


def test_no_time_limit_goodbye_after_a_silence_hang_up():
    w = CallWatch()
    w.on_silence()
    w.on_silence()
    assert w.on_time_limit(call_finished=False) is None and w.on_caller_spoke() is None


# ================================================================ 64: with Pipecat's real silence timer
class FakeAggregator:
    """Stands in for the user aggregator: Pipecat's real silence timer inside, and event handlers."""

    def __init__(self, timeout: float):
        self._user_idle_controller = UserIdleController(user_idle_timeout=timeout)
        self.handlers = {}
        self._user_idle_controller.add_event_handler("on_user_turn_idle", self._idle)

    def add_event_handler(self, name, handler):
        self.handlers[name] = handler

    async def _idle(self, controller):
        await self.handlers["on_user_turn_idle"](self)

    async def turn(self, words: str):
        """The caller makes a sound; `words` is what speech-to-text made of it ("" for noise)."""
        c = self._user_idle_controller
        await c.process_frame(UserStartedSpeakingFrame())
        await asyncio.sleep(0.02)
        await c.process_frame(UserStoppedSpeakingFrame())
        await self.handlers["on_user_turn_stopped"](self, None, SimpleNamespace(content=words))


class FakeWorker:
    """Records what the code queues. Like the real pipeline, timeout changes reach the timer,
    and a spoken line makes the agent start and stop speaking."""

    def __init__(self, agg: FakeAggregator):
        self.agg, self.said, self.ended = agg, [], False

    async def queue_frame(self, frame):
        await self.queue_frames([frame])

    async def queue_frames(self, frames):
        c = self.agg._user_idle_controller
        for f in frames:
            if isinstance(f, UserIdleTimeoutUpdateFrame):
                await c.process_frame(f)
            elif isinstance(f, TTSSpeakFrame):
                self.said.append(f.text)
                await c.process_frame(BotStartedSpeakingFrame())
                await c.process_frame(BotStoppedSpeakingFrame())
            elif isinstance(f, EndFrame):
                self.ended = True


async def wired(check_in=0.15, hang_up=0.1, max_call=60.0, finished=False):
    agg = FakeAggregator(check_in)
    tm = TaskManager()
    tm.setup(TaskManagerParams(loop=asyncio.get_running_loop()))
    await agg._user_idle_controller.setup(tm)
    worker, log = FakeWorker(agg), []
    wiring = CallWatchWiring(CallWatch(check_in, hang_up, max_call), agg, worker, log.append, lambda: finished)
    return agg, worker, log, wiring


def test_greeting_then_silence_checks_in_then_hangs_up():
    async def run():
        agg, worker, log, _ = await wired()
        await agg._user_idle_controller.process_frame(BotStoppedSpeakingFrame())  # the greeting ends
        await asyncio.sleep(0.6)
        return worker, log
    worker, log = asyncio.run(run())
    assert worker.said == [CHECK_IN, SILENCE_GOODBYE] and worker.ended
    assert [line["event"] for line in log] == ["silence", "silence"] and log[-1]["hang_up"] is True


def test_a_noise_with_no_words_does_not_switch_the_silence_count_off():
    """Review R1: a rustle on a pocket dial used to leave the call open until the 10-minute cap."""
    async def run():
        agg, worker, _, _ = await wired()
        await agg._user_idle_controller.process_frame(BotStoppedSpeakingFrame())
        await asyncio.sleep(0.05)
        await agg.turn("")            # noise: no words, so no reply
        await asyncio.sleep(0.6)
        return worker
    worker = asyncio.run(run())
    assert worker.said == [CHECK_IN, SILENCE_GOODBYE] and worker.ended


def test_a_noise_after_the_check_in_does_not_cancel_the_goodbye():
    async def run():
        agg, worker, _, _ = await wired()
        await agg._user_idle_controller.process_frame(BotStoppedSpeakingFrame())
        await asyncio.sleep(0.2)      # the check-in has been said
        await agg.turn("")
        await asyncio.sleep(0.15)     # longer than hang_up, shorter than check_in + hang_up
        return worker
    worker = asyncio.run(run())
    assert worker.said == [CHECK_IN, SILENCE_GOODBYE] and worker.ended


def test_words_after_the_check_in_bring_back_the_full_wait():
    async def run():
        agg, worker, _, _ = await wired()
        c = agg._user_idle_controller
        await c.process_frame(BotStoppedSpeakingFrame())
        await asyncio.sleep(0.2)      # check-in said
        await agg.turn("yes, sorry")
        await c.process_frame(BotStartedSpeakingFrame())   # the AI replies
        await c.process_frame(BotStoppedSpeakingFrame())
        await asyncio.sleep(0.12)     # past hang_up, before check_in: no goodbye yet
        early = list(worker.said)
        await asyncio.sleep(0.1)      # past check_in
        return early, worker
    early, worker = asyncio.run(run())
    assert early == [CHECK_IN]
    assert worker.said == [CHECK_IN, CHECK_IN] and not worker.ended


def test_the_time_limit_says_goodbye_and_hangs_up():
    async def run():
        _, worker, log, wiring = await wired(max_call=0.05)
        wiring.start_time_limit()
        await asyncio.sleep(0.15)
        return worker, log
    worker, log = asyncio.run(run())
    assert worker.said == [TIME_LIMIT_GOODBYE] and worker.ended and log[0]["event"] == "time_limit"


def test_the_time_limit_stays_quiet_for_a_finished_or_stopped_call():
    """Review R3/R6: a booked call got a false 'time limit' line in its log 10 minutes later."""
    async def run(finished, stop):
        _, worker, log, wiring = await wired(max_call=0.05, finished=finished)
        wiring.start_time_limit()
        if stop:
            wiring.stop()
        await asyncio.sleep(0.15)
        return worker.said, log
    assert asyncio.run(run(finished=True, stop=False)) == ([], [])
    assert asyncio.run(run(finished=False, stop=True)) == ([], [])


def test_bot_stops_the_time_limit_however_the_call_ends():
    with open("bot.py", encoding="utf-8") as f:
        source = f.read()
    assert "user_idle_timeout=watch.check_in_after" in source
    assert "finally:\n        silence.stop()" in source


# ================================================================ talking over a line the code says
SR = 16000
CHUNK = int(SR * 0.02) * 2  # 20 ms of 16-bit mono


class FakeVoice(FrameProcessor):
    """Turns a line into 2 s of audio, like the voice service."""

    async def process_frame(self, frame, direction):
        await super().process_frame(frame, direction)
        if isinstance(frame, TTSSpeakFrame):
            await self.push_frame(TTSStartedFrame(context_id="c1"))
            for _ in range(100):
                await self.push_frame(TTSAudioRawFrame(audio=b"\x10\x20" * (CHUNK // 2), sample_rate=SR,
                                                       num_channels=1, context_id="c1"))
            await self.push_frame(TTSStoppedFrame(context_id="c1"))
        else:
            await self.push_frame(frame, direction)


class FakeSpeaker(BaseOutputTransport):
    async def start(self, frame: StartFrame):
        await super().start(frame)
        await self.set_transport_ready(frame)

    async def write_audio_frame(self, frame) -> bool:
        await asyncio.sleep(0.02)
        return True


@pytest.mark.parametrize("interrupt", [False, True])
def test_talking_over_the_greeting_still_gives_stage_one_its_instructions_and_tools(clinic_for_call, interrupt):
    """Review R2: with Flows' own tts_say, an interrupted greeting left stage 1 with no
    instructions and no tools for the rest of the call."""
    async def run():
        context = LLMContext()
        pair = LLMContextAggregatorPair(context)
        worker = PipelineWorker(Pipeline([pair.user(), FakeVoice(), FakeSpeaker(TransportParams(
            audio_out_enabled=True, audio_out_sample_rate=SR)), pair.assistant()]),
            params=PipelineParams(audio_out_sample_rate=SR))
        flow = FlowManager(llm=OpenAILLMService(api_key="not-used"), context_aggregator=pair, worker=worker)
        runner = WorkerRunner(handle_sigint=False)
        await runner.add_workers(worker)
        running = asyncio.create_task(runner.run())
        await asyncio.sleep(0.3)
        session = clinic_for_call.new_call(clock=lambda: NOW)
        flow.state["session"] = session
        start = asyncio.create_task(flow.initialize(AgentBuilder.from_json(AGENT_FILE).build_initial_node(session)))
        if interrupt:
            await asyncio.sleep(0.7)                       # the caller talks over the greeting
            await worker.queue_frame(InterruptionFrame())
        await asyncio.sleep(1.0)
        done, node = start.done(), flow.current_node
        messages = [m.get("content", "") for m in context.get_messages()]
        tools = [t.name for t in getattr(context.tools, "standard_tools", [])]
        if not done:
            start.cancel()  # stuck waiting for the interrupted line: fail, don't hang
        await worker.cancel()
        try:
            await asyncio.wait_for(running, timeout=5)
        except Exception:
            pass
        return done, node, messages, tools
    done, node, messages, tools = asyncio.run(run())
    assert done and node == "identify"
    assert any("Find out, one question at a time" in m for m in messages)
    assert "start_booking" in tools


@pytest.fixture
def clinic_for_call(catalog, patients, tmp_path):
    return Clinic(catalog, patients, Schedule(catalog), bookings_file=tmp_path / "b.jsonl", log_dir=tmp_path / "logs")


# ================================================================ 66: the code says the read-back
def test_choose_option_gives_the_code_the_read_back_to_say(catalog, patients, tmp_path):
    _, s, node, call = at_booking(catalog, patients, tmp_path)
    result, same = call("choose_option", {"option_id": s.card.offered_options[0].option_id})
    read_back = s.card.read_back(catalog)
    assert result["ok"] is True and result["read_back"] == read_back
    assert "say" not in result and "said" not in result, "the AI must not be told to say anything"

    # The same stage, its conversation kept, the code speaking, and the AI waiting.
    assert same["name"] == BOOKING and s.stage == BOOKING
    assert same["context_strategy"].strategy == ContextStrategy.APPEND
    assert same["task_messages"] == []
    (action,) = same["pre_actions"]
    assert action["type"] == "say" and callable(action["handler"])
    spoken = action["text"]
    assert read_back in spoken and spoken.rstrip().endswith("?"), "the read-back, then a question to the caller"
    assert same["respond_immediately"] is False
    assert [f.name for f in same["functions"]] == [f.name for f in node["functions"]]
    assert same["role_message"] == node["role_message"]


def test_the_read_back_is_logged_and_no_new_stage_is_logged(catalog, patients, tmp_path):
    _, s, _, call = at_booking(catalog, patients, tmp_path)
    before = len(log_lines(s))
    call("choose_option", {"option_id": s.card.offered_options[0].option_id})
    (line,) = log_lines(s)[before:]
    assert line["tool"] == "choose_option" and s.card.read_back(catalog) in line["said"]
    assert line["next_stage"] is None


def test_a_refused_choose_option_says_nothing(catalog, patients, tmp_path):
    _, s, _, call = at_booking(catalog, patients, tmp_path)
    result = call("choose_option", {"option_id": "99"})
    assert isinstance(result, dict) and result["ok"] is False


def test_after_the_read_back_yes_books_it(catalog, patients, tmp_path):
    _, s, _, call = at_booking(catalog, patients, tmp_path)
    _, same = call("choose_option", {"option_id": s.card.offered_options[0].option_id})
    confirm = next(f for f in same["functions"] if f.name == "confirm_booking")
    result, end = asyncio.run(confirm.handler({}, FakeFlowManager(s)))
    assert result["ok"] is True and end["name"] == "end" and s.card.status == "booked"


def test_only_choose_option_has_the_code_speak(catalog, patients):
    """Every tool, in a call that books: only choose_option hands the code a sentence."""
    s = Clinic(catalog, patients, Schedule(catalog)).new_call(clock=lambda: NOW)
    s.enter_stage("identify", [])
    used = {}

    def run(name, args):
        out = run_tool(s, name, args)
        used[name] = out.say_now
        if out.next_stage:
            s.enter_stage(out.next_stage, [])

    run("start_booking", {"full_name": "Farhan Jida", "returning": False})
    run("list_visit_types", {"specialty": "Dermatology"})
    run("choose_visit_type", {"visit_type_id": SKIN_CANCER_SCREENING})
    run("answer_question", {"about": "location", "name": "Midtown"})
    run("change_choice", {"time_of_day": "morning"})
    run("turn_down_doctors", {"on_offer": True})
    run("choose_option", {"option_id": s.card.offered_options[0].option_id})
    run("confirm_booking", {})
    run("hand_off", {"reason": "speak_to_staff"})
    assert set(used) == set(TOOLS), "every tool was run"
    assert {name for name, said in used.items() if said} == {"choose_option"}


def test_an_outcome_cannot_both_move_and_speak():
    """Review R8: the sentence would be silently lost on the move."""
    with pytest.raises(ValueError, match="not both"):
        Outcome({"ok": True}, next_stage=BOOKING, say_now="Hello")


# ================================================================ 66, 67 and review R4: the instructions
def test_booking_instructions_hand_the_read_back_to_the_code_and_ask_for_a_line_before_searching():
    booking = next(n for n in agent_dict()["nodes"] if n["name"] == "booking")["task_messages"][0]["content"]
    assert "say the read_back word for word" not in booking
    assert "said to the caller for you, so don't say them yourself" in booking
    before_search = booking.split("call change_choice", 1)[1]
    assert "Let me check" in before_search, "the short line is asked for where searching again is described"


def test_a_yes_to_are_you_still_there_is_not_a_yes_to_the_booking():
    persona = agent_dict()["persona"]
    assert CHECK_IN in persona and "ask your last question again" in persona
