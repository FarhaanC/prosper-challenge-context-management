"""One typed call: the AI-played caller and an agent taking turns until the call ends.

The call ends when the caller hangs up, when the agent's end stage has said goodbye,
or after MAX_CALLER_TURNS caller lines (a stuck call, scored as not finished). Running
out of budget or credit ends it too; such a run is kept, marked, and left out of the
results.
"""

from __future__ import annotations

import traceback

from call.silence import CHECK_IN

from .ai import OutOfCredit
from .budget import BudgetStop
from .caller import CallerAI, heard

MAX_CALLER_TURNS = 30

FINISHED = ("caller_hung_up", "agent_ended", "turn_limit")   # the run counts in the results
STOPPED = ("budget_stop", "out_of_credit", "error")          # it doesn't


def run_conversation(agent, caller: CallerAI, check_in_after_read_back: bool = False,
                     max_turns: int = MAX_CALLER_TURNS) -> dict:
    record = {"greeting": None, "turns": [], "ended_by": "turn_limit", "stopped_because": ""}
    try:
        first = agent.start()
        record["greeting"] = first.to_dict()
        agent_said = heard(first)
        check_in_done, next_is_after_check_in = False, False
        for _ in range(max_turns):
            line, hung_up = caller.next_line(agent_said)
            if hung_up:
                if line:
                    record["turns"].append({"caller": line, "agent": None})
                record["ended_by"] = "caller_hung_up"
                break
            turn = agent.respond(line)
            entry = {"caller": line, "agent": turn.to_dict(), "after_check_in": next_is_after_check_in}
            next_is_after_check_in = False
            agent_said = heard(turn)
            if agent.ended:
                record["turns"].append(entry)
                record["ended_by"] = "agent_ended"
                break
            if (check_in_after_read_back and not check_in_done
                    and any(t["tool"] == "choose_option" and t["result"].get("ok") for t in turn.tools)):
                # The caller stays silent after the read-back; the silence watch says the check-in (decision 64).
                agent.add_spoken_line(CHECK_IN)
                agent_said = f"{agent_said} ... {CHECK_IN}"
                entry["check_in_said"] = CHECK_IN
                check_in_done, next_is_after_check_in = True, True
            record["turns"].append(entry)
    except BudgetStop as e:
        record["ended_by"], record["stopped_because"] = "budget_stop", str(e)
    except OutOfCredit as e:
        record["ended_by"], record["stopped_because"] = "out_of_credit", str(e)
    except Exception:  # a bug in the loop: keep the transcript so far, and stop the whole run
        record["ended_by"], record["stopped_because"] = "error", traceback.format_exc()
    record["outcome"] = agent.outcome()
    record["totals"] = totals(record, caller)
    return record


def totals(record: dict, caller: CallerAI) -> dict:
    agent_turns = [t["agent"] for t in record["turns"] if t.get("agent")]
    if record["greeting"]:
        agent_turns.insert(0, record["greeting"])
    answered = [t["seconds"] for t in agent_turns if t["passes"]]
    return {
        "agent_input_tokens": sum(t["input_tokens"] for t in agent_turns),
        "agent_cached_tokens": sum(t["cached_tokens"] for t in agent_turns),
        "agent_output_tokens": sum(t["output_tokens"] for t in agent_turns),
        "agent_passes": sum(t["passes"] for t in agent_turns),
        "agent_cost": round(sum(t["cost"] for t in agent_turns), 6),
        "slowest_reply_seconds": round(max(answered), 3) if answered else 0.0,
        "caller_lines": sum(1 for t in record["turns"] if t.get("caller")),
        "caller_cost": round(caller.cost, 6),
    }
