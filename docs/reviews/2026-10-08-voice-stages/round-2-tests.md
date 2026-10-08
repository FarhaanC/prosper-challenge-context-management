# Round-2 independent tests: voice stages (build `25c3f91`)

Tester: a fresh agent. I did not read `backend/call/`, `backend/agent_builder/` or `backend/bot.py` while doing this work. Expected answers come from `round-2-spec-changes.md`, `INTERFACE.md`, `PLAN.md`, `docs/decisions.md` (50–55), the triage, the raw data files and the rules module (`backend/clinic/`). Which appointment times exist comes from the rules module's own fake calendar (`clinic.Schedule`). Where I needed the exact layout of a text (for example one line of `{visit_types}`), I learned it by calling the code, never by reading it, and I only used it to find the line, never as the expected answer.

Clinic time for every test: Tuesday 6 October 2026, 9:00 AM, unless a test says otherwise.

## Counts

| | Tests | Pass | Fail |
| --- | --- | --- | --- |
| Round-1 voice tests (`test_voice_*.py` from round 1, after my updates) | 296 | 296 | 0 |
| New round-2 tests (`test_voice_round2_*.py`) | 336 | 336 | 0 |
| Older independent tests (rules module) | 2,848 | 2,848 | 0 |
| **All of `tests_independent/`** | **3,480** | **3,480** | **0** |

**No test fails.** Every change in the spec-change note behaves as written, and every round-1 test whose purpose still stands passes.

### Before my changes

31 of the 296 round-1 voice tests failed (the brief said about 33). The difference: two tests compare the code against `INTERFACE.md` (`test_global_functions_are_exactly_what_the_interface_shows` and `test_registry_destinations_match_the_interface[turn_down_doctors]`), and that sheet has since been regenerated for this build, so they pass without changes. The triage's count of 33 was made against the old sheet.

### Something the raw count hid

Another **25 round-1 tests were passing for the wrong reason.** They send change_choice in the old `what` / `new_value` shape and expect a refusal. The new code refuses them because `what` is now a field it doesn't have, not because of the bad value the test was about. So they passed while testing nothing. I rewrote them in the new shape, so each one checks its own value again (items 14 and 22 below). All still pass.

## What I changed in the round-1 tests, and why

Every edited test has a `# round 2: ...` comment saying what changed and which spec item it rests on. I didn't loosen any check. Where the spec now settles something the old test left open, the test is now stricter.

**`test_voice_stage_moves.py`**

1. `test_change_choice_in_identify_records_without_moving` (5 cases): old `what`/`new_value` replaced by the wish field itself (`{"visit_type": "skin check"}`, `{"doctor_name": ...}`, `{"place": "Midtown"}`, `{"days": [...]}`, `{"language": ...}`). Spec: "change_choice has a new shape".
2. `test_wish_recorded_in_identify_is_used_later`: same change of shape.
3. `test_change_choice_in_visit_type_records_without_moving` (5 cases): same change of shape.
4. `test_change_visit_type_in_booking_goes_to_stage_2_and_clears_what_depended_on_it`: `{"visit_type": "knee MRI"}`.
5. `test_change_in_booking_rebuilds_booking_with_fresh_options` (5 cases): one wish field per case.
6. `test_change_time_keeps_the_doctor_and_place_as_wishes`: `{"days": [...]}`.

**`test_voice_agent_builder.py`**

7. `test_clinic_agent_loads_with_safe_settings`: the always-available tools now include turn_down_doctors. Spec: "turn_down_doctors is available in every stage"; decision 53.
8. `test_every_stage_function_is_what_the_interface_shows`: turn_down_doctors is no longer one of the booking stage's own tools. Spec: "The booking stage's own tools are choose_option and confirm_booking".
9. `test_change_choice_handler_in_identify_stays`: new shape.
10. `test_change_in_booking_rebuilds_booking_with_fresh_options_and_reset`: new shape.

**`test_voice_booking_stage.py`**

11. `test_turned_down_doctor_stays_out_after_later_changes`: new shape. It now also checks that each change is accepted. Before, both changes were refused and the test still passed.
12. `test_change_of_visit_type_starts_the_turned_down_list_again`: new shape, and checks the change is accepted.
13. `test_confirm_after_a_change_is_refused`: new shape, and checks the change is accepted.
14. `test_change_choice_after_the_call_ended_is_refused` (6 cases): new shape. Before, these were refused only because of the unknown `what` field. Now the refusal has to come from the call being over (decision 55).

**`test_voice_demo_paths.py`**

15. `test_demo_script_skin_check_then_knee_mri_for_returning_patient`: `{"visit_type": "knee MRI"}`.

**`test_voice_identity.py`**

16. `test_found_returning_patient_moves_on_with_their_record`: the success reply is now exactly `{"ok": true}`, with no "Thank you, James". The thank-you moved into stage 2's instructions. The test now checks the reply is `{"ok": true}`, that stage 2's instructions tell the AI to thank the caller by first name, and that "James Wilson" is in what the AI is shown there. Spec: "start_booking: The success reply is {"ok": true}… Stage 2's instructions tell the AI to thank the caller by first name".

**`test_voice_placeholders.py`**

17. `test_booking_card_shows_caller_wishes_and_agreed_choices`: once the knee MRI is accepted, the card's visit description is "MRI - Knee", not the caller's words "knee MRI". The test now checks that, and that "knee MRI" is gone from the card. Spec: "The card's visit description becomes the accepted visit type's name"; decision 53.
18. `test_options_text_is_refreshed_after_every_rebuild`: new shape, and checks the change is accepted.
19. `test_unusable_values_are_for_the_ai_not_the_caller`: new shape.
20. `test_options_text_after_a_change_of_visit_type_shows_no_old_options`: new shape. The old test allowed "raises an error" or "shows no old options". The spec now says it raises an error, so the test requires a `ValueError`. Spec: "After a visit-type change, {options} has no search to show (it raises an error, as before any search)".
21. `test_option_numbers_are_never_reused_through_a_long_call`: new shape. The last step used empty values to clear the time wish. Empty now counts as "not sent", so it sends `"any"` instead (`days: ["any"], time_of_day: "any"`). Spec: "'any' drops a wish… An empty string or empty list counts as not sent".

**`test_voice_values.py`**

22. `BAD_CHANGES` (17 cases of `test_change_choice_in_booking_refuses_and_keeps_the_options_on_offer`): every case rewritten in the new shape, so it tests its own bad value again. Four needed more than a rename:
    - "time as new_value phrase" → the phrase in `time_of_day` (the old `new_value` for a time no longer exists);
    - "time with nothing" → `{}` (nothing sent);
    - "near without a place" → `place: ""` with `near: true` (empty counts as not sent);
    - "unknown kind" → an unknown field `mood`.
    "no kind" (`new_value` alone) is unchanged: it is still a field the tool doesn't have.
23. `test_change_choice_doctor_does_not_silently_drop_a_day_sent_with_it`: new shape. Decision 51 settles what the old test left open ("refused or honoured"): both must be applied. The test now requires ok, the day and the doctor.
24. `test_choose_option_refuses_a_stale_number_after_fresh_options`: new shape, and checks the change is accepted.

**Left as they were.** Some old tests are still right under the new spec but looser than it: `test_unknown_field_is_not_silently_dropped`, `test_placeholder_in_the_persona_is_filled_or_refused`, `test_no_tool_skips_identification` and `test_today_is_the_clinic_date_and_time_from_the_call_clock`. I left them alone and added strict versions in the new files.

## What I added

Six new files in `backend/tests_independent/`, and one small helper, `voice_round2_reference.py`. The helper parses `{visit_types}` lines, lists open times from a fresh fake calendar, and checks "refused and nothing changed".

| File | What it covers | Tests |
| --- | --- | --- |
| `test_voice_round2_change_choice.py` | change_choice's new shape | 121 |
| `test_voice_round2_identify.py` | start_booking's specialty, `{visit_types}`, wishes on failed identity tries, the card's visit description | 48 |
| `test_voice_round2_turn_down.py` | turn_down_doctors before options, in stages 1 and 2 | 26 |
| `test_voice_round2_call_order.py` | the order of a call, unknown fields, answer_question / choose_option / hand_off changes, triage R8 and R9 | 80 |
| `test_voice_round2_shown.py` | what the AI is shown: `{today}`, the window message, "Fix first", `{outcome}`, the end stage, the persona | 27 |
| `test_voice_round2_files_and_load.py` | booked_at, damaged-line messages, load-time checks, a renamed first stage | 34 |

What the new tests check, by spec item:

- **Several changes in one call.**
  - "Wednesday afternoon at Midtown" in the booking stage gives exactly the first three open Wednesday-afternoon skin-check times at Midtown. I worked those out from the catalog and the fake calendar: Dr. Kenji Kim is the only doctor who can see a new patient there.
  - The same answer comes back whichever order the fields are sent in.
  - The same three wishes sent in stage 2 are used for the first options.
  - Eight wishes sent before identification are all recorded, and the call stays.
  - A doctor and a place changed together after choosing: neither old choice is carried over.
- **Order, and "latest".**
  - The strongest kind sent becomes the latest change (8 combinations, including the same fields in reverse order).
  - It decides the outcome when wishes clash. Midtown + Friday: Dr. Kim is never at Midtown on a Friday, so the place wins and the Friday wish gets a note. Dr. Daniel Smith + Arabic: the doctor wins and Arabic gets a note.
  - A visit type sent with a doctor and a day is applied first. So the turned-down list is cleared, but the doctor and day survive, the latest change is "doctor", and the knee MRI options that follow are Dr. Ramirez on a Friday.
- **Soonest.**
  - A time change resets it (three variants).
  - It is kept when sent in the same call (two variants).
  - Place, language and doctor changes keep it.
  - "Soonest" on its own gives the earliest time any valid doctor has, ranked by time and not distance.
  - A time change alone keeps the time of day, and the time of day alone keeps the days.
- **"any" drops each kind of wish** (doctor, place, days, time of day, language), in the booking stage and before identification. Only that wish is dropped. After choosing, doctor "any" keeps the place as a wish and place "any" keeps the doctor (the plan's table).
- **An empty value counts as not sent.**
  - Only-empty calls are refused (8 shapes × 3 stages), and the options on offer still stand.
  - `days: []` sent with a time of day keeps the days. An empty doctor sent with a language keeps the doctor. An empty place sent with days keeps the place.
- **Refusals change nothing** (16 cases × 3 stages):
  - specialty without visit_type;
  - near with no place, an empty place, place "any", or only a time change;
  - the old `what` shape, `new_value`, or a misspelt field;
  - **one good field plus one bad one** (nothing at all is applied);
  - an unknown specialty.
  - The unknown-field message names every field change_choice has.
- **Near with place "any"** is refused, in every stage.
- **turn_down_doctors before options.**
  - By name and by id, in stages 1 and 2: recorded, and the call stays.
  - Honoured by the first options; the card shows who was turned down.
  - Two doctors turned down before identification leave only the third.
  - "Dr. Chen" asks which one and changes nothing.
  - on_offer or current with nothing on offer, an unknown name, a sentence, an unknown id, nothing, or an unknown field: all refused, changing nothing.
- **`{visit_types}` after start_booking with a specialty.**
  - 5 specialties × a new patient, James Wilson and Emily Brown. The ids are exactly that specialty's visit types in `catalog.json`, with names and lengths as there.
  - "Can book" exactly matches my own rules from the raw data. Every "can't book" gives a reason that mentions the referral or existing-patients rule where that applies.
  - The specialty is matched as list_visit_types matches it: 11 spellings tried through both tools, with the same answer each time.
  - Unknown specialties are refused and record nothing.
  - No specialty gives "Not looked up yet". Stage 1 shows all 21 specialty names.
  - A visit-type change with a specialty, made from booking, lists that specialty in stage 2.
- **Wishes on a failed identity try.**
  - Kept on a wrong birthday, a missing birthday and a wrong name.
  - Wishes from two failed tries are used once the caller is found.
  - A refused value on a try records nothing and doesn't count as a try (6 kinds of bad value).
- **The card's visit description** becomes the visit's name when accepted, and stays as said when refused. A visit the caller can't book still records the wishes sent with it (decision 54); a bad value sent with it records nothing.
- **A finished call** (booked, handed off, or handed to staff because two patients share a name and birthday) refuses 12 different tool calls, changing nothing. answer_question still works. hand_off says `handed_off: true` only when it changes the status (first hand-off yes; after a booking or a second hand-off, no).
- **Before identification**, list_visit_types, choose_visit_type, choose_option and confirm_booking are refused with "Identify the caller first", also after a failed try. answer_question, change_choice and turn_down_doctors work.
- **Unknown fields:** every one of the 9 tools refuses an extra field and names all its own fields. run_tool with an unknown tool name raises a `ValueError` naming all 9 tools.
- **answer_question:** ok true when found, false when not. Values that aren't text, an unknown `about`, or a missing field are refused.
- **choose_option:** "2" and 2 work. "Option 2", "option 2", "#2", "2.", 2.0, `true` and a list are refused.
- **The year:**
  - `{today}` is exactly "Tuesday 6 October 2026 at 9 AM (clinic time, San Francisco)", and the same for two other dates, one in 2027.
  - The window message is exactly "… is outside the booking window (6 October to 20 October 2026)." for dates in 2024, 2025, just after and just before the window, through start_booking, choose_visit_type and change_choice.
- **"Fix first":** an unknown place's note is under "Fix first (don't read this to the caller…)" and not under "Tell the caller first".
- **The goodbye:**
  - Booked: the read-back, then "Confirm the day, time and doctor in one short sentence (not the whole read-back again)".
  - Every hand-off says "A member of staff will call the caller back about this", and nothing says "put/putting … through".
  - A hand-off after a booking keeps the read-back in the goodbye (triage K5).
  - The built end node holds the outcome, then "speak only. Don't call any tool".
  - The persona's "use a tool" rule mentions the goodbye.
- **booked_at in clinic time:** to the minute, from the call's clock, including a clock with seconds. It stays the same when the computer's time zone is set to Dubai.
- **Damaged-line messages:** "missing start", "unknown doctor id prov_999", "isn't a date and time", "isn't a number of minutes", "not a JSON record" (a list, a number), and "missing … provider_id". None shows Python error names.
- **Load-time checks:**
  - 20 broken agent files, each refused naming the problem:
    - parallel_tool_calls as 1, null or "false";
    - global_tools as text, or holding a number;
    - a global tool twice; stage tools as text; a stage tool twice;
    - a tool both in a stage and global; two stages with the same name;
    - `{Options}`, `{ options }`, `{visit-types}`, `{options!r}`, `{1}`, `{ok: false}`, and `{today}{weather}`;
    - a placeholder or unknown braces in the persona; a placeholder in a stage's role message.
  - The starter `example_flow.json` still loads.
  - The always-available tools are exactly answer_question, change_choice, turn_down_doctors and hand_off.
- **Renamed first stage (triage R6):** with the first stage renamed "greeting", change_choice and turn_down_doctors before identification still record without moving.
- **Triage R8:** after a failed confirm, "soonest" and the latest change are kept.
- **Triage R9:** if the bookings file can't be written, the error surfaces and the time is not held.

## Failing tests

**None.**

## Things I noticed that no spec line covers (for the reviewer, not failures)

- **answer_question uses a different reply key.** Its refusals put the reason under `message`. Every other tool puts it under `error`. The spec doesn't name the key, so my helper accepts either.
- **Per-stage `role_messages` (plural) is silently ignored.** The agent format's per-stage role message is `role_message` (singular). A placeholder there is refused at load, as the spec says. But a stage with `role_messages` (Pipecat's own plural name) loads without complaint and is simply dropped, so a typo in the agent file is lost silently.
- **A visit change made in stage 2 isn't shown to the AI right away.** change_choice with `visit_type` + `specialty` in stage 2 records the change and stays. The stage isn't rebuilt, so the AI doesn't see the new `{visit_types}` list until it calls list_visit_types. That matches the spec ("in the visit_type stage: recorded, and the call stays"), but the specialty sent there may do nothing visible.
