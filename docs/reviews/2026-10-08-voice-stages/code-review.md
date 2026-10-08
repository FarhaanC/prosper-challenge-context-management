# Independent code review: voice stages and tools (v0.2.0 candidate, 8 Oct)

Reviewer: a fresh agent that never saw the build conversation or the build log.
Scope: `backend/call/`, `backend/agent_builder/`, `backend/clinic_agent.json`, `backend/bot.py`, `backend/tests/test_builder_call_tools.py`, plus how they use `backend/clinic/`.
Method: read the plan, decisions 43 to 49, the process doc and all of this step's code; read the Pipecat Flows 1.4.0 and Pipecat 1.4.0 source that the code relies on; wrote probe scripts to prove findings (in `review-probes/`, run from `backend/` with `python3 ../docs/reviews/2026-10-08-voice-stages/review-probes/<file>`). No code, test or agent file was changed.

**Results of running things**
- Whole test suite: **3167 passed** (2 min 16 s). This step's file: **43 passed**.
- pyflakes on `call/`, `agent_builder/`, `bot.py`, `tests/test_builder_call_tools.py`: **clean**.
- Fuzzing every tool with odd but likely values from the AI (probe 4): **no crashes**.

Severity: **high** = wrong booking, crash, or a broken live call; **medium** = likely confusion or a real gap; **low** = tidiness.

---

## High

### R1. The AI is never told the year, but must send dates as YYYY-MM-DD. A wrong guess gets a refusal that contradicts itself (high)
**Where:** `call/session.py:145` (`_fill_today`), `call/tools.py:122` and `:447` (day field descriptions), `clinic_agent.json` (every stage starts with `Now: {today}`).

**What's wrong:** `{today}` fills in as `Tuesday 6 October at 9 AM (clinic time, San Francisco)`, with no year. The `days` field asks for "a date YYYY-MM-DD" when the caller names a date ("the 15th"). gpt-4o has to guess the year, and its own sense of "now" is a year or more behind 2026. The refusal that comes back doesn't mention the year either, so it reads as nonsense:

```
(a) {today} = 'Tuesday 6 October at 9 AM (clinic time, San Francisco)'
    change_choice(time, days=['2024-10-15']) -> {'ok': False, 'error': 'Tuesday 15 October is outside the booking window (6 October to 20 October).'}
    change_choice(time, days=['2025-10-15']) -> {'ok': False, 'error': 'Wednesday 15 October is outside the booking window (6 October to 20 October).'}
```
(probe `p7_year_and_stage_names.py`)

**Live call:** the caller says "Can I come in on the 15th?" The AI sends `2024-10-15` and is told "15 October is outside the booking window (6 October to 20 October)". From there the AI either loops on guesses or tells the caller something false ("we can't book the 15th"). The same thing happens through `start_booking` and `choose_visit_type`, where a refused day also blocks the whole call, including identifying the caller, until the AI drops the day.

**Fix:** put the year in `{today}` (for example "Tuesday 6 October 2026") and the year in the window message ("6 to 20 October 2026"). Better still, accept a month-day date with no year and let the code pick the year that falls inside the window, since the code already knows the window. Add a test that sends a wrong-year date.

### R2. If the AI calls a tool in the end stage instead of speaking, the call hangs up in silence (high if it happens; likely enough to fix now)
**Where:** `agent_builder/builder.py:116` (end node gets `end_conversation`), `clinic_agent.json` persona and end node, `call/tools.py:368` (hand-off wording) and the `hand_off` description.

**What's wrong (checked in the source):**
- Flows adds the global tools to every node, including the end node (`pipecat_flows/manager.py:662`). Probe 3 shows the end-stage request offers `answer_question`, `change_choice` and `hand_off`.
- The end node's `end_conversation` post-action queues an `EndFrame` right after the `LLMRunFrame` (`manager.py:720`, `actions.py:334-359`). The OpenAI service handles the run inline (`services/openai/base_llm.py:561-565`), so if the AI's reply is spoken text, the goodbye is said before the end. But if the reply is a **tool call**, the call runs in a background task, the `EndFrame` arrives, `LLMService.stop()` cancels the function runner (`services/llm_service.py:473-482`), and nothing more is said.
- Several things push the AI toward a tool here: the persona says "**Use a tool to move the conversation forward**" (it applies to every stage, the end stage included). After a hand-off, the end instruction says "Tell the caller you're **putting them through to a member of staff**", and the `hand_off` tool's description begins "**Put the caller through to a member of staff**".

**Live call:** the caller asks for a person. The AI calls `hand_off` and moves to the end stage. Given the instruction "tell the caller you're putting them through", plus a tool whose description is exactly that, the AI may call `hand_off` again. The call then ends with no words at all. After a booking, a caller's last question ("what's the address again?") could lead to `answer_question`, and again the call hangs up without the confirmation.

I couldn't prove that gpt-4o will actually do this without a live model. The shutdown order above is proven from the source.

**Fix (any of these):**
- Don't use the AI in the end stage at all. Speak a sentence built by the code with a `tts_say` pre-action, then `end_conversation`. The outcome is already code-built, so nothing is lost.
- Or keep the AI there, but word the persona's tool rule as "except in the goodbye", and reword the hand-off outcome so it doesn't echo the tool description.
- Add a test that the end node can only produce speech.

---

## Medium

### R3. A change with two parts ("Dr. Kim on Friday", "Friday afternoon at Midtown") silently loses everything after the first part
**Where:** `call/tools.py:308-340` (`change_choice`), with `history: reset` in `clinic_agent.json`.

**What's wrong:** `change_choice` takes `days` and `time_of_day` whatever `what` is, then silently ignores them unless `what` is `time` (only `near` is refused). The AI can't make a second call either. `change_choice` moves the stage, the reset wipes the conversation, and the new booking stage never sees the caller's "on Friday". Proof (probe `p2_change_two_things.py`):

```
change_choice{'what': 'doctor', 'new_value': 'Dr. Kenji Kim', 'days': ['Friday']}
  -> {'ok': True}, next stage booking
  card days=[] time_of_day=''
  options now on offer: ['Thursday AM', 'Tuesday AM', 'Wednesday AM']
change_choice{'what': 'location', 'new_value': 'Midtown', 'days': ['Friday'], 'time_of_day': 'afternoon'}
  -> {'ok': True} ... card days=[] time_of_day=''   options now on offer: ['Wednesday AM']
```

**Live call:** "Could I do Friday afternoon at Midtown instead?" The caller is offered Midtown on Wednesday morning. They have to repeat themselves, and the AI has no memory that they already asked. This is the "silently dropped" problem that decision 11 exists to prevent.

**Fix:** let one `change_choice` call carry several kinds of change (doctor and/or place and/or time and/or language). The card can apply them in turn, with "latest" set to the strongest. If that's too much for now, at least **refuse** extra fields with a message ("send days only with what = time"). The AI then learns before the move instead of after it. Either way, add a test.

### R4. The card can say "visit: skin check" next to "Agreed so far: MRI - Knee"
**Where:** `call/tools.py:224-225` (`choose_visit_type` only fills `visit_description` if it's empty).

**What's wrong:** the caller's first description sticks even when stage 2 settles on a different visit. That happens when the caller changes their mind while choosing, and also when they accept the **alternative** offered after a refusal (a knee MRI refused, then a New Patient Consultation accepted). Proof (probe `p5_stale_visit_description.py`):

```
Caller: James Wilson (returning patient; referrals on file: Radiology, Orthopedics)
Caller asked for: visit: skin check
Agreed so far: MRI - Knee
```

**Live call:** in the booking stage, which has no memory of stage 2, the AI sees a card that contradicts itself. It may ask "was that the skin check?" or call `change_choice(visit_type, "skin check")` and send the caller backwards. In the alternative case it may describe the consultation as "for your knee MRI", which comes close to the referral promise the plan forbids.

**Fix:** when `choose_visit_type` is accepted, set `visit_description` to the chosen visit's name, or keep both: "asked for: skin check; chose: MRI - Knee". Add a test for the alternative path.

### R5. Going from identification to choosing a visit needs three AI passes of silence, over the plan's budget of two
**Where:** the `visit_type` stage instruction in `clinic_agent.json` ("Work out which specialty fits ... and call list_visit_types"); the same after `change_choice(visit_type)` from the booking stage.

**What's wrong:** the caller gives their date of birth, then:
1. the AI calls `start_booking` (pass 1);
2. the stage moves and resets, and the new stage starts with no caller words, only an instruction to call `list_visit_types`, so the AI does that (pass 2);
3. only then does it speak (pass 3).

That's about 3.5 s of silence by the plan's own figures (decision 9: "no reply should need more than 2"). The instruction "thank them by first name" doesn't help if the AI's first output is a tool call, which is gpt-4o's usual habit when told to call a tool.

**Fix:** when the visit description already points to a specialty, do the lookup in code and put the visit types for it into the stage's instructions (a `{visit_types}` placeholder). This is the same move the plan already makes for options. Otherwise, tell the AI to say one short sentence before calling the tool, and measure it on a real call.

### R6. Stage names are hard-coded in the tools, but the load-time checks don't know that. Renaming "identify" lets a change skip the identity check
**Where:** `call/tools.py:336` (`session.stage == IDENTIFY`), `agent_builder/builder.py:50-85` (`_validate`).

**What's wrong:** decision 49 says load-time checks turn agent-file mistakes into start-up errors, and the agent file is meant to be edited (the editor, a Copilot). But the tools compare against the fixed names `identify`, `visit_type`, `booking` and `end`. The checks only verify the names that tools can *move to*, and `identify` isn't one of them. Proof (probe `p7`, part b): rename the first node to `greeting`, and it loads without complaint. Then:

```
(b) first stage 'greeting': change_choice -> {'ok': True}, moves to: visit_type; caller identified: False
```

So "I'd like Friday" said before identification jumps straight to choosing a visit, with no caller on the card. Decision 47 says this must never happen.

**Fix:** have `_validate` require the stage names the tool code depends on (or give each tool a `needs_stages` list in the registry), and fail loudly. Or decide the move from the card itself ("no caller yet → stay") rather than from the stage name.

### R7. "Anyone but Dr. Chen", said before options are on offer, is lost
**Where:** `call/tools.py:109` (`TURN_DOWN_HINT`), `clinic_agent.json` (`turn_down_doctors` only in the booking node).

**What's wrong:** in the identify and visit-type stages, the `doctor_name` field tells the AI to use `turn_down_doctors` "once options are on offer". That tool doesn't exist in those stages, and nothing else can record the wish. The reset at the next move then wipes it.

**Live call:** "I need a skin check, but not Dr. Chen, I didn't like him." Dr. Chen is offered first in the booking stage.

**Fix:** make `turn_down_doctors` available from the start (by name only before options exist), or add a "not these doctors" field to the wish fields that travel with `start_booking` and `choose_visit_type`.

---

## Low

### R8. A time taken at the last moment silently drops "as soon as possible"
**Where:** `call/tools.py:264` (`card.change_choice("time")` on a failed confirm). Every time change sets `soonest = False` (`clinic/card.py:207`).

Proof (probe `p6_slot_taken_drops_soonest.py`): the caller asked for the soonest knee MRI. After the slot is taken, `soonest` is `False` and the new options are Dr. Nguyen at 1:30 PM, while Dr. Ramirez's 9:30 AM the same day (in the first offer) is no longer considered.

Rare with one call at a time, but it's a silent drop. **Fix:** go back to choosing without counting it as a caller's time change (clear the doctor, place and time, and keep `soonest`).

### R9. Errors other than "refused" escape `run_tool`: no call-log line, a raw error for the AI, and a booking held in memory but not saved
**Where:** `call/tools.py:473-482` (only `Refused` is caught); `:259` books the in-memory schedule before `:270` writes the file.

Probe 4 found no crash from odd values. But any unexpected error (a disk-write failure, a bug in `clinic/`) would:
- write no call-log line, which is exactly the case decision 45's log is for;
- reach the AI as Flows' `{"status": "error", "error": "<python message>"}`.

If the file write fails during `confirm_booking`, the time is held in memory but not saved. A retry is then told "That time is no longer available", because of the caller's own unsaved booking. **Fix:** catch and log every exception in `run_tool` (still re-raise or return a plain refusal). Write the file before marking the time as booked in memory, or undo the in-memory booking if the write fails.

### R10. Reply shapes and docstrings that don't match
- `call/tools.py:12` says refusals and "not found" replies have `"ok": false` and the caller never hears them. But `answer_question` replies with `"found"` and no `"ok"`, and the identity replies (`ok: false` with a `say`) are meant to be heard.
- `answer_question_tool` (`:343`) passes raw values, unlike every other tool's `_text` check. A list sent as `name` became the text `"['Dr. Chen']"` and matched 7 doctors (probe 4).
- `start_booking` returns `"say": "Thank you, James. I've found your details."` on a move (`:191`), but the reset wipes tool results before the next AI reply (`manager.py:835-845`). In the voice call it's dead output, and the builder's test (`test_knee_mri_for_james_wilson...`) checks a sentence no caller ever hears.
- `choose_option` with `"Option 1"` replies "Option Option 1 isn't on offer". It's harmless, but `card.offered` could strip a leading "option".

**Fix:** pick one reply shape (`ok` plus `say` for caller-facing text, `error` for the AI), and use `_text` for `answer_question`. Either drop `say` from moves or document it as for the typed loop only.

### R11. The load-time checks miss two things they claim to cover
- The registry says `turn_down_doctors` moves only to `booking` (`call/tools.py:432`), but `card.turn_down_doctors` returns `visit_type` when no visit is chosen. That's fine in today's file, but the check is there to catch other files.
- Placeholders are checked (and filled) only in `task_messages` (`builder.py:72`). A `{today}` in the persona or a node's `role_message` passes the check and reaches the AI as literal text.

### R12. A refused `choose_visit_type` still records the wishes sent with it
`call/tools.py:214-215` records wishes before checking whether the visit can be booked (probe 4 flags `CHANGED-ON-REFUSAL`). Keeping what the caller said is arguably right, but the task brief and the docstrings promise "a refused call changes nothing". Decide which you want, write it down, and test it.

### R13. End-stage wording
- After a hand-off, the end instruction is a description followed by "Say this in one or two short sentences". "Say this" could be read as saying "The caller asked to speak to a person" aloud.
- After a booking, the caller hears the full read-back twice (before "yes" and again in the goodbye).
- "Putting you through to a member of staff" is followed by the line going dead. For a demo, "a member of staff will call you back" is more honest.

### R14. Gaps and naming problems in this step's tests (AI-slop checklist: tests)
- `test_no_log_or_saving_when_the_clinic_has_no_paths` only checks that there's no log. It never books anything, so "no saving" is untested.
- `test_hand_off_from_any_stage_and_after_booking` only tests the booking stage. The identify and visit-type stages (decision 46) are untested.
- Untested: `change_choice` for doctor or location in the booking stage (the plan's change table), extra fields on `change_choice` (R3), the alternative path (R4), and a refused `choose_visit_type` changing the card (R12).
- Nothing tests the Pipecat side for real. The wrapper test calls handlers with a fake flow manager, so global tools in the end node, `end_conversation`, and `bot.py`'s `parallel_tool_calls` setting are never tested. Probe 3 shows the last of these can be tested without a network.
- Good points: expected answers come from the catalog and plan rather than copied output, and the bad-values test checks that nothing changed.

### R15. The README is out of date
`README.md` still describes `example_flow.json` as "the example agent ... a clinic scheduler" and lists neither `backend/call/` nor `backend/clinic/`. `bot.py` now runs `clinic_agent.json`.

---

## Checked and found fine

- **Handler return shapes (Flows 1.4.0, `manager.py:480-524`):** a `(result, node)` tuple moves the stage after the result is added (`run_llm=False`, then `_set_node`); a bare dict stays and runs the AI again. The wrappers in `builder.py:136-144` use this correctly.
- **The reset:** `ContextStrategy.RESET` sends `LLMMessagesUpdateFrame`, which replaces the whole context, tool call and result included. Apart from R3, R4 and R7, each stage's instructions carry what the next reply needs: the card, options and notes, the failed-booking note, and the outcome.
- **Global tools:** present in every node, the end node included (`manager.py:662`; probe 3).
- **`parallel_tool_calls`:** passed through `Settings(extra=...)`, and it survives Flows' per-stage persona update (extras are merged, not replaced, in `services/settings.py`). It's in every request (probe 3). It's never sent without tools, because the globals are always there and the load check covers an agent without globals.
- **Interruptions:** Flows' `cancel_on_interruption` defaults to `False`, so a caller talking over the bot can't cancel a tool halfway through a move.
- **Second call in the same process:** each connection gets its own `FlowManager`, `AgentBuilder` and `CallSession`. The registry and builder hold no per-call state. The shared schedule refuses a time booked by an earlier call (`SlotTaken`), and that is tested.
- **Bookings file:** one line per booking, reloaded at start-up, and a damaged line stops start-up with its line number (decision 48). A reloaded time is never offered again (tested).
- **Read-back matches what's saved:** both are built from the card. Any change clears the choice, so `confirm_booking` can only save the last read-back the AI was given, and the goodbye repeats what was saved.
- **Identity steps (decisions 32, 36):** `start_booking` follows the `IdentityCheck` steps. A bad wish value is refused before an identity try is counted. Same name and birthday goes to staff.
- **`turn_down_doctors` (decision 37):** names are turned into ids, and several matches give a "which one" list with no change.
- **Plain values (decisions 38 to 40):** days and times are checked before anything is recorded, and sentences in name fields are refused. No crashes in probe 4.
- **Pipecat kept out of `call/` (decision 49):** no Pipecat or loguru imports in `call/` or `clinic/`.
- **The `change_choice` moves (decisions 43, 47):** the moves match the table, with no move in identify or visit_type.
- **`hand_off` in every stage (decision 46):** it's global, and it works after a booking too.
- **The 21 specialties** are listed in the visit-type stage.
- **Clean results:** pyflakes clean, and the full test suite passes.

## Probe scripts (`review-probes/`)
| File | Shows |
| --- | --- |
| `p1_what_the_ai_sees.py` | Each stage's filled instructions and every tool reply along the knee-MRI demo path, through the real Pipecat wrappers |
| `p2_change_two_things.py` | R3: extra fields on `change_choice` silently dropped |
| `p3_request_shape.py` | The real OpenAI request: `parallel_tool_calls` kept; the end stage offers 3 tools (R2) |
| `p4_odd_values.py` | Odd values for every tool: no crashes; R10, R12 |
| `p5_stale_visit_description.py` | R4 |
| `p6_slot_taken_drops_soonest.py` | R8 |
| `p7_year_and_stage_names.py` | R1 (no year; self-contradicting refusal) and R6 (renamed stage skips identity) |
