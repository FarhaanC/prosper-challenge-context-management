# Triage: the independent review of the test runner (12 Oct)

The reviewer was one fresh agent (process rule P5: one check, kept proportionate). It never saw the build conversation or the build log. It was given the code, `docs/decisions.md`, `docs/process.md`, `INTERFACE.md`, the test plan (`plan-given-to-the-reviewer.md`), and Pipecat Flows' own source. It made no OpenAI calls. Its report is in `review.md`, and its tests are in `reviewer-tests/`, unedited.

**Before reading our code**, the reviewer worked out each scenario's expected answer from the raw catalog. Four of the six matched ours exactly. The other two (scenarios 3 and 5) became R10 and R6.

## Decisions on each finding

| # | Finding | Severity | Decision | What was done |
| --- | --- | --- | --- | --- |
| R1 | A caller who says goodbye and hangs up in the same line crashed the scoring, so a paid run was lost and paid for again | High | **Fix** | Scoring handles a turn with no agent reply. Each run is now saved *before* it's scored. If scoring ever fails, the error is kept in the run, the run isn't paid for again, and the new `rescore` command scores the saved runs again for free. |
| R2 | The scale test's paid runs could never pass, because they never saw their own booking | High | **Fix** | Our agent's outcome now comes from the booking card (decision 20 says to score against the card), not from a file. |
| R3 | The "promised a staff follow-up" check flagged good advice ("reach out to your own doctor") and missed real promises | High | **Fix; Farhaan to confirm** | The check now looks at one sentence at a time. It needs the clinic's side (staff, someone, the team, the office, we, they) promising future contact, and skips questions and offers ("would you like…", "…if you want"). It's tested on 13 sentences that should match and 13 that shouldn't. Every flagged sentence is quoted in the results, so a person can check it. |
| R4 | After a budget stop, the round-1 table could compare versions on different scenarios | Medium | **Fix; Farhaan to confirm** | Round 1's table only counts scenarios every version has finished, and names any left out. Once a version has run, the money check uses that version's real cost (plus 30%) instead of the first guess. `plan` warns when a round may not fit under the stop. |
| R5 | A hand-off was judged by the tool's name, not by what happened | Medium | **Fix** | It's now judged by the outcome: the card (ours) or the call (naive) says "handed off". The naive hand_off refuses the same reasons ours refuses. |
| R6 | Scenario 5 accepted a first visit as a "yearly check-up" | Medium | **Fix; Farhaan to confirm** | Only Annual Physical (appt_002) and Annual Wellness Visit (appt_003) count. |
| R7 | The naive versions' search could only look at one doctor at a time, which made them look worse than they are | Medium | **Fix; Farhaan to confirm (decision 89)** | Naive's find_open_times can now leave out the doctor and get times for every doctor the catalog lists for that visit, soonest first, with no rule checks. The other differences (ours spells names back; ours ends the call itself) are stated next to the results table. |
| R8 | Missing tests on the paths where R1 and R2 were; some tests can't fail | Medium | **Fix** | 36 new builder tests (74 in all), including a whole paid run with a stand-in for OpenAI, a scoring failure being kept, the booking without a file, a tool failing in our code, the round-1 table and the staff-promise sentences. One test that repeated a load-time check was removed. |
| R9 | A turn stuck in a loop didn't count as a failure | Low | **Fix** | It's now a fail. |
| R10 | Scenario 3 ("near Downtown") also accepted the Midtown booking | Low | **Fix; Farhaan to confirm** | Scenario 3 now expects Dr. Ramirez at Downtown. Scenario 4 ("any place") still accepts either valid pair. |
| R11 | Scoring never checked whose name the booking is under | Low | **Fix; Farhaan to confirm** | The booking must be under the scenario's caller (the record's name for James Wilson, the name given for new patients). Capitals and extra spaces don't matter. |
| R12 | Small ways spending could slip past the $7 stop | Low | **Fix (mostly)** | An unpriced model is refused before anything is sent. The caller's replies are capped at 200 tokens (the agents are left as in the voice agent). A damaged line in the spending record now gives a clear message. **Won't fix:** two commands running at once each keep their own total (we only ever run one at a time), and a time-out might be billed but not recorded (unlikely at these sizes). |
| R13 | Windows: a temporary-file clean-up error could lose a paid run | Low | **Fix** | The temporary folder ignores clean-up errors, and the run is saved first anyway (R1). The `.env` note is already covered: the runner says clearly when the key isn't found. |
| R14 | AI-slop items | Low | **Fix** | Comments now match the code. Unused code (`Ledger.room`, `STOPPED`, `tools_called`, `_known`) was removed. The naive greeting is read from the agent file. The scale test reuses `run.finished`, `run.save` and `run.add_score`. The magic numbers have names (`MARGIN`, `ONE_SCALE_RUN`). "Passed" is renamed "Scenarios passed" so it isn't confused with "AI passes". |
| R15 | Small differences between the typed loop and a voice call | Low | **Won't fix; written down** | They're listed under the results table ("How these typed calls differ from a voice call"). None changes the numbers. |

**Nothing was disputed.** Every finding was agreed, so no verifier was needed (process step 6).

## Proof (process step 7)

- The reviewer's 23 tests were run unchanged against the fixed code: **23 of 23 pass**. Before the fixes, 18 failed, each for its finding. The only change was pointing their settings file (`conftest.py`) at the folder holding the fixed code.
- Builder tests: **74 of 74 pass**.

## For Farhaan to confirm before the paid runs

These change what counts as a pass (the test plan), not how the agent behaves:
- **R3:** the new staff-promise check.
- **R4:** round 1 compares only scenarios every version finished.
- **R6:** only the yearly visits count for scenario 5.
- **R7 (decision 89):** the naive search can look across all doctors.
- **R10:** scenario 3 must be Downtown.
- **R11:** the booking must be under the caller's name.

Each is a one-line change if he'd rather not, and `rescore` re-scores any saved runs for free.
