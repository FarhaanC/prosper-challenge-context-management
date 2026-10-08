# Round-2 independent review: voice stages, fixes (build `25c3f91`)

Reviewer: the same fresh agent that wrote `round-2-tests.md`. I did this review **after** that report was written, and I didn't change any tests to fit what I then read in the code. I never saw the build conversation or a build log.

**Scope:** the fixes listed in `triage.md`. I read the current `backend/call/` (`tools.py`, `session.py`), `backend/agent_builder/` (`builder.py`, `schema.py`), `backend/clinic_agent.json`, how `bot.py` wires them, and the builder's `backend/tests/test_builder_call_tools.py`. There is no git in this folder, so I compared against the round-1 code as `code-review.md` describes it.

**Probes:** in `round-2-probes/`. Run each one from `backend/` with `python3 ../docs/reviews/2026-10-08-voice-stages/round-2-probes/<file>.py`. No code, test or agent file under `backend/` was changed.

**Results of running things:**
- Builder tests (`backend/tests/`): **353 passed**.
- Independent tests (`backend/tests_independent/`, including my 336 new ones): **3,480 passed**.
- pyflakes on `call/`, `agent_builder/`, `bot.py` and `tests/test_builder_call_tools.py`: **clean**.

**Severity:**
- **high:** a wrong booking, a crash, or a broken live call with the shipped agent file;
- **medium:** something the caller said is silently lost or overturned, a wrong booking that is only reachable outside the shipped file, or a real gap in a stated guarantee;
- **low:** tidiness, or a small gap.

**Summary:** no high findings. The triage's fixes do what they say: every round-1 finding marked "Fix" is fixed, and the "Won't fix" reasons hold up. But the two new features each brought a way for the caller's words to be lost: one change_choice call carrying several changes, and turn_down_doctors in every stage. Those are S1 to S3. S4 is an older hole that decision 55 now promises is closed and isn't.

---

## Findings

### S1. Turning one doctor down before options exist wipes the doctor the caller asked for (medium)

**Where:**
- `call/tools.py:351` calls `card.turn_down_doctors`;
- `clinic/card.py`, `turn_down_doctors`: `prefs.doctor_name_heard, prefs.preferred_provider_id = "", ""` and `latest = DOCTOR` (through `_finish_change`).

**What happens:** decision 53 made turn_down_doctors work before options exist, so it "records without moving". But it still runs the booking stage's full "doctor change". That throws away any doctor wish already on the card, and makes "doctor" the latest change. Proof (`q2_turn_down_wipes_doctor_wish.py`):

```
after start_booking: doctor wish = 'Dr. Daniel Smith' | latest = ''
turn_down_doctors 'not Dr. Kim' in stage 2 -> {'ok': True, 'noted': 'Recorded. Carry on with this stage.'}
now: doctor wish = '' | not = ['prov_027'] | latest = 'doctor'
first options (caller asked for Dr. Daniel Smith): Dr. Wei Sato @ Midtown ... (x3)
```

**Scenario:** "A skin check with Dr. Smith, please, but not Dr. Kim." Both are said before the visit is chosen. The caller is then offered Dr. Wei Sato three times. Nothing tells them that their Dr. Smith wish was dropped. This is the kind of silent loss decision 53 was meant to close (R7).

**Fix:** before options are on offer, add the ids to `not_provider_ids` only. Clear the doctor wish only if it names one of the turned-down doctors, and leave `latest` alone. One way to do that is a small `card.add_turned_down(ids)` used when nothing is on offer. Add a test for "doctor wish + turn down another doctor" in stages 1 and 2. In the booking stage, consider the same rule for a doctor who isn't on offer and isn't the one wished for.

### S2. A visit-type change in stages 1–2 wipes a turn-down said before any visit was chosen (medium)

**Where:**
- `call/tools.py:378` calls `card.change_choice("visit_type", ...)`;
- `clinic/card.py`, `change_choice`'s visit branch: `prefs.latest, prefs.not_provider_ids = "", []`.

**What happens:** "A change of visit type starts the list again" made sense when a doctor could only be turned down from the options for an accepted visit. Since decision 53, "not Dr. Kim" can be recorded before any visit exists. The caller then refines what they want, the AI sends change_choice with `visit_type`, and the turn-down is silently cleared. Proof (`q3_visit_change_wipes_early_turn_downs.py`), the same in both stages:

```
[identify] after 'not Dr. Kim': not = ['prov_027']
[identify] change_choice visit_type -> {'ok': True, 'noted': 'Recorded. ...'} | not = []
[identify] options: ['#1 Dr. Kenji Kim @ Downtown Health Center Tue 06 Oct 11:00', ...]
```

**Scenario:** "I don't want Dr. Kim… actually, I'd like a skin cancer check rather than a general check-up." Dr. Kim is the first option offered.

**Fix:** reset the turned-down list only when an accepted visit (`choices.visit_type_id`) is being replaced. Doing it from the tool layer keeps `clinic/` unchanged. Add a test for each stage.

### S3. "As soon as possible", sent on its own, overturns the caller's newer place (or doctor) choice (medium)

**Where:** `call/tools.py:370` (`time_sent` counts `soonest`) and `:383-387` (it runs `card.change_choice("time")`, which sets `latest = "time"`).

**What happens:** soonest is grouped with the time wishes. So "soonest" on its own makes "time" the latest change, even though no day or time of day changed. Any older day wish then outranks the caller's newer place choice. Proof (`q1_soonest_flips_latest.py`):

```
1) wishes: Friday.                         options on Friday at three places
2) caller: 'Midtown, please'. latest = location
   options: Dr. Kenji Kim @ Midtown Wed 07 Oct (x3); note "There's nothing on Friday at Midtown Medical Group."
3) caller: 'whatever's soonest'. latest = time
   options: back to Friday at North Beach / Mission District / Richmond
   note: "Midtown Medical Group isn't available on Friday."
```

**Scenario:** the caller picked Midtown, then said "whatever's soonest". They're moved away from Midtown, and told about a Friday they no longer care about. This follows the spec note's wording ("the strongest kind sent becomes the latest"), but the spec didn't consider soonest on its own.

**Fix:** when only `soonest` is sent, set it, clear the chosen option and refresh, but keep `latest` as it was. Equivalently: count it as a time change only when `days` or `time_of_day` is sent. Add a test with a place, then soonest.

### S4. choose_visit_type after an option is chosen keeps the old doctor, place and time, and confirm_booking then saves a visit the caller never heard read back (medium)

**Where:** `call/tools.py:260-278`. An accepted choose_visit_type sets the specialty and visit type and refreshes the options. It never clears `provider_id`, `location_id` or `slot`, and it doesn't check that no visit was accepted yet.

**What happens:** in the shipped agent file, choose_visit_type is only offered in stage 2, so a live voice call can't reach this. But decision 55 says the order of a call is enforced by the code so that "the typed test loop (decision 22) and edited agent files shouldn't depend on" which tools a stage offers. Here the code doesn't enforce it. Proof (`q4_choose_visit_type_keeps_old_slot.py`):

```
read back to the caller: Skin Cancer Screening with Dr. Kenji Kim at Downtown Health Center, ... 11 AM.
choose_visit_type appt_028 (Full Body Skin Exam) in the booking stage -> {'ok': True} | still chosen: prov_027 loc_004 2026-10-06 11:00:00
confirm_booking -> {'ok': True, 'booked': 'Full Body Skin Exam with Dr. Kenji Kim at Downtown Health Center, ... 11 AM. ...'}
```

The saved booking is a visit the caller never agreed to. That breaks the plan's guarantee 2 ("what's saved always matches what was said"). It is reachable if an edited file makes choose_visit_type a global tool (the load checks allow that), or in a typed loop that doesn't limit tools per stage.

**Fix:** have choose_visit_type refuse once a visit type is accepted ("To change the visit, use change_choice with visit_type"). Or have it go through the same clearing as a visit-type change. Add a test that runs it from the booking stage after choose_option.

### S5. The end stage's wording after a hand-off still points the AI at hand_off (medium; I can't prove it without a live model)

**Where:**
- `call/tools.py:402-406` (`HAND_OFF_REASONS`) and `:422-426` (the outcome);
- the hand_off description at `:515-517`;
- Flows adds every global tool to every node (`pipecat_flows/manager.py:662`). There is no way to turn this off for one node.

**What happens:** decision 50 accepts a residual risk, and the reword removed "putting through". But after the stage reset, the only thing in the end stage that sounds like the caller's request is the reason sentence. That sentence is worded as a live request, and it matches the hand_off tool's own trigger. Proof (`q7_end_stage_after_hand_off.py`), what the AI gets:

```
developer: "The caller wants to reschedule an appointment. A member of staff will call the caller back about this.
            Tell the caller that ..., thank them and say goodbye. ... speak only. Don't call any tool ..."
tools offered: ['answer_question', 'change_choice', 'turn_down_doctors', 'hand_off']
hand_off: "For things a member of staff handles: rescheduling or cancelling an appointment, or when the caller asks
           for a person. Staff will call them back; this ends the call with a goodbye."
```

Two pulls towards the tool:
- "The caller wants to reschedule" / "The caller asked to speak to a person" are exactly hand_off's trigger conditions.
- hand_off's description says it "ends the call with a goodbye", while the instruction asks the AI to "say goodbye".

The end stage also now offers one more tool than in round 1 (turn_down_doctors). If gpt-4o calls any tool there, the call hangs up in silence (round-1 R2).

**Fix:**
- Word the reason as something already done: "This call has been passed to staff (the caller wanted to reschedule)."
- Drop "this ends the call with a goodbye" from hand_off's description (say instead "after this, you only say goodbye").
- Optional, if it's worth the time: a pre-action on the end node that sets `tool_choice: "none"` for that one AI turn. Pipecat's settings-update frame may allow this. I haven't checked that it works.

### S6. A specialty sent before identification is dropped; one sent with change_choice in stage 2 does nothing visible (low)

**Where:** `call/tools.py:247` (`session.listed_specialty = specialty`, even when it's None); `:237` (a failed try records wishes but not the specialty); `:379`.

**What happens** (`q5_specialty_and_any.py`):
- change_choice with `visit_type` + `specialty` before identification sets the specialty. A later start_booking without a specialty resets it to None, and stage 2 opens with "Not looked up yet".
- The same happens when the specialty was sent with a failed identity try. Then the right birthday is sent without repeating the specialty.
- In stage 2, change_choice with a specialty records it and stays. The stage isn't rebuilt, so the AI never sees the new list and has to call list_visit_types anyway.

Each case costs the extra AI pass that decision 52 was meant to save.

**Fix:**
- In start_booking, `if specialty: session.listed_specialty = specialty`.
- Keep the specialty from a failed try, like the other wishes.
- In stage 2, return `visit_types` in the change_choice reply when a specialty is sent.

### S7. The load-time checks still let a misspelt key through, and some wrong types crash with raw Python errors (medium)

**Where:** `agent_builder/schema.py:62-72` and `:89-101` (unknown keys are ignored); `agent_builder/builder.py:61, 66, 76, 79`.

**What happens** (`q6_load_check_gaps.py`):

```
LOADED   booking stage 'tools' misspelt 'tool'  (booking stage tools now: [])
LOADED   stage 'role_messages' (Pipecat's plural) with {today}
LOADED   top-level 'global_tool' misspelt, ...
CRASH    history as a list: TypeError: unhashable type: 'list'
CRASH    persona as a number: TypeError: expected string or bytes-like object, got 'int'
CRASH    role_message as a list: TypeError: ...
CRASH    a task message that's plain text: AttributeError: 'str' object has no attribute 'get'
```

Decision 49 promises that "a typo in the agent file is an error at start-up, not a broken call". A booking stage whose `tools` key is misspelt loads, and then can never book. The editor and Copilot will be writing these files.

**Fix:**
- Refuse keys the schema doesn't know (per node, per edge, at the top level), naming the key. The starter file's keys are all known (`name`, `task_messages`, `edges`, `end`).
- Type-check `persona`, `role_message`, `history` and each task message (a dict with text `content`) before using them, so every problem comes back in the one ValueError list.

### S8. `visit_type: "any"` is stored as the visit description (low)

**Where:** `call/tools.py:366, 378`.

**What happens:** `change_choice {"visit_type": "any"}` is accepted. It sends the call back to stage 2 with "visit: any" on the card (`q5`). The description lists "any" only for doctor, days and time.

**Fix:** treat a no-preference word in `visit_type` as not sent, or refuse it.

### S9. Doubled braces load and reach the AI half-filled (low)

**Where:** `call/session.py:46` (`PLACEHOLDER = r"\{([^{}]*)\}"`).

**What happens:** `{{today}}` passes the load check. It is filled as `{Tuesday 6 October 2026 at 9 AM (...)}`, braces and all. Since "anything in braces" is now a placeholder, there's also no way to write a literal brace in an instruction.

**Fix:** refuse `{{` and `}}` at load, or treat them as escapes and say so in INTERFACE.md.

### S10. answer_question still has its own reply shape, and the tool docstring's rule about `ok: false` doesn't hold (low; AI-slop: inconsistent shapes and a docstring that doesn't match)

**Where:** `call/tools.py:397-399` and `:14-16`; `clinic/facts.py`.

**What happens:**
- answer_question's refusals and "not found" replies give `{"ok": false, "found": false, "message": ...}`. Every other tool uses `error` (probe in `round-2-tests.md`). R10 asked for one shape, and this is half done.
- The module docstring says an `ok: false` reply "is for the AI to act on and the caller never hears it, except the identity steps' say". But choose_visit_type's refusal reasons are meant to be explained to the caller (its own description says so), and turn_down_doctors' `which_one` is a question for the caller. The persona repeats the same rule.

**Fix:** map answer_question's non-found replies to `error`. Reword the docstring (and the persona line): "ok false means the tool didn't do it; act on the reply".

### S11. Card kinds written as plain strings in tools.py, a stale comment in card.py, a duplicated message (low; AI-slop: the same rule in two places)

**Where:**
- `call/tools.py:360-393`: `"language"`, `"time"`, `"location"`, `"doctor"` written out as strings. `clinic/card.py:27-34` exports `DOCTOR`, `LOCATION`, `TIME`, `LANGUAGE` precisely because "Round 2 found a bug where one file said 'location' and the other 'place'".
- `clinic/card.py:37`: "by the exact names the tools use" is no longer true; the tools now use `doctor_name`, `place`, `days`…
- `call/tools.py:111` and `:255`: the same "isn't one of our specialties" refusal is built twice. list_visit_types could call `_specialty`.

**Fix:** import the constants, reuse `_specialty`, and update the comment.

### S12. Gaps in the builder's new tests (low; AI-slop: a test that checks the code against itself)

**Where:** `tests/test_builder_call_tools.py`.

- **Tools present in every stage.** `test_the_real_openai_request_sends_one_tool_at_a_time_in_every_stage` (`:599`) builds the tool list itself (`b.global_functions() + node["functions"]`). So "tools present in every stage" is true by construction, not checked through FlowManager. It does prove `parallel_tool_calls` reaches the request, which is the important half. The line `s.offer = None` (`:610`) does nothing.
- **An unclear parametrization.** `test_option_number_is_a_number_only` uses `None` to mean "send the number as an int".
- **Not covered:**
  - one good field plus one bad field in change_choice (nothing applied);
  - soonest kept when sent with a time change (and S3);
  - empty values counting as not sent (only `{}` is tested);
  - turn_down_doctors in stage 2 not moving;
  - a doctor wish surviving a turn-down (S1);
  - turn-downs surviving a visit change in stages 1–2 (S2);
  - choose_visit_type after choose_option (S4).
  My independent tests now cover the first four.

### S13. Stage 2's instructions can't tell a fresh entry from a return (low; live-call risk, unproven)

**Where:** `clinic_agent.json`, the `visit_type` node.

- **The thank-you can come at the wrong time.** "If the caller has only just been identified, thank them by first name." After a visit change from the booking stage, stage 2 is entered again with the same instructions and a card naming the caller. The reset leaves the AI no way to tell the two apart, so it may say "Thank you, James" in the middle of the call.
- **It may still be three silent passes.** With `{visit_types}` listed and a clear visit description ("skin check"), gpt-4o may call choose_visit_type straight away without speaking. That makes three silent passes after the date of birth (start_booking, choose_visit_type, then the booking stage speaks). That is the count R5 set out to reduce, although the visit question is saved.

**Fix:**
- Have the code fill in one line saying why stage 2 started ("just identified" / "the caller changed the visit"). For example, add it to the card or use a small placeholder.
- Tell the AI to say one short sentence before calling choose_visit_type.
- Measure both on a real call.

---

## Checking the triage claims

| # | Claim | Verdict |
| --- | --- | --- |
| R1 | Year in `{today}` and in the window message | **Fixed.** `session.py:182`; the window message is from `clinic/options.py`. Tested for 2024, 2025 and the edges of the window, through three tools. |
| R2 | Reword (decision 50) | **Reworded as decided; risk remains.** Persona "Until the goodbye…", end stage "speak only…", no "putting through". The reason sentence and hand_off's description still invite the tool (S5). |
| R3 | One change_choice carries several changes | **Fixed.** Every value is checked before anything changes (`_read_wishes`); the order is visit, language, time, place, doctor; "latest" is the strongest kind; empty means not sent; "any" drops a wish. 121 independent tests pass. New problem: S3. |
| R4 | Card's visit description becomes the accepted visit's name | **Fixed** (`tools.py:276`). |
| R5 | Pre-listed visit types | **Fixed for the common path** (`start_booking` specialty, `{visit_types}`). Content matches my rules for 15 specialty/caller combinations. Gaps: S6, S13. |
| R6 | Moves decided by the card, not a stage name | **Fixed.** `_after_change` stays when there's no caller. The one remaining name check (`session.stage == VISIT_TYPE`) is safe, because the load check requires a `visit_type` node whenever a tool can move there. Tested with a renamed first stage, through run_tool and through the Pipecat handlers. |
| R7 | turn_down_doctors in every stage | **Fixed as designed,** but it brought S1 and S2. |
| R8 | A failed confirm keeps soonest and the latest change | **Fixed** (`tools.py:308-311`). Tested. |
| R9 | Unexpected errors logged; file written before the time is held | **Fixed** (`tools.py:552-554`, `:318-326`). Tested with a bookings path that is a folder. `schedule.book` can't fail after `check_booking` has just passed, so the write-first order leaves nothing half done. |
| R10 | Reply shapes | **Mostly fixed:** `ok` everywhere, answer_question values checked, dead "say" gone, digits-only option numbers (`True` is refused too). Remaining: S10. |
| R11 | Load checks: turn_down → visit_type; persona placeholders | **Fixed.** Remaining load-check gaps: S7, S9. |
| R12 | Won't fix (decision 54) | **Sound.** The wishes are the caller's own words, and the module docstring now limits "a refused call changes nothing" to refused values. Tested both ways. |
| R13 | End-stage wording | **Fixed** (short confirmation; "will call you back"). See S5 for the reason sentence. |
| R14 | Test gaps | **Mostly fixed.** Remaining: S12. |
| R15 | README | **Fixed.** It describes `clinic_agent.json`, `call/`, `clinic/`, the bookings file and the call logs. |
| T1–T10 | | **All fixed.** Each is covered by a passing independent test (see `round-2-tests.md`). |
| K2 | Won't fix (defaults kept for the starter agent) | **Sound.** The starter still loads; our file sets both settings, and a test checks it. |
| K6, K8 | Won't fix (only our code writes the file) | **Sound** for a one-call-at-a-time demo (decision 48). |
| K9 | Won't fix now (`{options}`/`{outcome}` in the wrong stage) | **Acceptable for the demo,** but the editor that is meant to catch it doesn't exist yet. Worth a line in the defence notes. |

## Checked and found fine

- **change_choice:**
  - every value is checked before any change, so one bad field means nothing is applied (16 refusal cases × 3 stages);
  - the visit type is applied first, then weakest to strongest, so the strongest kind becomes "latest";
  - a time change resets soonest unless it is sent with it;
  - `near` with no place, or with place "any", is refused;
  - an unknown field is refused, naming every field;
  - a visit change from the booking stage clears `session.offer`, so `{options}` raises until a new visit is accepted.
- **`_after_change`:** the card decides (no caller → stay; stage 2 → stay; booking → refresh; a visit change from booking → visit_type). The stays return `noted: "Recorded…"`.
- **run_tool's checks:** they run in a sensible order (unknown field, then finished call, then needs a caller). An unknown tool name raises a ValueError naming the tools. Unexpected errors are logged with the tool and args, then raised.
- **`{visit_types}`:** built from `can_book_visit_type`, the same rule list_visit_types uses. The specialty is matched by the same `match_specialty` (11 spellings agree between the two tools).
- **The placeholder regex:** the load check and the filling use the same pattern. Filled-in text isn't scanned again (`re.sub`), so braces inside the card or a note can't break a stage.
- **The new load-time checks:** each of parallel_tool_calls type, list types, repeats, a tool in a stage and global, duplicate stages, unknown braces, and placeholders in the persona or a stage's `role_message` gives a clear message (20 cases).
- **booked_at:** `now.isoformat(timespec="minutes")` from the call's clock. It is unchanged with the computer's time zone set to Dubai.
- **Damaged bookings-file lines:** each problem is named, and no Python error names appear.
- **hand_off:** `handed_off` is true only when the status changes. A hand-off after a booking keeps the read-back in the goodbye.
- **Flows:** global tools reach every node, the end node included (`manager.py:662`), with no way to opt out per node. That is why S5's wording matters.
- **bot.py:** passes `parallel_tool_calls: False` through `Settings(extra=...)` and gives each call its own session (unchanged since round 1).
- **pyflakes:** clean. No unused imports or dead code in the changed files, apart from the test line noted in S12.

## Probe scripts (`round-2-probes/`)

| File | Shows |
| --- | --- |
| `_setup.py` | Shared setup (fixed clock, catalog, helpers) |
| `q1_soonest_flips_latest.py` | S3 |
| `q2_turn_down_wipes_doctor_wish.py` | S1 |
| `q3_visit_change_wipes_early_turn_downs.py` | S2 |
| `q4_choose_visit_type_keeps_old_slot.py` | S4 |
| `q5_specialty_and_any.py` | S6, S8 |
| `q6_load_check_gaps.py` | S7, S9 |
| `q7_end_stage_after_hand_off.py` | S5: the end stage's text and tools after a hand-off |
