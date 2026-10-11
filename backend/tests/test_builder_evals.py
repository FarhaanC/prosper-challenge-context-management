"""Builder tests for the typed test runs (evals/), with a pretend AI that follows a script.

They check that the loop copies what the voice agent does (decision 22 and review R11),
that the naive versions behave as decision 86 says, that scoring catches what decision 87
says it must, and that the $7 stop holds (decision 84). Nothing here calls OpenAI.
"""

import json
import re
from dataclasses import replace
from datetime import datetime
from types import SimpleNamespace as NS

import httpx
import openai
import pytest

from call import TOOLS, Clinic
from clinic import Schedule
from evals.agents import AGENT_FILE, GREETING, MAX_PASSES_PER_TURN, NaiveAgent, OurAgent
from evals.ai import OpenAIChat, OutOfCredit, Reply, ToolCall
from evals.budget import BudgetStop, Ledger, Usage, dollars
from evals.caller import CallerAI
from evals.conversation import run_conversation
from evals.run import ROUNDS, VERSIONS
from evals.scenarios import BY_ID, CHECK_IN_SCENARIO, SCENARIOS
from evals.scoring import STAFF_PROMISE, score

NOW = datetime(2026, 10, 13, 9, 0)
AGENT = json.loads(AGENT_FILE.read_text(encoding="utf-8"))
JAMES = {"full_name": "James Wilson", "returning": True, "date_of_birth": "1984-03-12",
         "visit_description": "knee MRI", "specialty": "Radiology"}


class ScriptedAI:
    """Plays the AI from a script: each step is a reply text, (text, tool name, arguments), or a Reply."""

    def __init__(self, steps):
        self.steps = list(steps)
        self.requests = []

    def reply(self, messages, tools=None, one_tool_at_a_time=True):
        self.requests.append({"messages": json.loads(json.dumps(messages)), "tools": tools,
                              "one_at_a_time": one_tool_at_a_time})
        step = self.steps.pop(0)
        if isinstance(step, Reply):
            return step
        if isinstance(step, str):
            return Reply(step, [], Usage(100, 0, 10), 0.01, 0.0)
        text, name, args = step
        return Reply(text, [ToolCall(f"call_{len(self.requests)}", name, json.dumps(args))], Usage(100, 0, 10),
                     0.01, 0.0)

    def tool_names(self, i):
        return [t["function"]["name"] for t in self.requests[i]["tools"]]


@pytest.fixture
def clinic(catalog, patients, tmp_path):
    return Clinic(catalog, patients, Schedule(catalog), bookings_file=tmp_path / "bookings.jsonl")


def ours(clinic, steps):
    ai = ScriptedAI(steps)
    agent = OurAgent(ai, clinic, NOW)
    return agent, ai


# ---------------------------------------------------------------- our agent: the loop copies the voice agent
def test_greeting_is_said_by_the_code_and_the_ai_waits(clinic):
    agent, ai = ours(clinic, [])
    first = agent.start()
    greeting = AGENT["nodes"][0]["pre_actions"][0]["text"]
    assert first.said == [greeting] and first.passes == 0 and ai.requests == []
    assert agent.messages[-1] == {"role": "assistant", "content": greeting}


def test_a_stage_move_wipes_the_conversation_and_the_new_stage_answers(clinic):
    agent, ai = ours(clinic, [("Thank you, one moment.", "start_booking", JAMES), "Thanks, James. The knee MRI?"])
    agent.start()
    turn = agent.respond("James Wilson, born March 12th 1984, I need a knee MRI.")
    assert turn.passes == 2
    assert turn.said == ["Thank you, one moment.", "Thanks, James. The knee MRI?"]
    second = ai.requests[1]["messages"]
    assert second[0] == {"role": "system", "content": AGENT["persona"]}
    assert [m["role"] for m in second] == ["system", "developer"]  # nothing from the first stage survives
    assert "MRI - Knee" in second[1]["content"] and not re.search(r"\{[a-z_]+\}", second[1]["content"])
    stage = next(n for n in AGENT["nodes"] if n["name"] == "visit_type")
    assert ai.tool_names(1) == AGENT["global_tools"] + stage["tools"]
    assert all(r["one_at_a_time"] for r in ai.requests)


def test_a_tool_that_stays_gets_a_second_pass_that_sees_its_result(clinic):
    agent, ai = ours(clinic, [("One moment.", "start_booking", {**JAMES, "specialty": ""}), "Which kind of visit?",
                              ("Let me look.", "list_visit_types", {"specialty": "Radiology"}), "Here they are."])
    agent.start()
    agent.respond("James Wilson, 1984-03-12, an MRI.")
    turn = agent.respond("An MRI of my knee.")
    assert turn.passes == 2
    last = ai.requests[-1]["messages"][-1]
    assert last["role"] == "tool" and "MRI - Knee" in last["content"]
    assert ai.requests[-1]["messages"][-2]["tool_calls"][0]["function"]["name"] == "list_visit_types"


def _to_options(clinic):
    agent, ai = ours(clinic, [("One moment.", "start_booking", JAMES), "The knee MRI?",
                              ("Great.", "choose_visit_type", {"visit_type_id": "appt_065"}), "I have two options."])
    agent.start()
    agent.respond("James Wilson, 1984-03-12, knee MRI.")
    agent.respond("Yes, the knee MRI.")
    return agent, ai


def test_choose_option_read_back_is_the_agents_turn_with_no_second_pass(clinic):
    agent, ai = _to_options(clinic)
    assert "Option 1" in ai.requests[-1]["messages"][1]["content"]
    ai.steps = [("", "choose_option", {"option_id": "1"})]
    turn = agent.respond("The first one.")
    assert turn.passes == 1  # decision 66 / review R11: no AI pass spent on the read-back
    assert turn.said[-1].startswith("To confirm:") and turn.said[-1].endswith("Would you like me to book it?")
    assert agent.messages[-1] == {"role": "assistant", "content": turn.said[-1]}
    assert agent.session.card.choices.slot is not None


def test_confirm_moves_to_the_end_stage_which_says_goodbye_and_ends(clinic):
    agent, ai = _to_options(clinic)
    ai.steps = [("", "choose_option", {"option_id": "1"}), ("", "confirm_booking", {}), "You're booked. Goodbye!"]
    agent.respond("The first one.")
    turn = agent.respond("Yes please.")
    assert agent.ended and turn.said[-1] == "You're booked. Goodbye!"
    out = agent.outcome()
    assert out["status"] == "booked" and [b["visit_type_id"] for b in out["bookings"]] == ["appt_065"]


def test_a_tool_instead_of_a_goodbye_is_noticed(clinic):
    agent, ai = _to_options(clinic)
    ai.steps = [("", "choose_option", {"option_id": "1"}), ("", "confirm_booking", {}),
                ("", "answer_question", {"about": "location", "name": "Downtown"})]
    agent.respond("The first one.")
    turn = agent.respond("Yes.")
    assert agent.ended and any("instead of saying goodbye" in p for p in turn.problems)


def test_a_stuck_turn_is_ended_and_noticed(clinic):
    agent, ai = ours(clinic, [("", "answer_question", {"about": "location", "name": "Downtown"})] * MAX_PASSES_PER_TURN)
    agent.start()
    turn = agent.respond("Where are you?")
    assert turn.passes == MAX_PASSES_PER_TURN and "More than" in turn.problems[0]


def test_bad_json_from_the_ai_goes_back_to_it_as_an_error(clinic):
    agent, ai = ours(clinic, [Reply("", [ToolCall("c1", "start_booking", "{not json")], Usage(1, 0, 1)),
                              "Sorry, could you say that again?"])
    agent.start()
    turn = agent.respond("Hi")
    assert turn.tools[0]["result"]["status"] == "error" and turn.passes == 2


# ---------------------------------------------------------------- naive versions (decision 86)
BAD_MRI = {"patient_name": "Omar Haddad", "visit_type_id": "appt_065", "provider_id": "prov_014",
           "location_id": "loc_000", "start": "2026-10-14T10:00"}


def test_naive_sees_the_whole_catalog_and_the_rules(clinic):
    ai = ScriptedAI([])
    agent = NaiveAgent(ai, clinic, NOW, checks=False)
    assert agent.start().said == [GREETING]
    text = agent.messages[0]["content"]
    assert agent.messages[0]["role"] == "developer" and agent.system.startswith("You are a warm")
    assert all(p.id in text for p in clinic.catalog.providers.values())
    assert "requires_referral = true need a referral" in text and "Tuesday 13 October 2026" in text


def test_naive_version_1_books_anything(clinic):
    ai = ScriptedAI([("", "book_appointment", BAD_MRI), "Booked!"])
    agent = NaiveAgent(ai, clinic, NOW, checks=False)
    agent.start()
    turn = agent.respond("Yes, book it.")
    assert turn.tools[0]["result"]["ok"] is True and agent.outcome()["status"] == "booked"


def test_naive_version_2_runs_our_rule_check(clinic):
    ai = ScriptedAI([("", "book_appointment", BAD_MRI), "Sorry."])
    agent = NaiveAgent(ai, clinic, NOW, checks=True)
    agent.start()
    turn = agent.respond("Yes, book it.")
    result = turn.tools[0]["result"]
    assert result["ok"] is False and any("existing patients" in p for p in result["problems"])
    assert agent.outcome()["bookings"] == []


def test_naive_open_times_come_from_the_same_schedule(clinic):
    ai = ScriptedAI([("", "find_open_times", {"provider_id": "prov_014", "visit_type_id": "appt_065",
                                               "time_of_day": "morning"}), "Here are some times.",
                     ("", "find_open_times", {"provider_id": ["prov_014"], "visit_type_id": "appt_065"}), "Hmm."])
    agent = NaiveAgent(ai, clinic, NOW, checks=False)
    agent.start()
    times = agent.respond("When?").tools[0]["result"]["times"]
    assert 0 < len(times) <= 6 and all(datetime.fromisoformat(t["start"]).hour < 12 for t in times)
    for t in times:
        start = datetime.fromisoformat(t["start"])
        assert clinic.schedule.is_open("prov_014", t["location_id"], 45, start, NOW)
    assert agent.respond("And?").tools[0]["result"]["ok"] is False  # a list isn't an id: refused, no crash


# ---------------------------------------------------------------- scoring (decision 87)
def _run(outcome, said=(), turns=None):
    return {"ended_by": "caller_hung_up", "outcome": outcome,
            "turns": turns or [{"caller": "hi", "agent": {"said": list(said), "tools": [], "problems": []}}]}


def test_a_rule_breaking_booking_fails_and_counts_as_bad(catalog, patients):
    s = BY_ID["knee_mri_new_patient"]
    result = score(s, _run({"status": "booked", "bookings": [BAD_MRI], "hand_off_called": False}),
                   catalog, patients, NOW)
    assert not result["passed"] and result["bad_bookings"] == 1


def test_a_valid_booking_of_the_wrong_doctor_fails(catalog, patients):
    # The children's Dr. Maria Garcia: a booking that breaks no rule, but isn't the one the caller asked for.
    s = BY_ID["maria_garcia_checkup"]
    start = next(Schedule(catalog).iter_open_slots("prov_002", "loc_000", 30, NOW))
    booking = {"visit_type_id": "appt_002", "provider_id": "prov_002", "location_id": "loc_000",
               "start": start.isoformat()}
    result = score(s, _run({"status": "booked", "bookings": [booking], "hand_off_called": False}),
                   catalog, patients, NOW)
    assert not result["passed"] and result["bad_bookings"] == 0
    assert any("prov_002" in r for r in result["reasons"])


def test_the_real_caller_is_used_not_the_agents_guess(catalog, patients):
    # James Wilson has a Radiology referral; a knee MRI booked for him at a valid place passes the rules.
    s = BY_ID["james_knee_mri_downtown"]
    sched = Schedule(catalog)
    start = next(sched.iter_open_slots("prov_014", "loc_004", 45, NOW))
    booking = {"visit_type_id": "appt_065", "provider_id": "prov_014", "location_id": "loc_004",
               "start": start.isoformat()}
    assert score(s, _run({"status": "booked", "bookings": [booking], "hand_off_called": False}),
                 catalog, patients, NOW)["passed"]
    # The same booking for a new patient (scenario 2's caller) breaks the rules.
    assert score(BY_ID["knee_mri_new_patient"], _run({"status": "booked", "bookings": [booking],
                                                      "hand_off_called": False}),
                 catalog, patients, NOW)["bad_bookings"] == 1


def test_the_expected_pairs_are_checked_on_their_own(catalog, patients):
    # The knee MRI's valid pairs are also enforced by the rules; this checks the scenario's own list too.
    s = replace(BY_ID["james_knee_mri_downtown"], expected=replace(
        BY_ID["james_knee_mri_downtown"].expected, pairs=frozenset({("prov_015", "loc_005")})))
    start = next(Schedule(catalog).iter_open_slots("prov_014", "loc_004", 45, NOW))
    booking = {"visit_type_id": "appt_065", "provider_id": "prov_014", "location_id": "loc_004",
               "start": start.isoformat()}
    result = score(s, _run({"status": "booked", "bookings": [booking], "hand_off_called": False}),
                   catalog, patients, NOW)
    assert not result["passed"] and "valid doctor-place pairs" in result["reasons"][0]


def test_a_hand_off_is_needed_where_expected(catalog, patients):
    s = BY_ID["obgyn_new_then_person"]
    assert not score(s, _run({"status": "in_progress", "bookings": [], "hand_off_called": False}),
                     catalog, patients, NOW)["passed"]
    assert score(s, _run({"status": "handed_off", "bookings": [], "hand_off_called": True},
                         said=["A member of staff will call you back."]), catalog, patients, NOW)["passed"]


@pytest.mark.parametrize("line", ["A member of staff will call you back about this.",
                                  "Someone will follow up with you tomorrow.", "Our team will contact you.",
                                  "We'll get back to you soon."])
def test_staff_promises_are_spotted(line):
    assert STAFF_PROMISE.search(line)


@pytest.mark.parametrize("line", ["Would you like a Follow-up Visit?", "Staff at Downtown are lovely.",
                                  "I'll check the follow-up options."])
def test_ordinary_lines_are_not_promises(line):
    assert not STAFF_PROMISE.search(line)


def test_a_promise_without_hand_off_fails(catalog, patients):
    s = BY_ID["knee_mri_new_patient"]
    result = score(s, _run({"status": "in_progress", "bookings": [], "hand_off_called": False},
                           said=["Sorry, a member of staff will follow up with you."]), catalog, patients, NOW)
    assert not result["passed"] and result["staff_promise"]


def test_a_turn_limit_or_a_code_failure_fails(catalog, patients):
    s = BY_ID["knee_mri_new_patient"]
    stuck = {**_run({"status": "in_progress", "bookings": [], "hand_off_called": False}), "ended_by": "turn_limit"}
    assert not score(s, stuck, catalog, patients, NOW)["passed"]
    crashed = _run({"status": "in_progress", "bookings": [], "hand_off_called": False}, turns=[
        {"caller": "hi", "agent": {"said": [], "tools": [], "problems": ["start_booking failed in the code: X"]}}])
    assert not score(s, crashed, catalog, patients, NOW)["passed"]


# ---------------------------------------------------------------- whole conversations
def test_a_whole_conversation_with_the_check_in_after_the_read_back(clinic, catalog, patients):
    agent, ai = ours(clinic, [("One moment.", "start_booking", JAMES), "The knee MRI?",
                              ("Great.", "choose_visit_type", {"visit_type_id": "appt_065"}), "Two options.",
                              ("", "choose_option", {"option_id": "1"}),
                              ("", "confirm_booking", {}), "Booked, goodbye."])
    caller = CallerAI(ScriptedAI(["James Wilson, 1984-03-12, knee MRI.", "Yes.", "The first one.", "Yes."]), "")
    run = run_conversation(agent, caller, check_in_after_read_back=True)
    assert run["ended_by"] == "agent_ended"
    check_turn = next(t for t in run["turns"] if t.get("check_in_said"))
    assert check_turn["agent"]["said"][-1].startswith("To confirm:")
    after = next(t for t in run["turns"] if t.get("after_check_in"))
    assert after["caller"] == "Yes." and after["agent"]["tools"][0]["tool"] == "confirm_booking"
    # That's exactly what decision 71 rules out, so the scoring fails it:
    result = score(CHECK_IN_SCENARIO, run, catalog, patients, NOW)
    assert not result["passed"] and "Are you still there?" in " ".join(result["reasons"])
    assert {"role": "assistant", "content": "Are you still there?"} in ai.requests[-2]["messages"]


def test_the_caller_hanging_up_ends_the_call(clinic):
    agent, _ = ours(clinic, [])
    run = run_conversation(agent, CallerAI(ScriptedAI(["Sorry, wrong number. [HANG UP]"]), ""))
    assert run["ended_by"] == "caller_hung_up" and run["turns"] == [{"caller": "Sorry, wrong number.", "agent": None}]


def test_a_budget_stop_mid_call_keeps_the_transcript(clinic, tmp_path):
    ledger = Ledger(tmp_path / "spend.jsonl", stop_at=0.05)

    class Broke(ScriptedAI):
        def reply(self, *a, **k):
            ledger.check_room(0.10, "the next reply")

    agent, _ = ours(clinic, [])
    run = run_conversation(agent, CallerAI(Broke([]), ""))
    assert run["ended_by"] == "budget_stop" and "Stopped before" in run["stopped_because"]


# ---------------------------------------------------------------- the budget (decision 84)
def test_prices():
    assert dollars("gpt-4o", Usage(1_000_000, 0, 0)) == 2.50
    assert dollars("gpt-4o", Usage(1_000_000, 1_000_000, 0)) == 1.25
    assert dollars("gpt-4o-mini", Usage(0, 0, 1_000_000)) == 0.60
    with pytest.raises(ValueError):
        dollars("gpt-5", Usage(1, 0, 1))


def test_the_spending_record_survives_a_restart(tmp_path):
    first = Ledger(tmp_path / "s.jsonl")
    first.record("gpt-4o", Usage(1_000_000, 0, 0), "x")
    assert Ledger(tmp_path / "s.jsonl").spent == pytest.approx(2.50)
    assert first.stop_at == 7.00
    with pytest.raises(BudgetStop):
        Ledger(tmp_path / "s.jsonl").check_room(4.51, "y")


def _completion(text="hi", calls=(), prompt=1000, cached=400, out=50):
    message = NS(content=text, tool_calls=[NS(id="c", function=NS(name=n, arguments="{}")) for n in calls] or None)
    usage = NS(prompt_tokens=prompt, completion_tokens=out, prompt_tokens_details=NS(cached_tokens=cached))
    return NS(choices=[NS(message=message)], usage=usage)


class FakeClient:
    def __init__(self, *results):
        self.results = list(results)
        self.params = []
        self.chat = NS(completions=NS(create=self.create))

    def create(self, **params):
        self.params.append(params)
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def _rate_limit(code=None, retry_after="3"):
    response = httpx.Response(429, headers={"retry-after": retry_after},
                              request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"))
    return openai.RateLimitError("Rate limit reached", response=response,
                                 body={"code": code} if code else None)


def test_one_reply_is_costed_recorded_and_asks_for_one_tool_at_a_time(tmp_path):
    ledger = Ledger(tmp_path / "s.jsonl")
    client = FakeClient(_completion(calls=["start_booking"]))
    reply = OpenAIChat(client, "gpt-4o", ledger, "t", say=lambda _: None).reply([{"role": "user", "content": "x"}],
                                                                               tools=[{"type": "function"}])
    assert client.params[0]["parallel_tool_calls"] is False
    assert reply.tool_calls[0].name == "start_booking" and reply.usage == Usage(1000, 400, 50)
    assert ledger.spent == pytest.approx(dollars("gpt-4o", Usage(1000, 400, 50)))


def test_rate_limit_waits_are_not_counted_in_the_timing(tmp_path):
    waited = []
    client = FakeClient(_rate_limit(), _completion())
    chat = OpenAIChat(client, "gpt-4o-mini", Ledger(tmp_path / "s.jsonl"), "t", sleep=waited.append,
                      say=lambda _: None)
    reply = chat.reply([{"role": "user", "content": "x"}])
    assert waited == [3.5] and reply.text == "hi" and reply.seconds < 1
    assert "parallel_tool_calls" not in client.params[0]  # no tools, nothing to say about them


def test_no_credit_stops_at_once(tmp_path):
    chat = OpenAIChat(FakeClient(_rate_limit(code="insufficient_quota")), "gpt-4o", Ledger(tmp_path / "s.jsonl"),
                      "t", sleep=lambda _: pytest.fail("must not wait"), say=lambda _: None)
    with pytest.raises(OutOfCredit):
        chat.reply([{"role": "user", "content": "x"}])


def test_no_request_is_made_without_room(tmp_path):
    client = FakeClient()
    chat = OpenAIChat(client, "gpt-4o", Ledger(tmp_path / "s.jsonl", stop_at=0.05), "t")
    with pytest.raises(BudgetStop):
        chat.reply([{"role": "user", "content": "x"}])
    assert client.params == []


# ---------------------------------------------------------------- the plan of runs
def test_the_rounds_match_decisions_84_and_87():
    assert len(SCENARIOS) == 6 and set(VERSIONS) == {"naive", "naive_rules", "ours", "ours_mini"}
    assert VERSIONS["ours_mini"] == "gpt-4o-mini" and all(VERSIONS[v] == "gpt-4o" for v in ("naive", "naive_rules", "ours"))
    r1 = ROUNDS["round1"]
    assert len(r1) == 6 * 4 + 1 and r1[-1] == (CHECK_IN_SCENARIO, "ours", 1)
    assert [v for _, v, _ in r1[:4]] == list(VERSIONS)  # scenario by scenario
    for name, number in (("round2", 2), ("round3", 3)):
        assert {v for _, v, _ in ROUNDS[name]} == {"ours", "ours_mini"} and {n for *_, n in ROUNDS[name]} == {number}
    assert all(item in r1 for item in ROUNDS["smoke"])  # the smoke run is part of round 1, never paid twice


def test_every_tool_the_agent_file_uses_is_one_the_loop_offers():
    for node in AGENT["nodes"]:
        for name in AGENT["global_tools"] + node.get("tools", []):
            assert name in TOOLS


# ---------------------------------------------------------------- the scale test
def test_the_big_catalog_is_repeatable_and_keeps_the_real_one(tmp_path, catalog):
    from evals.scale import make_big_catalog

    first = make_big_catalog(tmp_path / "a")
    second = make_big_catalog(tmp_path / "b")
    assert (first / "catalog.json").read_bytes() == (second / "catalog.json").read_bytes()
    big = type(catalog).load(first)
    assert len(big.providers) == 2000 and len(big.locations) == 500 and big.visit_types.keys() == catalog.visit_types.keys()
    for pid, p in catalog.providers.items():  # the real 50 doctors are unchanged
        assert big.providers[pid] == p
    new = [p for pid, p in big.providers.items() if pid not in catalog.providers]
    assert not [p for p in new if "garcia" in p.name.lower()]


def test_ours_gives_the_ai_the_same_size_of_instructions_on_any_catalog(tmp_path, catalog, patients):
    from evals.scale import make_big_catalog, stage_sizes

    big = type(catalog).load(make_big_catalog(tmp_path / "big"))
    normal_sizes, big_sizes = stage_sizes(catalog, patients), stage_sizes(big, patients)
    for stage, size in normal_sizes.items():
        assert abs(big_sizes[stage] - size) < 200, stage
