# Independent tests: voice stages and tools (build 349b652)

Tester: a fresh agent that never saw the build conversation, the builder's tests, or the source of `backend/call/`, `backend/agent_builder/` or `backend/bot.py`. Expected answers come from `PLAN.md`, `docs/decisions.md`, `INTERFACE.md` and the raw data files (`catalog.json`, `patients.json`, `location_extras.json`). I learned the shape of results by calling the code, never by reading it.

Fixed clinic time for every test: Tuesday 6 October 2026, 9:00 AM. Bookings files and call logs go to a temporary folder per test.

## Counts

| | Tests | Pass | Fail |
| --- | --- | --- | --- |
| New tests (this step) | 296 | 272 | 24 |
| Older independent tests (rules module) | 2,848 | 2,848 | 0 |
| **All of `tests_independent/`** | **3,144** | **3,120** | **24** |

No older independent test fails.

The 24 failures come from **10 separate causes** (listed below). None of them affects the two demo paths: the Garcia skin check, the knee MRI, booking and reloading all pass.

## What I tested, by area

New files in `backend/tests_independent/`, plus one helper, `voice_reference.py`:

| File | Area | Tests | Fail |
| --- | --- | --- | --- |
| `test_voice_demo_paths.py` | 1. Demo paths end to end: "Dr. Garsha" skin check, knee MRI refused or offered, book, read-back = saved line, reload never re-offers the time | 14 | 0 |
| `test_voice_identity.py` | 2. Identity steps (decisions 32, 36), registering as new, same name and birthday → staff | 24 | 0 |
| `test_voice_stage_moves.py` | 3. Which tool moves where; change_choice table; never skipping identification | 43 | 2 |
| `test_voice_values.py` | 4. Values from the AI (decisions 37–40, 42, 47): refusals change nothing | 111 | 9 |
| `test_voice_booking_stage.py` | 5. turn_down_doctors, confirm_booking edge cases, hand_off, after the call ends | 34 | 5 |
| `test_voice_placeholders.py` | 6. What the AI is shown: {today}, {specialties}, {booking_card}, {options}, {outcome}, option numbers | 20 | 3 |
| `test_voice_agent_builder.py` | 7. clinic_agent.json, load-time checks, Pipecat handlers, history reset, one tool call at a time | 31 | 4 |
| `test_voice_files.py` | 8. Call log and bookings file, damaged files, nothing saved when paths are None | 19 | 1 |

What passed and matters most:
- **Skin check with "Dr. Garsha" (new patient):** no Garcia is offered. A true note says the Garcias don't offer Skin Cancer Screening, and the "Doctors who can" list is exactly the three new-patient dermatologists. A returning patient gets all four, Dr. Wei Sato included.
- **Knee MRI for a new patient:** refused, and the call stays in stage 2 with nothing changed. The alternative is a primary-care visit the caller can actually book, and the reply tells the AI not to promise a referral. Emily Brown (returning, no referral) is refused for the referral reason only.
- **James Wilson knee MRI near Downtown:** only the 2 valid pairs are offered (Dr. Linda Ramirez at Downtown, Dr. Hannah Nguyen at Midtown), nearest first.
- **Full demo script:** skin check, then "actually a knee MRI". The choices and options are cleared, the old doctor wish is kept with a true note (decision 26), and option numbers keep counting up.
- **Booking:** the read-back has the right visit, doctor, place, address, time and length from the raw data. The saved line matches the chosen option exactly, and {outcome} contains the read-back.
- **After a booking:** a second call on the same clinic, and a clinic reloaded from the file, never offer that time. A shorter visit that would overlap it isn't offered either.
- **Identity:** every step of decisions 32 and 36 behaves as written, including the same reply for every miss and the third try needing a spelled name. Correct details are accepted at any step; registering as new gives no referrals; a second start_booking can't swap in another patient.
- **Stage moves:**
  - change_choice records without moving in stages 1 and 2, and rebuilds the booking stage with fresh options in stage 3.
  - Changing the visit type clears the visit type, doctor, place, time and options.
  - hand_off works from every stage.
  - confirm_booking: refused when nothing is chosen, saves once if called twice, and offers fresh options when the time was taken meanwhile.
  - change_choice after the call ended is refused.
- **Builder:** every tool the AI is shown matches INTERFACE.md word for word. Handlers move with filled instructions or stay; history is reset on every move, including booking → booking; the end node ends the call. The call log's stage line holds exactly the instructions given. Broken agent files with an unknown tool, an unknown placeholder, a missing stage or a bad history setting are refused, with the problem named.

## Failing tests, one by one

### Cause 1: a language value with "not" in it, or two languages, gets through (6 tests)

- `test_values::test_start_booking_refuses_unusable_wishes_and_changes_nothing[a language sentence]`
- `test_values::test_start_booking_refuses_unusable_wishes_and_changes_nothing[two languages]`
- `test_values::test_choose_visit_type_refuses_unusable_wishes_and_changes_nothing[a language sentence]`
- `test_values::test_choose_visit_type_refuses_unusable_wishes_and_changes_nothing[two languages]`
- `test_values::test_change_choice_in_booking_refuses_and_keeps_the_options_on_offer[language sentence]`
- `test_values::test_change_choice_in_booking_refuses_and_keeps_the_options_on_offer[two languages]`

**Expected:** `language: "not Spanish"` or `"Spanish French"` is refused by the tool that receives it. The reply says how to send it, the stage stays the same and the card is untouched. That is exactly what already happens for bad days, bad times, "someone else" as a doctor and "anywhere but Downtown" as a place.
**Source:** decisions 38, 40 and 42 (two-word languages and "not" words are refused), and the rule that a refused call changes nothing.
**What happened:** the call is accepted and the card changes. start_booking and choose_visit_type move the call on. In the booking stage, the options the caller was just offered are thrown away, and the new instructions say "Fix first … I couldn't use the language" with **no options at all**.
**Verdict:** code bug (inconsistent handling). The value is caught eventually, but only after the stage has moved and the history has been wiped. In a real call, "Spanish or French, either is fine" could make every option disappear mid-booking.

### Cause 2: change_choice accepts `near: true` with no place (1 test)

- `test_values::test_change_choice_in_booking_refuses_and_keeps_the_options_on_offer[near without a place]`

**Expected:** refused, as start_booking and choose_visit_type already do ("near goes with a place").
**Source:** decision 39 ("near is a yes/no passed with a place name"); the task's "near without a place" case.
**What happened:** accepted. The place wish is wiped, `near` is silently dropped, and the options on offer are replaced.
**Verdict:** small code bug (inconsistent with the other two tools).

### Cause 3: change_choice silently drops a day sent with a doctor change (1 test)

- `test_values::test_change_choice_doctor_does_not_silently_drop_a_day_sent_with_it`

**Expected:** `{"what": "doctor", "new_value": "Dr. Kenji Kim", "days": ["Thursday"]}` is either refused (the description says "only the fields for that kind") or honours the day. Losing it without a word is the one outcome that shouldn't happen.
**Source:** the change_choice description in INTERFACE.md; decision 40 ("anything else is refused, never guessed"); decision 11 (nothing dropped silently).
**What happened:** accepted. The doctor changed and the day wish vanished.
**Verdict:** gap in the spec that lets a silent failure through. In a real call, "Dr. Kim, on Thursday" in one breath is a very natural thing to say.

### Cause 4: an unknown field is silently ignored (1 test)

- `test_values::test_unknown_field_is_not_silently_dropped`

**Expected:** start_booking with `"doctor": "Dr. Kenji Kim"` (the wrong field name; it should be `doctor_name`) is refused, or the doctor is recorded.
**Source:** my reading of decision 40 ("anything else is refused, never guessed"). No line says this about field names, so it is my judgement.
**What happened:** the call succeeds and the doctor wish is lost.
**Verdict:** gap in the spec. Language models do sometimes use a near-miss field name, and here a wish would vanish with no sign.

### Cause 5: a finished call can be reopened by stage tools (5 tests)

- `test_booking_stage::test_nothing_reopens_a_booked_call[choose_visit_type]`: after a booking, choose_visit_type moves the call back to the booking stage.
- `test_booking_stage::test_nothing_reopens_a_booked_call[choose_option]`: after a booking, choose_option changes the doctor and time on the card, so the card no longer matches what was saved.
- `test_booking_stage::test_nothing_reopens_a_booked_call[turn_down_doctors]`: after a booking, `current: true` moves the call back to booking.
- `test_booking_stage::test_nothing_reopens_a_handed_off_call[choose_visit_type]`: after a hand-off from stage 1, it **crashes** (`AttributeError: 'NoneType' object has no attribute 'is_new_patient'`).
- `test_booking_stage::test_nothing_reopens_a_handed_off_call[start_booking]`: after a hand-off, start_booking identifies the caller and moves to stage 2.

**Expected:** once the call is booked or handed off, nothing changes the card or moves the call. change_choice already refuses with "The call is finished; nothing can be changed now."
**Source:** the plan's end stage ("says goodbye … and ends the call"), and the code's own rule as applied to change_choice.
**What happened:** see each line above.
**Verdict:** code robustness bug. **Low risk for the voice agent:** in Pipecat the end node offers only the global tools (answer_question, change_choice, hand_off), and those behave correctly. It matters if the typed test loop (decision 22) ever calls run_tool without limiting tools to the current stage.

### Cause 6: stage-2 tools crash before anyone is identified (2 tests)

- `test_stage_moves::test_no_tool_skips_identification[choose_visit_type-args0]`
- `test_stage_moves::test_no_tool_skips_identification[list_visit_types-args1]`

**Expected:** called in stage 1, before start_booking has succeeded, they are refused (ok false) and don't move the call.
**Source:** the plan's stage order; decision 47 ("can't skip the identity check").
**What happened:** both crash with `AttributeError` (no caller yet). They don't move the call, but the crash is not a refusal. choose_option, confirm_booking and turn_down_doctors are refused properly in the same situation.
**Verdict:** code robustness bug. As with cause 5, Pipecat won't offer these tools in stage 1, so it is low risk for voice.

### Cause 7: {options} still shows the old options after the visit type changes (1 test)

- `test_placeholders::test_options_text_after_a_change_of_visit_type_shows_no_old_options`

**Expected:** after change_choice moves the call back to stage 2, {options} shows nothing from the old visit type (or refuses, as it does before any search).
**Source:** the plan's change_choice table and decision 11: changing the visit type clears everything that depended on it.
**What happened:** the card's options are cleared, but {options} still prints Options 1–3 for the skin check.
**Verdict:** small code bug. **Not visible with the shipped agent file**, because the visit_type stage doesn't use {options}. It would show up if someone added {options} to stage 2 in the editor, and the AI would then offer options that `choose_option` refuses.

### Cause 8: notes for the caller can carry instructions meant for the AI (2 tests)

- `test_placeholders::test_caller_notes_carry_no_tool_instructions[near Downtown]`
- `test_placeholders::test_caller_notes_carry_no_tool_instructions[Atlantis]`

**Expected:** nothing under "Tell the caller first" tells anyone how to send a value ("Pass …").
**Source:** the booking stage instructions ("First tell the caller anything under 'Tell the caller first'"). Bad values already go under a separate "Fix first (don't read this to the caller…)" heading, so the code clearly means to keep the two apart.
**What happened:** an unrecognised place appears under "Tell the caller first" as "I don't recognise the place 'near Downtown'. Pass just a place name: a neighbourhood, a street or one of our location names."
**Verdict:** gap in the spec. No line says which kind of note goes to whom, apart from bad values. **Real-call risk:** the AI's most likely mistake is `place: "near Downtown"` instead of `place: "Downtown", near: true`. The caller would then hear "I don't recognise near Downtown", and the AI isn't clearly told to fix and resend.

### Cause 9: `booked_at` in the bookings file uses the computer's clock, not clinic time (1 test)

- `test_files::test_booked_at_is_clinic_time_from_the_call_clock`

**Expected:** `booked_at` is the call's clock, which is clinic time (6 October, 9:00 in the test).
**Source:** INTERFACE.md ("NOW: a fixed datetime in clinic time"); the rules module's own rule in slots.py: "Code that needs the current time must use clinic_now(), never datetime.now(), because the computer running the agent may be anywhere (e.g. Dubai)".
**What happened:** `booked_at` was `2026-10-08T20:12:30`, the test machine's own clock. On a laptop in Dubai, one saved line would hold a Dubai time next to a San Francisco appointment time, with no label to tell them apart.
**Verdict:** likely code bug. The spec doesn't list the file's fields. (The call log's `at` field and the log file names also use the computer's clock. I didn't test those; for logs it may be intended.)

### Cause 10: load-time checks miss some typos and bad settings (4 tests)

- `test_agent_builder::test_broken_agent_file_is_refused_at_load_with_a_clear_message[parallel_tool_calls as text]`: `"parallel_tool_calls": "no"` is accepted and stored as the text "no". Text that isn't empty counts as "yes" in Python. If bot.py uses this setting as a yes/no (I can't see bot.py), "no" would turn parallel tool calls **on**, the opposite of the plan's safety setting. Expected: refused, like a bad `history`. **Code bug.**
- `test_agent_builder::test_broken_agent_file_is_refused_at_load_with_a_clear_message[placeholder in wrong case]`: `{Options}` passes the check and reaches the AI as literal text, with no options in it. **Code bug** against decision 49's purpose ("a typo in the agent file is an error at start-up, not a broken call").
- `test_agent_builder::test_broken_agent_file_is_refused_at_load_with_a_clear_message[placeholder with a space]`: `{booking card}` behaves the same way. **Code bug.**
- `test_agent_builder::test_placeholder_in_the_persona_is_filled_or_refused`: a `{today}` in the persona is neither filled nor refused; the AI sees "{today}". INTERFACE.md says placeholders are for task messages, so this is a **gap in the spec**, but an easy mistake to make in the editor.

## My own mistakes, fixed before the final run

- I expected a well-shaped but impossible birthday (`1984-02-30`) to count as "unusable". The rules module (checked earlier) treats it as an ordinary miss, which still meets decision 32. I removed that case.
- I expected "near Downtown" options in strict distance order. The rules module deliberately offers each different doctor/place pair before a second time at the same place, so I now check the order in which places first appear.
- "Turn down everyone on offer" for a new patient left nobody, because all three possible dermatologists were on offer. I switched that test to James Wilson, who has four.
- I expected `duration_min: "45"` (as text) in the bookings file to be refused. The code reads it correctly as 45 and blocks the time, which is fine, so I replaced it with `"forty-five"` (refused).

## Behaviour I found unspecified, and risks for a real call

1. **Wishes said during a failed identity try are dropped.** Example: the caller says "knee MRI" on a try that fails, and the AI later resends only name and birthday. "knee MRI" is then gone, and stage 2 has to ask again. It's minor, but it's an extra question the caller already answered.
2. **Missing settings default to the unsafe side.** An agent file without `parallel_tool_calls` gets `True` (parallel calls on), and one without `history` gets `keep`. An older-style file would silently run without the plan's safety settings.
3. **The agent file accepts some odd structures** without complaint: two stages with the same name, the same tool twice in a stage, and a tool listed both in a stage and in `global_tools`. Pipecat may then see a function twice. I didn't test what happens at run time.
4. **`global_tools` written as text** instead of a list is refused, but the message goes letter by letter ("Global tool 'h' isn't in the tool registry" eight times). It is refused, but the message isn't clear.
5. **hand_off after a booking** replies `handed_off: true` while the card stays "booked". The goodbye ({outcome}) sensibly mentions both: the saved booking, and putting the caller through to staff. The only odd part is the reply's wording, and nothing in the spec covers this case.
6. **Two identical bookings in the file** (same doctor, same time) both load without complaint. Decision 48 assumes one call at a time, so our code shouldn't produce this, but a hand-edited file could.
7. **Damaged-line messages** name the file and the line (good), but some reasons are raw Python text, such as `('start')` or `list indices must be integers or slices, not str`.
8. A saved booking's **length isn't checked against its visit type**. If a line said 20 minutes for a 45-minute MRI, part of the real appointment would be offered again. Only our own code writes the file, so the risk is low.
9. **{options} and {outcome} raise an error** if a stage uses them before a search or before the call has an outcome. With the shipped file this can't happen, but an editor change could cause a crash in the middle of a call rather than at load.
10. **`run_tool` with an unknown tool name** raises a raw `KeyError`. Pipecat never does this; a typed test loop might.
11. **I couldn't check how "one tool call at a time" reaches the AI service.** That happens in bot.py, which I was not allowed to read. I only checked the setting in the agent file.
12. **Lenient but harmless:** choose_option accepts the number `1` as well as the text `"1"`. "Morning" with a capital M is accepted.
