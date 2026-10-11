"""Reviewer's tests for backend/evals/ (see review.md for the finding each one backs).

test_finding_*  : the correct behaviour; FAILS on the code as reviewed.
test_ok_*       : checked and fine; passes.
Nothing here calls OpenAI.
"""

import json
from datetime import datetime
from types import SimpleNamespace as NS

import pytest

from call import Clinic
from clinic import Schedule
from evals import run as run_module
from evals.agents import NaiveAgent, OurAgent
from evals.ai import OpenAIChat, Reply, ToolCall
from evals.budget import Ledger, Usage
from evals.caller import CallerAI
from evals.conversation import run_conversation
from evals.results import build_results
from evals.scenarios import BY_ID
from evals.scoring import STAFF_PROMISE, score

NOW = datetime(2026, 10, 13, 9, 0)
JAMES = {"full_name": "James Wilson", "returning": True, "date_of_birth": "1984-03-12",
         "visit_description": "knee MRI", "specialty": "Radiology"}


class ScriptedAI:
    """Plays the AI from a script: a reply text, or (text, tool, args)."""

    def __init__(self, steps):
        self.steps = list(steps)
        self.requests = []

    def reply(self, messages, tools=None, one_tool_at_a_time=True):
        self.requests.append({"messages": json.loads(json.dumps(messages)), "tools": tools})
        step = self.steps.pop(0)
        if isinstance(step, str):
            return Reply(step, [], Usage(100, 0, 10), 0.01, 0.0)
        text, name, args = step
        return Reply(text, [ToolCall(f"c{len(self.requests)}", name, json.dumps(args))], Usage(100, 0, 10), 0.01, 0.0)


def _outcome(**kw):
    base = {"status": "in_progress", "bookings": [], "hand_off_called": False, "name_confirmed": None}
    base.update(kw)
    return base


def _run(outcome, said=(), extra_turns=()):
    turns = [{"caller": "hi", "agent": {"said": list(said), "tools": [], "problems": []}}] + list(extra_turns)
    return {"ended_by": "caller_hung_up", "outcome": outcome, "turns": turns}


def _slot(catalog, provider, location, minutes):
    return next(Schedule(catalog).iter_open_slots(provider, location, minutes, NOW)).isoformat()


# ---------------------------------------------------------------- R1: a goodbye said with [HANG UP] crashes scoring
def test_finding_R1_scoring_a_call_where_the_caller_says_goodbye_and_hangs_up(catalog, patients):
    # conversation.py stores {"caller": "Thanks, bye!", "agent": None} when the caller hangs up WITH words.
    run = _run(_outcome(), said=["You'd need a referral first."],
               extra_turns=[{"caller": "Okay, thanks. Goodbye!", "agent": None}])
    result = score(BY_ID["knee_mri_new_patient"], run, catalog, patients, NOW)  # AttributeError today
    assert result["passed"]


class FakeClient:
    """Stands in for OpenAI's client: returns the scripted texts in order."""

    def __init__(self, texts):
        self.texts = list(texts)
        self.chat = NS(completions=NS(create=self.create))

    def create(self, **params):
        text = self.texts.pop(0)
        usage = NS(prompt_tokens=1000, completion_tokens=20, prompt_tokens_details=NS(cached_tokens=0))
        return NS(choices=[NS(message=NS(content=text, tool_calls=None))], usage=usage)


def test_finding_R1_one_paid_run_is_saved_when_the_caller_says_goodbye_with_hang_up(tmp_path, monkeypatch, catalog,
                                                                                   patients):
    """The whole path of `python -m evals.run`: the conversation is paid for, then scoring crashes, so
    the run file is never written; the next command runs (and pays for) the same conversation again."""
    monkeypatch.setattr(run_module, "RESULTS_DIR", tmp_path)
    ledger = Ledger(tmp_path / "spending.jsonl")
    client = FakeClient(["Hi, I need a knee MRI.",                  # caller
                         "I'm sorry, you'd need a referral first.",  # naive agent
                         "Okay, thank you. Goodbye! [HANG UP]"])     # caller hangs up WITH words
    scenario = BY_ID["knee_mri_new_patient"]
    try:
        run_module.one_run(scenario, "naive", 1, client, ledger, catalog, patients)
    except Exception as e:  # noqa: BLE001 - the point of the test
        pytest.fail(f"one_run crashed after spending ${ledger.spent:.4f}: {type(e).__name__}: {e}")
    assert run_module.finished(run_module.run_path("naive", scenario, 1))


# ---------------------------------------------------------------- R2: the scale test's paid runs can never pass
def test_finding_R2_ours_on_a_clinic_without_a_bookings_file_still_reports_its_booking(catalog, patients):
    # evals/scale.py run_ours_on_big builds Clinic(big, patients, Schedule(big)) with no bookings_file.
    clinic = Clinic(catalog, patients, Schedule(catalog))
    ai = ScriptedAI([("One moment.", "start_booking", JAMES), "The knee MRI?",
                     ("Great.", "choose_visit_type", {"visit_type_id": "appt_065"}), "Two options.",
                     ("", "choose_option", {"option_id": "1"}), ("", "confirm_booking", {}), "Booked. Goodbye."])
    agent = OurAgent(ai, clinic, NOW)
    agent.start()
    agent.respond("James Wilson, 1984-03-12, knee MRI.")
    agent.respond("Yes, the knee MRI.")
    agent.respond("The first one.")
    agent.respond("Yes.")
    assert agent.session.card.status == "booked"
    assert len(agent.outcome()["bookings"]) == 1  # 0 today, so scoring says "Expected one booking, found 0"


# ---------------------------------------------------------------- R3: the staff-promise pattern
@pytest.mark.parametrize("line", [
    "Please reach out to your own doctor for a referral.",       # "reach out to you" inside "to your"
    "Your doctor can follow up with you about a referral.",
    "Would you like me to have a member of staff call you back?",  # an offer, not a promise
    "Let me check and get back to you in a moment.",
])
def test_finding_R3_ordinary_or_offering_lines_are_not_promises(line):
    assert not STAFF_PROMISE.search(line)


@pytest.mark.parametrize("line", [
    "I'll have someone call you.",
    "Someone from the clinic will contact you.",
    "We will contact you to arrange it.",
    "Our scheduling team will ring you later today.",
    "You'll get a call from one of our staff.",
])
def test_finding_R3_real_promises_are_spotted(line):
    assert STAFF_PROMISE.search(line)


def test_finding_R3_the_new_patient_mri_scenario_fails_for_good_advice(catalog, patients):
    run = _run(_outcome(), said=["I'm sorry, a knee MRI needs a referral and is for existing patients. "
                                 "Please reach out to your own doctor for a referral, then call us back."])
    assert score(BY_ID["knee_mri_new_patient"], run, catalog, patients, NOW)["passed"]


# ---------------------------------------------------------------- R5: hand-off judged by tool name, not by outcome
def test_finding_R5_a_hand_off_made_by_the_code_is_a_hand_off(catalog, patients):
    # start_booking hands a caller to staff itself (identity can't be confirmed): status handed_off, and the
    # end stage tells the AI to say a member of staff will call back. No hand_off tool call is made.
    run = _run(_outcome(status="handed_off"), said=["A member of staff will call you back about this. Goodbye."])
    assert score(BY_ID["knee_mri_new_patient"], run, catalog, patients, NOW)["passed"]


def test_finding_R5_a_refused_hand_off_is_not_a_hand_off(catalog, patients, tmp_path):
    clinic = Clinic(catalog, patients, Schedule(catalog), bookings_file=tmp_path / "b.jsonl")
    ai = ScriptedAI([("One moment.", "hand_off", {"reason": "the caller is upset"}),  # not one of the 3 reasons
                     "A member of staff will call you back."])
    agent = OurAgent(ai, clinic, NOW)
    agent.start()
    turn = agent.respond("Can I talk to a person?")
    assert turn.tools[0]["result"]["ok"] is False and agent.session.card.status == "in_progress"
    run = {"ended_by": "caller_hung_up", "outcome": agent.outcome(),
           "turns": [{"caller": "Can I talk to a person?", "agent": turn.to_dict()}]}
    result = score(BY_ID["obgyn_new_then_person"], run, catalog, patients, NOW)
    assert not result["passed"]  # passes today: hand_off "was called", and the false promise is excused too


# ---------------------------------------------------------------- R6: scenario 5 accepts a first visit as a "yearly physical"
def test_finding_R6_a_new_patient_visit_is_not_a_yearly_check_up(catalog, patients):
    booking = {"visit_type_id": "appt_001", "provider_id": "prov_003", "location_id": "loc_005",
               "start": _slot(catalog, "prov_003", "loc_005", 30)}
    run = _run(_outcome(status="booked", bookings=[booking]))
    assert not score(BY_ID["maria_garcia_checkup"], run, catalog, patients, NOW)["passed"]


# ---------------------------------------------------------------- R4: round-1 table compares different scenario sets
def _saved_run(results_dir, version, scenario_id, passed):
    path = results_dir / "runs" / version / f"{scenario_id}__run1.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    totals = {"agent_input_tokens": 1000, "agent_cached_tokens": 0, "agent_output_tokens": 10, "agent_passes": 5,
              "agent_cost": 0.01, "slowest_reply_seconds": 1.0, "caller_lines": 5, "caller_cost": 0.001}
    path.write_text(json.dumps({"version": version, "scenario": scenario_id, "title": scenario_id, "run": 1,
                                "ended_by": "caller_hung_up", "greeting": None, "turns": [], "totals": totals,
                                "score": {"passed": passed, "reasons": [] if passed else ["x"], "bad_bookings": 0}}))


def test_finding_R4_round_1_rows_cover_the_same_scenarios(tmp_path):
    # A budget stop (or an error) part-way through round 1: naive has a scenario that ours doesn't.
    _saved_run(tmp_path, "naive", "garcia_skin_check", True)
    _saved_run(tmp_path, "naive", "knee_mri_new_patient", False)
    _saved_run(tmp_path, "ours", "garcia_skin_check", True)
    out = build_results(tmp_path, Ledger(tmp_path / "spending.jsonl")).read_text(encoding="utf-8")
    rows = [line for line in out.splitlines() if line.startswith("| 1. Naive") or line.startswith("| 3. Ours")]
    counts = {line.split("|")[2].strip().split(" of ")[1] for line in rows[:2]}
    assert len(counts) == 1, rows  # today: "1 of 2" against "1 of 1", in the same table


# ---------------------------------------------------------------- budget details
def test_finding_R12_an_unpriced_model_is_refused_before_it_is_paid_for(tmp_path):
    calls = []

    class Client(FakeClient):
        def create(self, **params):
            calls.append(params)
            return super().create(**params)

    chat = OpenAIChat(Client(["hi"]), "gpt-4.1", Ledger(tmp_path / "s.jsonl"), "t", say=lambda _: None)
    with pytest.raises(ValueError):
        chat.reply([{"role": "user", "content": "x"}])
    assert calls == []  # today the request is sent (and billed), then the price lookup fails: spend not recorded


# ---------------------------------------------------------------- checked and fine
def test_ok_a_budget_stop_before_a_conversation_spends_nothing(tmp_path, monkeypatch, catalog, patients):
    monkeypatch.setattr(run_module, "RESULTS_DIR", tmp_path)
    ledger = Ledger(tmp_path / "spending.jsonl", stop_at=0.05)
    record = run_module.one_run(BY_ID["knee_mri_new_patient"], "naive", 1, FakeClient([]), ledger, catalog, patients)
    assert record["ended_by"] == "budget_stop" and ledger.spent == 0


def test_ok_the_real_caller_decides_the_rules_not_the_naive_agents_patient_id(catalog, patients, tmp_path):
    # Version 1 saves whatever the AI sends; scoring re-checks it for the scenario's real caller.
    clinic = Clinic(catalog, patients, Schedule(catalog))
    start = _slot(catalog, "prov_014", "loc_004", 45)
    ai = ScriptedAI([("", "book_appointment", {"patient_name": "Omar Haddad", "patient_id": "pat_001",
                                               "visit_type_id": "appt_065", "provider_id": "prov_014",
                                               "location_id": "loc_004", "start": start}), "Booked."])
    agent = NaiveAgent(ai, clinic, NOW, checks=False)
    agent.start()
    turn = agent.respond("Yes")
    run = {"ended_by": "caller_hung_up", "outcome": agent.outcome(),
           "turns": [{"caller": "Yes", "agent": turn.to_dict()}]}
    result = score(BY_ID["knee_mri_new_patient"], run, catalog, patients, NOW)
    assert not result["passed"] and result["bad_bookings"] == 1


def test_ok_check_in_is_said_after_the_read_back_and_joins_the_conversation(catalog, patients, tmp_path):
    clinic = Clinic(catalog, patients, Schedule(catalog), bookings_file=tmp_path / "b.jsonl")
    ai = ScriptedAI([("One moment.", "start_booking", JAMES), "The knee MRI?",
                     ("Great.", "choose_visit_type", {"visit_type_id": "appt_065"}), "Two options.",
                     ("", "choose_option", {"option_id": "1"}),
                     "Sorry, just to check: would you like me to book it?",
                     ("", "confirm_booking", {}), "Booked. Goodbye."])
    caller = CallerAI(ScriptedAI(["James Wilson, 1984-03-12, knee MRI.", "Yes.", "The first one.", "Yes.",
                                  "Yes, book it."]), "")
    run = run_conversation(OurAgent(ai, clinic, NOW), caller, check_in_after_read_back=True)
    result = score(BY_ID["check_in_after_read_back"], run, catalog, patients, NOW)
    assert result["passed"], result
