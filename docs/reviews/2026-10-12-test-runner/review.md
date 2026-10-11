# Independent review: the typed test runner (`backend/evals/`)

Reviewer: a fresh agent that did not write this code and has not seen the conversation that built it.
Date: 12 Oct 2026. Everything below was checked against the files in `/home/claude/review/repo/`.
No OpenAI calls were made. Line numbers are in the files as they are now.

A few words used below:
- **Pass** (as in "AI pass"): one request to the AI and its reply.
- **Scoring**: the code that decides whether a run passed (`evals/scoring.py`).
- **False pass / false fail**: the scoring says "pass" when the agent got it wrong, or "fail" when it got it right.
- **Ledger**: the spending record (`spending.jsonl`) behind the $7 stop.

**Summary: 15 findings. 3 high, 5 medium, 7 low.**

| # | Severity | One line |
| --- | --- | --- |
| R1 | High | A caller who says goodbye and hangs up in one line crashes the scoring; the paid run is lost and the next command pays for it again |
| R2 | High | The scale test's paid runs of our agent can never pass: they never see their own booking |
| R3 | High | The "promised staff follow-up" check fails good advice ("reach out to your own doctor") and misses many real promises |
| R4 | Medium | After a budget stop, the round-1 table can compare versions on different scenarios, and by the author's own estimates round 1 doesn't fit in $7 |
| R5 | Medium | "Handed off" is judged by the tool's name, not by what happened |
| R6 | Medium | Scenario 5 accepts a "New Patient Visit" as a yearly check-up |
| R7 | Medium | The naive versions differ from ours in more than "what the AI is given", so the "only difference" claim doesn't hold |
| R8 | Medium | The author's tests miss the two paths where R1 and R2 live; a few tests can't fail |
| R9 | Low | A turn stuck in a loop (more than 6 AI passes) isn't counted as a failure |
| R10 | Low | Scenario 3 ("near Downtown") also accepts the Midtown booking |
| R11 | Low | Scoring never checks whose name the booking is under |
| R12 | Low | Small ways spending can slip past the record or the $7 stop |
| R13 | Low | Windows: a temporary-folder clean-up error can lose a paid run; `.env` and console encodings |
| R14 | Low | AI-slop checklist items (comments that don't match, dead code, copies of the same thing) |
| R15 | Low | Small differences between the typed loop and the voice agent that don't change the numbers |

---

## 1. Part 1: the expected outcomes, worked out before opening `evals/`

I worked these out from `data/catalog.json`, `data/patients.json`, `data/location_extras.json`, the six policies, and decisions 27-28 only, and saved them before opening `scenarios.py`.

Facts from the data that matter:
- **Dr. Garcias:** prov_002 Dr. Maria Garcia (MD, Pediatrics, Mission Bay loc_000), prov_003 Dr. Maria Garcia (NP, Family Medicine, loc_002 North Beach / loc_005 Midtown / loc_007 Richmond), prov_008 Dr. Carlos Garcia (Family Medicine, loc_002 / loc_007). All take new patients. **None offers any Dermatology visit.**
- **Skin visits:** appt_027 Skin Cancer Screening and appt_028 Full Body Skin Exam need no referral and allow new patients. appt_026 Dermatology Consultation needs a referral; appt_029 Mole Removal needs a referral, is existing patients only and needs surgery; appt_030 Acne Follow-up is existing patients only; appt_031 Cosmetic Consultation is bookable but isn't a skin check. Dermatologists: prov_001 (loc_004, loc_007), prov_027 (loc_002, loc_004, loc_005, loc_006), prov_035 (loc_001, loc_007), all taking new patients; prov_048 is **not** taking new patients. No skin visit needs equipment.
- **Knee MRI (appt_065):** needs a Radiology referral, existing patients only, needs `imaging`. Only prov_014 (loc_000, loc_004) and prov_015 (loc_000, loc_005) offer it. Imaging is at loc_001, loc_004, loc_005 only; loc_000 has none.
- **James Wilson** (pat_001, 1984-03-12) is returning, with Radiology and Orthopedics referrals.
- **OB/GYN:** only prov_036 (loc_004) offers appt_040-044, and is **not** taking new patients.

| # | Caller | My expected outcome |
| --- | --- | --- |
| 1 | Lena Park, new, skin check, asks for "Dr. Garcia" | Tell her no Dr. Garcia does skin checks; **one booking**, visit **appt_027 or appt_028**, doctor **prov_001, prov_027 or prov_035**, at one of that doctor's own locations. Not prov_048 (not taking new patients), not appt_026/029/030/031. |
| 2 | Omar Haddad, new, knee MRI, no referral | **No booking.** appt_065 is blocked twice (referral, existing patients only); so is every other MRI/X-ray/CT. A hand-off isn't required unless he asks. |
| 3 | James Wilson, knee MRI near Downtown | **One booking of appt_065.** Valid doctor-place pairs: (prov_014, loc_004 Downtown) and (prov_015, loc_005 Midtown). "Near Downtown" points to **prov_014 at loc_004**, which has 19 open times in the window, so that's the strict answer; Midtown is valid by the rules but not what was asked. |
| 4 | James Wilson, Garcia skin check, then knee MRI anywhere | **Exactly one booking, appt_065**, at (prov_014, loc_004) or (prov_015, loc_005). No skin booking; Dr. Garcia must not carry over (no Garcia offers MRIs). |
| 5 | Priya Nair, new adult, yearly check-up with the family-medicine Dr. Maria Garcia | **One booking with prov_003** (not prov_002, the children's doctor, who also offers appt_002/003: a trap), visit **appt_002 Annual Physical or appt_003 Annual Wellness Visit**, at loc_002, loc_005 or loc_007 (the location must be settled, policy 6). |
| 6 | Sofia Reyes, new, annual well-woman exam with an OB/GYN | **No booking.** appt_041 is only offered by prov_036, who isn't taking new patients, and no one else offers any OB/GYN visit. When she asks for a person, **hand_off** should be called. |

### Comparison with `scenarios.py`

| # | Same? | Difference |
| --- | --- | --- |
| 1 | Same | `SKIN_CHECKS` and `DERMATOLOGISTS_FOR_NEW` match exactly; the location is checked by the rule re-check. |
| 2 | Same | `NOT_BOOKED`. (A hand-off would also pass, which I agree with.) |
| 3 | **Different** | `KNEE_MRI_PAIRS` accepts Midtown (prov_015, loc_005) for a caller who asked for "near Downtown". See R10. |
| 4 | Same | |
| 5 | **Different** | `CHECK_UPS` (scenarios.py:60) also accepts appt_000 New Patient Consultation and appt_001 New Patient Visit. The caller asks for "a yearly physical"; prov_003 offers both yearly visits to new patients, so there's no reason to accept a first visit. The docstring (scenarios.py:21-23) calls these "check-up visits", which they aren't. See R6. |
| 6 | Same | `HANDED_OFF`, and a booking fails it. |

The docstring's facts (scenarios.py:10-25) are otherwise all correct.

---

## 2. Findings

### R1 (High). A caller who says goodbye and hangs up in one line crashes the scoring; the paid run is lost and the next command pays for it again

**What's wrong.** When the AI-played caller replies with words plus `[HANG UP]` (for example "Thanks, goodbye! [HANG UP]"), the loop saves that turn as `{"caller": "Thanks, goodbye!", "agent": None}` (conversation.py:37). The scoring then does `turn.get("agent", {}).get(...)` (scoring.py:57 and again at 112). `.get("agent", {})` only uses `{}` when the key is *missing*; here the key is there with the value `None`, so it crashes with `AttributeError: 'NoneType' object has no attribute 'get'`.

**Why it matters.** In `run.py` the scoring runs (line 110) *before* the run is written to disk (line 111), and nothing catches the error, so:
1. the conversation has already been paid for (the ledger has it), but the run file is never written;
2. the whole command stops, and the results tables aren't rebuilt;
3. running the command again finds the run "not finished" and runs it again, paying again, and it can crash again the same way.

This is likely, not rare. Every persona ends with "thank them and say goodbye", and gpt-4o-mini often puts the goodbye and the `[HANG UP]` in the same reply. The naive versions never end the call themselves, so every naive run ends with the caller hanging up; ours does too whenever no booking or hand-off happens (scenario 2). `scale.py:194` calls the same scoring and has the same problem.

**Evidence.** `out/tests/test_review_evals.py::test_finding_R1_*`. The second test runs `run.one_run` with a stand-in for OpenAI: it crashes after recording $0.003 of spending, and no run file is written. The author's own `test_the_caller_hanging_up_ends_the_call` builds exactly this shape of run but never scores it.

**Fix.** In scoring.py use `(turn.get("agent") or {})` in both places. Also in `run.one_run`, write the transcript to disk before scoring, and catch a scoring error (save it in the run record) so that a scoring bug never throws away a paid conversation.

### R2 (High). The scale test's paid runs of our agent can never pass

**What's wrong.** `scale.run_ours_on_big` builds `Clinic(big, patients, Schedule(big))` with no bookings file (scale.py:187). `OurAgent.outcome()` reads bookings only from that file (agents.py:230-237); with no file it reports **0 bookings** even after a successful `confirm_booking`. Both scale scenarios expect one booking, so the scoring always says "Expected one booking, found 0": a fail, every time, after paying for it (about $0.30-0.80).

**Evidence.** `test_finding_R2_ours_on_a_clinic_without_a_bookings_file_still_reports_its_booking`: the card says `booked`, and `outcome()["bookings"]` is empty.

**Fix.** Give the scale run a temporary bookings file, as `run.one_run` does. Better still, have `OurAgent` record what `confirm_booking` saved (or keep the bookings in memory on the Clinic), so the outcome doesn't depend on a file being configured.

### R3 (High). The "promised staff follow-up" check fails good advice and misses many real promises

**What's wrong.** Decision 87 fails a run in which the agent *promises* a staff call-back without calling hand_off. The pattern (scoring.py:24-27) is a list of phrases, and only three should-match and three should-not-match sentences are tested. I tried 27 realistic sentences:

Wrongly flagged (false fail):
- "Please reach out to your own doctor for a referral." ("reach out to you" matches inside "reach out to **you**r")
- "Your doctor can follow up with you about the results."
- "Dr. Chen will follow up with you at your next visit."
- "Your doctor will be in touch about the results."
- "Would you like me to have a member of staff call you back?" (an offer, not a promise)
- "I can't book that, but a member of staff can call you back if you want." (an offer)
- "Let me check and get back to you in a moment."

Missed (false pass):
- "I'll have someone call you." / "I'll ask a colleague to give you a call."
- "Someone from the clinic will contact you." / "The front desk will call you tomorrow."
- "We will contact you to arrange it." / "Our scheduling team will ring you later today."
- "You'll get a call from one of our staff." / "I'll let the office know and they'll follow up."
- "I've passed your details on, and a nurse will phone you."

**Why it matters.** Scenario 2 (Omar's knee MRI) is built to make the agent say exactly the flagged kind of sentence: the persona asks "is there anything else I can do?", and the honest answers are "get a referral from your own doctor" or "I can have a member of staff call you back". Omar then declines and no hand-off happens, so a correct agent fails. This can move the headline pass rate for every version.

**Evidence.** `test_finding_R3_*` (14 cases, plus a whole scenario-2 run scored as a fail for good advice).

**Fix.** Don't decide this with a phrase list alone. Options, best first:
1. Only flag sentences that talk about the clinic's people ("staff", "team", "someone", "we", "colleague", "the office/clinic/front desk") making a future contact, and skip questions and "if you want" offers; then test many sentences that should and shouldn't match, as the checklist asks.
2. Or have the scorer list every flagged sentence in the results for a human to confirm, and count it as a fail only once confirmed.
3. At the very least fix `reach out to you\b` (word boundary) and drop `get back to you` and `follow up with you` unless the subject is staff.

### R4 (Medium). After a budget stop, the round-1 table can compare versions on different scenarios, and by the author's own estimates round 1 doesn't fit in $7

**What's wrong.** Round 1 runs scenario by scenario, so a stop leaves the last scenario done for some versions and not others. `build_results` then makes each version's row from whatever runs that version has (results.py:56, 71-74). So "Passed 3 of 5" for naive can sit next to "Passed 4 of 4" for ours in the same headline table, with tokens and costs averaged over different scenarios. The same happens if one version's run stops with an error.

This isn't hypothetical. With the starting guesses in run.py:58, round 1 is 6 × ($0.60 + $0.60 + $0.25 + $0.04) + $0.25 for the check-in run = **about $9.20**, more than the $7 stop. If a naive call really costs about $0.60, the two naive versions alone (12 calls) cost about $7.20. My own rough estimate is lower (about 11,000-12,000 input tokens per naive pass, mostly at the cached price, roughly $0.30 per naive call), but nobody knows until it runs.

**Evidence.** `test_finding_R4_round_1_rows_cover_the_same_scenarios`: naive "1 of 2" and ours "1 of 1" in one table.

**Fix.** In round 1, count a scenario only when every version has a finished run of it, and list the left-out ones under the table. Run `plan` first and compare its round-1 estimate with what's left under $7. If it doesn't fit, cut a scenario from round 1 up front rather than letting the stop decide. After the first few real runs, consider letting the measured cost replace the starting guess instead of the guess acting as a minimum (run.py:127).

### R5 (Medium). "Handed off" is judged by the tool's name, not by what happened

**What's wrong.** `hand_off_called` is true if the AI *asked* for a tool called hand_off (agents.py:130, 236, 424), whatever happened next. Two problems:
- **A refused hand-off counts.** If the AI sends a reason that isn't one of the three allowed, our tool refuses (`ok: false`) and the call isn't handed off, but scenario 6 still passes. The "promise without hand_off" check is also switched off for the whole call (scoring.py:93). A false pass.
- **A hand-off made by the code doesn't count.** `start_booking` hands the caller to staff itself when identity can't be confirmed (tools.py:317). The card says `handed_off`, the end stage tells the AI to say "a member of staff will call you back", but no hand_off tool was called. So the scoring flags a false promise, and in a hand-off scenario it says "hand_off was never called". A false fail.

The naive version's `_hand_off` (agents.py:417) accepts any reason, so the two versions aren't even judged the same way.

**Evidence.** `test_finding_R5_a_refused_hand_off_is_not_a_hand_off` and `test_finding_R5_a_hand_off_made_by_the_code_is_a_hand_off`.

**Fix.** Score on the outcome: ours `card.status == "handed_off"` (or "a hand-off happened at any point"), naive `status == "handed_off"`. Make naive's hand_off refuse a reason outside its list, the same way ours does.

### R6 (Medium). Scenario 5 accepts a "New Patient Visit" as a yearly check-up

**What's wrong.** `CHECK_UPS` (scenarios.py:60) includes appt_000 and appt_001. The caller asks for "a yearly physical"; the right bookings are appt_002 or appt_003, which prov_003 offers to new patients. A naive agent that books "New Patient Visit with Dr. Maria Garcia" (a natural slip for a new patient) passes. This is one of only six scenarios, so one false pass moves a version's pass rate by about 17 points.

**Evidence.** `test_finding_R6_a_new_patient_visit_is_not_a_yearly_check_up`.

**Fix.** `CHECK_UPS = {"appt_002", "appt_003"}`, and correct the docstring.

### R7 (Medium). The naive versions differ from ours in more than "what the AI is given", so the "only difference" claim doesn't hold

**What's wrong.** Decision 86 says that with the same data tools, "the only differences are 'everything pasted in' against 'small slices', and 'no checks' against 'checks'". The test plan says version 2 against 3 "shows what the context management itself adds". In the code there are other differences that move the numbers, in both directions:
- **Searching.** Naive's `find_open_times` takes **one doctor at a time** (agents.py:277-286). For "any dermatologist" or "Ramirez or Nguyen" the naive AI has to make one tool call per doctor, and each call is another full pass over about 11,000 tokens. Ours searches every valid doctor and place in one code call, ranks by distance and applies wishes. Naive's passes and tokens per call are pushed up by tool design, not only by the pasted catalog.
- **Ending the call.** Ours ends the call by itself after the goodbye. Naive has no way to end it, so when the caller says "thanks, bye" without `[HANG UP]`, naive spends one more full-catalog pass on "Goodbye!". That's a small extra charge on naive.
- **The other way:** ours has to spell back new patients' names letter by letter (decisions 59, 77), which adds turns and tokens that naive doesn't spend, and which the scoring never rewards (R11).

None of this is cheating, and decision 86's "same data" holds: same catalog, same schedule, same patient lookup, same caller AI, same persona style, same timing and costing code. But an interviewer who reads the tool list can fairly say "your naive search was deliberately clumsy".

**Fix.** Either give naive a `find_open_times` that takes a visit type and an optional doctor and returns times for every doctor who offers it (with no rule checks, so the comparison stays "checks against no checks"), or keep it and state the differences plainly next to the results table. Also report tokens per caller line, not only per call, so turn-count differences (spelling) are visible.

### R8 (Medium). The author's tests miss the two paths where R1 and R2 live; a few tests can't fail

All 39 pass (`python3 -m pytest -q -p no:cacheprovider tests/test_builder_evals.py`). They do test real behaviour for most of the loop: the stage wipe, the tool order, the second pass, the code read-back, the end stage, bad JSON, the budget stop, rate-limit waits, no-credit, and the naive tools. Gaps:
- Nothing runs `run.one_run` or `run_round` from start to finish with a stand-in OpenAI. That would have caught R1.
- Nothing runs `scale.run_ours_on_big` or checks `OurAgent.outcome()` without a bookings file (R2).
- `test_the_caller_hanging_up_ends_the_call` builds the exact run that crashes the scoring, but never scores it.
- The staff-promise tests have 3 positive and 3 negative sentences, none like the ones the scenarios provoke (R3).
- `build_results` and `_row` aren't tested (R4), and neither are the transcript writer, `most_spent`, or `finished`.
- No test for a tool that raises an exception inside OurAgent (the "failed in the code" path that scoring relies on).
- **Can't fail, or restate the code:** `test_prices` repeats the price table (it can't catch a wrong price). `test_the_rounds_match_decisions_84_and_87` repeats the settings. `test_every_tool_the_agent_file_uses_is_one_the_loop_offers` is already enforced by the builder when the agent file loads.

**Fix.** Add an end-to-end test of `one_run` with a fake client whose caller says "Bye! [HANG UP]", a scale-run test, and a staff-promise table of 20 or more realistic sentences. My tests in `out/tests/` can be used as a starting point.

### R9 (Low). A turn stuck in a loop isn't counted as a failure

When a turn needs more than 6 AI passes, the loop ends the turn and writes a note (agents.py:111). The scoring only fails "failed in the code" notes, so a looping agent can still pass. In a real call that would be a long silence. It also caps the "AI passes" figure. **Fix:** count it as a fail, or at least show the count in the results.

### R10 (Low). Scenario 3 ("near Downtown") also accepts the Midtown booking

`KNEE_MRI_PAIRS` is used for scenario 3, which asks for "near Downtown". prov_014 at Downtown has 19 open times, so the Midtown booking (prov_015, loc_005, about 1.9 km away) means the agent ignored the place. Ours ranks by distance and should pick Downtown; naive may not. **Fix:** `pairs={("prov_014","loc_004")}` for scenario 3 only, or keep both and report "nearest place chosen" as an extra column.

### R11 (Low). Scoring never checks whose name the booking is under

The rule re-check correctly uses the scenario's real caller (good). But it never checks that the saved booking names that caller: the right name for a new patient (decision 77's spelling work is never rewarded or checked), or `patient_id == pat_001` for James. "Lena Parks" passes. **Fix:** compare the saved name (or patient_id) with the scenario's caller.

### R12 (Low). Small ways spending can slip past the record or the $7 stop

The stop itself is sound: a check before every request (`check_room`, ai.py:86) with $0.10 kept back, a check before each conversation, and every reply written to `spending.jsonl` straight away, which is read back on every start. The prices are right: gpt-4o $2.50 / $1.25 cached / $10.00 output and gpt-4o-mini $0.15 / $0.075 / $0.60 per million tokens (checked on OpenAI's model pages today). One thing I couldn't confirm: which dated version the plain "gpt-4o" name points to. The 2024-08-06 and 2024-11-20 versions cost the prices above; only the old 2024-05-13 version costs more. It's worth checking the `model` field in one real reply.. Small gaps:
- **Unknown model:** the price is looked up *after* the request (budget.py:84, from ai.py:111), so an unpriced model is billed, then the run crashes, and that spend is never recorded. Look the price up before sending. (`test_finding_R12_*`)
- **Time-outs:** a 90-second client time-out (ai.py:51) counts as a connection error and is retried (ai.py:103). OpenAI may still bill the first attempt, and it isn't recorded. This is unlikely at these sizes.
- **No reply-length cap:** with no `max_tokens`, one reply could in theory cost more than the $0.10 kept back (about $0.19 for a runaway gpt-4o reply). Setting `max_tokens` on the caller's requests is harmless; on the agent's it would make it differ from the voice agent, so leave that alone.
- **Two runs at once** (for example `evals.run` and `evals.scale` in two windows) each keep their own running total, so together they can pass $7.
- The ledger lives inside the results folder. Deleting that folder to "start clean" also resets the $7 count.
- A half-written last line (power cut, Ctrl+C mid-write) stops every command with a JSON error. That's safe, but the message is unclear.
- **Rate limits:** handled, and the waits aren't timed. On a low-tier key (gpt-4o at 30,000 tokens a minute), each naive pass is about 11,000 tokens, so expect long waits; round 1 may take an hour or more.
- **No credit:** stops at once. A repeat after a stop carries on correctly, skipping finished runs; a run that stopped with an "error" is re-run (and re-paid) each time until the cause is fixed.

### R13 (Low). Windows

- `run.one_run` scores and saves the run *after* the `TemporaryDirectory` block closes (run.py:99-111). On Windows, if anything (an antivirus scan, the search indexer) briefly holds `bookings.jsonl`, the clean-up raises `PermissionError`, and the paid run is lost before it's saved. **Fix:** `TemporaryDirectory(ignore_cleanup_errors=True)` (Python 3.10+), or save before leaving the block.
- `.env`: in Windows PowerShell 5.1, `echo OPENAI_API_KEY=... > backend\.env` writes the file as UTF-16, which python-dotenv can't read. Create it in an editor saved as UTF-8 (or use `Set-Content -Encoding utf8`). If the key isn't found, the runner says so clearly.
- Printing: with `PYTHONUTF8=1` set as planned, printing agent sentences is safe. Without it, an unusual character in a failure reason could crash the print after the run was saved.
- Paths all use `pathlib`; file names have no colons; every file is read and written as UTF-8; times use `%A %B %I %p`, which Windows supports. No problems there.

### R14 (Low). AI-slop checklist items

- **Comments that don't match the code:** scoring.py:10 says staff promises are "only flagged, never acted on", but they fail the run. conversation.py:4 says a turn-limit call is "scored as not finished", but `turn_limit` is in `FINISHED` (it counts, as a fail). `evals/__init__.py:1` and results.py:58 say "three versions", but the tables have four rows.
- **Dead code:** `Ledger.room()` (budget.py:75) is never used. `STOPPED` (conversation.py:22) is never used.
- **The same thing in more than one place:** `GREETING` (agents.py:241) is a copy of the greeting in clinic_agent.json (if one changes, naive and ours greet differently; read it from the agent file). `_known` (agents.py:314) is a copy of `rules._known`. The "is this run finished" check is written again in scale.py:183 instead of using `run.finished`. "Up to 6 times" is in the tool description and also in `MAX_TIMES`.
- **Unexplained numbers:** `0.40` in scale.py:186; `1.3` in run.py:127 (it is explained in a comment).
- **Silent failures:** R5 (a refused hand-off counted as done), R9 (a stuck turn not counted).
- **Confusing names for the reader:** the results table has both "Passed" (scenario success) and "AI passes" (requests). Consider "AI requests" for the second.
- **Fragile text matching without should-not-match tests:** R3.

### R15 (Low). Small differences between the typed loop and the voice agent that don't change the numbers

For the record, everything I could find (none is likely to change the numbers):
- When the AI says something *and* calls a tool in one reply, the loop stores two messages; Pipecat probably stores one. Same words, a few tokens' difference.
- Building the next stage's instructions (`_enter`, which fills `{visit_types}` and `{options}`) isn't inside the timed part; in a call it is. A few milliseconds.
- If the AI asks for two tools at once (which shouldn't happen with parallel tool calls off), the loop runs only the first and notes it; Pipecat would run both.
- Timing is to the whole reply (no streaming), so it's slightly longer than a caller's real wait before the first words. This is documented, and the same for every version.
- The greeting: Pipecat Flows runs pre-actions before resetting the conversation, and its own comment (manager.py, `_update_llm_context`) warns that a reset can wipe text that a `tts_say` added. The builder's own `say` doesn't wait for the line to be spoken, so the greeting most likely joins the conversation *after* the reset (as the loop assumes). I couldn't confirm this without Pipecat's core code. Either way it's one short line.

---

## 3. What I checked and found fine

**The loop copies the voice agent (part A).** I loaded the real `agent_builder/builder.py` (with small stand-ins for the few Pipecat names it imports) and compared what it hands to Pipecat Flows with what `OurAgent` sends, stage by stage, on James Wilson's knee-MRI path (`out/tests/test_review_builder_parity.py`, which passes):
- The system instruction is the persona (or the stage's own role, if it has one), as Flows' `role_message` becomes the AI's system instruction.
- Each stage's instructions are filled from the booking card at the moment of the move, and are identical text.
- The conversation is wiped on every move (reset): the new stage's first request has only the system instruction and the new instructions.
- The tools are offered always-available first, then the stage's own, in the same order as Flows' `self._global_functions + node functions`.
- `parallel_tool_calls: false` is sent whenever tools are sent.
- After a tool that stays, there's a second AI pass that sees the tool's result.
- After a tool that moves, the new stage answers straight away.
- After `choose_option`, the code's read-back is the agent's turn, there's no second pass, the conversation keeps it (append, `respond_immediately: false`), and no new instructions are added.
- The greeting is said by the code and the AI waits (`respond_immediately: false`).
- The end stage gives one goodbye pass, then the call ends; a tool call there is noted (decision 50).
- A tool that crashes gives the AI `{"status": "error", ...}` and another pass, as Flows does, and the scoring counts it as a fail.

**Fairness (part B).** Every version uses the same caller AI (gpt-4o-mini) with the same persona and rules, the same fixed clinic time, a fresh schedule and a fresh temporary bookings file per run, the same request code (`OpenAIChat`), the same timing (rate-limit waits left out for everyone), and costs from OpenAI's own usage figures, including the cached-token discount. The naive versions get the same data (catalog, rules, map notes, visit notes) and the same patient lookup and schedule. Version 2 uses our real `check_booking`. Its instructions are a fair job description. Apart from R7, I found nothing that tilts the comparison.

**Scoring (part C).** Every saved booking is re-checked with `check_booking` for the scenario's *real* caller (not the agent's patient_id), on a fresh schedule, at the same clinic time (`test_ok_the_real_caller_decides_the_rules_not_the_naive_agents_patient_id`). "Expected one booking" catches double bookings. A hand-off scenario fails if anything is booked. The check-in run (decision 71) injects "Are you still there?" right after a successful read-back, adds it to the agent's conversation as the voice watch does, and fails only if the next agent turn calls `confirm_booking` (`test_ok_check_in_is_said_after_the_read_back_and_joins_the_conversation`).

**Budget (part D).** Apart from R12: the stop is checked before every request and every conversation, spending is remembered across runs, prices are right, "no credit" stops at once, a stop keeps what's finished, and repeating a command carries on rather than redoing finished runs (`test_ok_a_budget_stop_before_a_conversation_spends_nothing`).

**Scale (part E).** The big catalog is valid (it loads through the same checks), the same every time (fixed seed), keeps the real 50 doctors unchanged, gives new doctors their specialty's real menu, adds no Garcia, and is messy in realistic ways (repeated doctor names, random equipment and places). Its measurements are honest about what they are: `time_searches` times only `choose_visit_type` (the search), median of 20 runs, starting from a fresh schedule each time; `stage_sizes` counts characters of stage instructions on one path, without the persona or tool list (worth saying so in the write-up). The naive token count is free: the big catalog is about 765,000 characters, well over gpt-4o's 128,000-token limit, so OpenAI refuses it, and refusals aren't charged. Only R2 is wrong here.

**Windows (part H).** Apart from R13: paths, encodings and file names are fine.

---

## 4. Tests I wrote

In `/home/claude/review/out/tests/` (the author's files are untouched). Run them with:

```
cd /home/claude/review && python3 -m pytest -q -p no:cacheprovider out/tests
```

- `test_review_evals.py`: tests named `test_finding_R*` describe the **correct** behaviour and **fail today**. Each backs the finding in its name (R1, R2, R3, R4, R5, R6, R12). Tests named `test_ok_*` pass and record things checked and found fine.
- `test_review_builder_parity.py`: compares the voice agent's builder with the typed loop, stage by stage (passes).

Current result: 18 failed (all `test_finding_*`, each for the reason in its finding) and 5 passed.
