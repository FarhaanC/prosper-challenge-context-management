# Triage: review of decisions 64, 66 and 67

Build reviewed: `14dd04e`. Review: `review.md` (one fresh reviewer, Farhaan's choice for these
three small changes; no separate tester). Farhaan chose on 11 Oct: fix R1–R8 and R10, replace the
text-only tests (R9) with simulations of R1–R3, and carry R11 into the note for the text-mode loop.

| # | Finding (short) | Severity | Decision | What was done |
| --- | --- | --- | --- | --- |
| R1 | A noise with no words switched the silence count off until the agent next spoke, so a pocket dial ran to the 10-minute cap | high | **Fix** | `agent_builder/call_watch.py`: when a caller turn ends with no words, Pipecat's own silence timer is started again as if the agent had just finished speaking (so speech and tool calls still cancel it). Words after a check-in are what bring the full 20 s back; a noise no longer cancels a pending goodbye. Tests drive Pipecat's real timer: noise then silence; noise after the check-in; words after the check-in. |
| R2 | Talking over a line the code says (Flows' `tts_say`) jammed Flows; an interrupted greeting left stage 1 with no instructions or tools | high (from decision 58; 66 used the same mechanism) | **Fix** | Reproduced before fixing (`evidence/sim_greeting.py`). The builder now says every code-spoken line (an agent file's `tts_say`, and `say_now`) with its own `say` action, which only queues the line and waits for nothing. Test: a real pipeline with a stand-in voice, greeting interrupted part-way: stage 1 still gets its instructions and `start_booking`. Shown to fail on the old behaviour. |
| R3 | The 10-minute timer was only stopped when the caller hung up, so a normal booked call got a false "time limit" line in its log 10 minutes later | medium | **Fix** | `bot.py` stops it in a `finally` around the call, however the call ends. Test: a stopped timer says and logs nothing. |
| R4 | "Are you still there?" then "Yes" could be read as a yes to the booking | medium (mechanism verified; the AI's choice unverified) | **Fix** (Farhaan approved the persona line) | Persona: "If you've just asked 'Are you still there?', a yes only means the caller is still on the line: ask your last question again before acting on it." To check in Saturday's AI-played callers. |
| R5 | The tool result's `said` ("don't repeat it") sat one letter from the persona's `say` ("speak this"), and claimed the read-back was said before it was | low | **Fix** | Result field renamed `note`, worded without timing: "The code is reading the read_back to the caller…: don't repeat it." The call log keeps `said` (what the code actually queued). |
| R6 | The time-limit goodbye could follow a booking's own goodbye | low | **Fix** | `CallWatch.on_time_limit(call_finished=...)`: no time-limit goodbye once the call is booked or handed to staff. Test added. |
| R7 | `_say_and_wait` copied how a stage's role and tools are built | low | **Fix** | One helper, `_role_and_functions`, used by both. |
| R8 | A tool outcome with both a move and a sentence would silently drop the sentence | low | **Fix** | `Outcome` refuses the pair. Test added. |
| R9 | The new tests checked text, not behaviour | low–medium | **Fix** | String-search test for bot.py's wiring replaced by simulations (R1–R3 above); the read-back test checks meaning (the read-back, then a question) not the exact wording; the "only choose_option speaks" test now runs every tool. One small text check of bot.py stays (that the cap is stopped in `finally`). |
| R10 | `silence.py`'s description promised "anything the caller says resets the count" | low | **Fix** | Re-worded to match: counted from when the agent stops speaking; words reset it; a noise doesn't. |
| R11 | The typed test loop must copy `say_now` (no second AI pass after choose_option) | low (no loop yet) | **Fix when the loop is built** | Spec-change note below; the loop adds `say_now` as the agent's turn and skips the second pass. |

## The one failing independent test

`tests_independent/test_voice_agent_builder.py::test_choose_option_handler_stays` asserts the
choose_option handler returns no node. Decision 66 changes exactly that (it returns the same
stage, with the read-back said by the code). **Proved, not claimed (P3):** a throwaway adapter that
undoes only `_say_and_wait` (returns no node) makes the tester's unchanged file pass, 31 of 31.
The test itself was not edited (P2).

## Spec-change note for the next fresh tester (and the text-mode loop)

- `choose_option`: `outcome.say_now` is "To confirm: <read_back> Would you like me to book it?",
  said by the code. Through the builder, the handler returns `(result, node)`: the same stage,
  conversation kept (APPEND), no new instructions, the sentence as a `say` pre-action, and
  `respond_immediately` false. The result has `read_back` and a `note` telling the AI not to repeat it.
- An agent file's `tts_say` actions are said with the builder's `say` action (same text).
- The text-mode loop: when a tool returns `say_now`, add it as the agent's turn and don't run
  the second AI pass; wait for the caller's next line.
- The call log has `silence` and `time_limit` events (bot.py), and a tool line may carry `said`.

## Tests after the fixes

Builder: 403 pass. Independent: 3,479 of 3,480 pass; the one failure is above.
