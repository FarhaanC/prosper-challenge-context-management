"""Builder tests for decisions 64, 66 and 67 (agreed after the voice calls, built Fri 9 Oct).

64: silence check-in, hang-up and the 10-minute cap (call/silence.py, wired in bot.py).
66: the code says the read-back after choose_option; the AI waits for the caller.
67: in the booking stage the AI says a short line before searching again.
"""

import asyncio
import json

from pipecat_flows import ContextStrategy

from agent_builder import AgentBuilder
from call import CallWatch, Clinic, run_tool
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
        f = next(f for f in node["functions"] if f.name == name)
        return asyncio.run(f.handler(args, FakeFlowManager(s)))

    _, node = call("start_booking", {"full_name": "Farhan Jida", "returning": False})
    _, node = call("choose_visit_type", {"visit_type_id": SKIN_CANCER_SCREENING})
    return b, s, node, call


def log_lines(s) -> list:
    return [json.loads(line) for line in s.log_path.read_text(encoding="utf-8").splitlines()]


# ---------------------------------------------------------------- 64: silence and the time limit
def test_the_numbers_are_the_agreed_ones():
    assert (CHECK_IN_AFTER, HANG_UP_AFTER, MAX_CALL_SECONDS) == (20, 15, 600)


def test_silence_checks_in_then_says_goodbye_and_hangs_up():
    w = CallWatch()
    first = w.on_silence()
    assert first.say == CHECK_IN == "Are you still there?"
    assert first.hang_up is False and first.next_wait == HANG_UP_AFTER
    second = w.on_silence()
    assert second.say == SILENCE_GOODBYE and second.hang_up is True
    assert w.on_silence() is None, "nothing more once it has hung up"


def test_the_caller_speaking_starts_the_count_again():
    w = CallWatch()
    assert w.on_caller_spoke() is None, "no check-in pending: the wait hasn't changed"
    w.on_silence()
    assert w.on_caller_spoke() == CHECK_IN_AFTER
    assert w.on_silence().say == CHECK_IN, "a fresh silence gets a fresh check-in, not the goodbye"


def test_the_time_limit_ends_the_call_once():
    w = CallWatch()
    step = w.on_time_limit()
    assert step.say == TIME_LIMIT_GOODBYE and step.hang_up is True
    assert w.on_time_limit() is None and w.on_silence() is None


def test_no_time_limit_goodbye_after_a_silence_hang_up():
    w = CallWatch()
    w.on_silence()
    w.on_silence()
    assert w.on_time_limit() is None and w.on_caller_spoke() is None


def test_bot_wires_the_idle_timer_and_the_time_limit():
    with open("bot.py", encoding="utf-8") as f:
        source = f.read()
    assert "user_idle_timeout=CHECK_IN_AFTER" in source
    assert 'event_handler("on_user_turn_idle")' in source
    assert 'event_handler("on_user_turn_started")' in source
    assert "asyncio.sleep(MAX_CALL_SECONDS)" in source
    assert "time_limit_task.cancel()" in source


# ---------------------------------------------------------------- 66: the code says the read-back
def test_choose_option_gives_the_code_the_read_back_to_say(catalog, patients, tmp_path):
    _, s, node, call = at_booking(catalog, patients, tmp_path)
    option = s.card.offered_options[0]
    result, same = call("choose_option", {"option_id": option.option_id})
    read_back = s.card.read_back(catalog)
    assert result["ok"] is True and result["read_back"] == read_back
    assert "Don't repeat it" in result["said"]

    # The same stage, its conversation kept, the code speaking, and the AI waiting.
    assert same["name"] == BOOKING and s.stage == BOOKING
    assert same["context_strategy"].strategy == ContextStrategy.APPEND
    assert same["task_messages"] == []
    assert same["pre_actions"] == [{"type": "tts_say",
                                    "text": f"To confirm: {read_back} Would you like me to book it?"}]
    assert same["respond_immediately"] is False
    assert [f.name for f in same["functions"]] == [f.name for f in node["functions"]]
    assert same["role_message"] == node["role_message"]


def test_the_read_back_is_logged_and_no_new_stage_is_logged(catalog, patients, tmp_path):
    _, s, _, call = at_booking(catalog, patients, tmp_path)
    before = len(log_lines(s))
    call("choose_option", {"option_id": s.card.offered_options[0].option_id})
    (line,) = log_lines(s)[before:]
    assert line["tool"] == "choose_option" and line["said"].startswith("To confirm: ")
    assert line["next_stage"] is None


def test_a_refused_choose_option_says_nothing(catalog, patients, tmp_path):
    _, s, _, call = at_booking(catalog, patients, tmp_path)
    result = call("choose_option", {"option_id": "99"})
    assert isinstance(result, dict) and result["ok"] is False
    assert "said" not in result


def test_after_the_read_back_yes_books_it(catalog, patients, tmp_path):
    _, s, _, call = at_booking(catalog, patients, tmp_path)
    _, same = call("choose_option", {"option_id": s.card.offered_options[0].option_id})
    confirm = next(f for f in same["functions"] if f.name == "confirm_booking")
    result, end = asyncio.run(confirm.handler({}, FakeFlowManager(s)))
    assert result["ok"] is True and end["name"] == "end" and s.card.status == "booked"


def test_only_choose_option_has_the_code_speak(catalog, patients, tmp_path):
    clinic = Clinic(catalog, patients, Schedule(catalog))
    s = clinic.new_call(clock=lambda: NOW)
    s.enter_stage("identify", [])
    out = run_tool(s, "start_booking", {"full_name": "Farhan Jida", "returning": False})
    assert out.say_now == ""
    s.enter_stage(out.next_stage, [])
    out = run_tool(s, "choose_visit_type", {"visit_type_id": SKIN_CANCER_SCREENING})
    assert out.say_now == ""
    s.enter_stage(out.next_stage, [])
    out = run_tool(s, "change_choice", {"time_of_day": "morning"})
    assert out.say_now == ""


# ---------------------------------------------------------------- 66 and 67: the booking stage's instructions
def test_booking_instructions_hand_the_read_back_to_the_code_and_ask_for_a_line_before_searching():
    booking = next(n for n in agent_dict()["nodes"] if n["name"] == "booking")["task_messages"][0]["content"]
    assert "say the read_back word for word" not in booking
    assert "the read-back and the question whether to book it are then said to the caller for you" in booking
    assert "Before calling either of these, say one short line such as \"Let me check.\"" in booking
