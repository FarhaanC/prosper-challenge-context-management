# Triage: independent check of the voice stages (build `349b652`)

Every finding from the reviewer (`code-review.md`, R1–R15) and every failing test or listed risk from the tester (`independent-tests.md`, causes T1–T10, risks K1–K12) gets a decision here.

- **Fix:** the builder agrees.
- **Won't fix:** with a reason. Dismissing a finding needs Farhaan or a fresh verifier (process step 6); every won't-fix below was approved by Farhaan on 8 Oct.
- **Farhaan decides:** it changes behaviour or the plan.

Farhaan's decisions, and the builder's rule for the order of a call, are decisions 50–55 in `docs/decisions.md`.

## Reviewer findings

| # | Finding (short) | Decision | What happens |
| --- | --- | --- | --- |
| R1 | The AI isn't told the year, and the refusal for a wrong-year date contradicts itself | **Fix** | `{today}` includes the year. The "outside the booking window" message gives the years of both the date and the window. |
| R2 | The AI can call a tool in the end stage, and the call then ends in silence | **Farhaan decides → keep the AI, reword** (decision 50) | The persona's "use a tool" rule is limited to before the goodbye. The end stage says plainly "speak only, call no tools". The hand-off wording no longer echoes the hand_off tool. Pipecat adds the always-available tools to every stage, so a small risk remains. It is written down in the decision and in the defence notes. |
| R3 | Two changes at once ("Friday afternoon at Midtown") lose the second | **Farhaan decides → one call carries several changes** (decision 51) | change_choice takes the same wish fields as start_booking (doctor, place + near, days, time of day, soonest, language) plus the visit type. Every field sent is applied, then fresh options. |
| R4 | The card says "visit: skin check" next to "Agreed: MRI - Knee" | **Fix** (Farhaan approved, decision 53) | When a visit type is accepted, the card's visit description becomes that visit's name. |
| R5 | Three AI passes of silence after identification | **Farhaan decides → pre-list the visit types** (decision 52) | start_booking takes an optional specialty, which the AI picks from the 21 names in stage 1's instructions. Stage 2 opens with that specialty's visit types already listed (`{visit_types}`). change_choice can carry a specialty with a new visit type too. |
| R6 | Renaming the first stage lets a change skip identification | **Fix** | Whether a change moves the call now depends on the card (no caller yet → stay), not on a stage name. Every stage a tool can move to is still checked at load. |
| R7 | "Not Dr. Chen", said before options are on offer, is lost | **Fix** (Farhaan approved, decision 53) | turn_down_doctors is available in every stage. Before options are on offer it works by name, and it records without moving in stages 1–2. |
| R8 | A time taken at the last moment silently drops "as soon as possible" | **Fix** | Going back to choosing after a failed confirm keeps "soonest" and the caller's latest change. |
| R9 | Unexpected errors aren't logged; a failed file write leaves a booking held but not saved | **Fix** | run_tool logs any unexpected error, then lets it surface. The booking is written to the file before the time is marked taken. |
| R10 | Reply shapes; answer_question reads values unchecked; a dead "say"; "Option Option 1" | **Fix** | answer_question replies include `ok`, and its values are checked like every other tool's. The success "say" is dropped from start_booking (the stage reset wipes it). The file's notes now say which replies carry a sentence to say. Option numbers must be numbers only. |
| R11 | Load checks miss turn_down_doctors → visit_type, and placeholders in the persona | **Fix** | The registry lists both moves. A placeholder in the persona or a role message is refused at load. |
| R12 | A refused choose_visit_type still records the wishes sent with it | **Won't fix** (decision 54) | A *refused value* changes nothing. A visit the caller can't book is not a refused value: the doctor, day and so on they said are still their wishes, and dropping them would be a silent loss. Now tested. |
| R13 | End-stage wording: "say this"; read-back twice; "putting you through" then silence | **Fix** (with R2) | The goodbye confirms day, time and doctor briefly, without the whole read-back again. Hand-offs say "a member of staff will call you back", which is what actually happens in a demo. |
| R14 | Test gaps | **Fix** | New builder tests: nothing saved without paths (after a real booking); hand_off from every stage; doctor and place changes in booking; multi-part changes; the alternative-visit path; R12's rule; the real OpenAI request (one tool at a time; tools present in every stage). |
| R15 | README out of date | **Fix** | README describes clinic_agent.json, `call/`, `clinic/`, the bookings file and the call logs. |

## Tester's failing tests

| # | Cause (tests) | Decision | What happens |
| --- | --- | --- | --- |
| T1 | A language with "not", or two languages, gets through (6) | **Fix** | The language is checked by the tool before anything is recorded, using the rules module's own check (now public as `language_problem`). |
| T2 | change_choice accepts near without a place (1) | **Fix** | Refused, as in the other tools (the fields are now shared). |
| T3 | change_choice drops a day sent with a doctor change (1) | **Fix** (decision 51) | Both are applied. |
| T4 | An unknown field name is silently ignored (1) | **Fix** (Farhaan approved, decision 53) | Every tool refuses fields it doesn't have, naming the ones it does. |
| T5 | A finished call can be reopened; one crash (5) | **Fix** (decision 55) | Once booked or handed off, only answer_question and hand_off work. |
| T6 | Stage-2 tools crash before identification (2) | **Fix** (decision 55) | Tools that need a caller refuse politely until start_booking succeeds. |
| T7 | `{options}` shows old options after a visit change (1) | **Fix** | A visit change clears the search result. |
| T8 | Notes for the caller carry instructions for the AI (2) | **Fix** | "Place not recognised" notes go in the AI-only section ("Fix first"), with the other resend-this-value notes. |
| T9 | booked_at uses the computer's clock (1) | **Fix** | booked_at is clinic time, from the call's clock. (The call log's `at` stays the computer's clock: it records when the line was written, on this machine.) |
| T10 | Load checks miss typed settings and placeholder typos; persona placeholders (4) | **Fix** | Settings and lists are type-checked; anything in braces that isn't a known placeholder is refused; persona placeholders are refused. |

These changes alter some fields the tester's tests send (change_choice's `what`/`new_value` becomes the wish fields). Per process step 7 this is proved, not claimed: see "Proving the expected failures" below, filled in after the fixes.

## Tester's listed risks

| # | Risk | Decision | Reason |
| --- | --- | --- | --- |
| K1 | Wishes said during a failed identity try are dropped | **Fix** (Farhaan approved, decision 53) | They're recorded on every try, so they aren't lost. A refused value still records nothing. |
| K2 | Missing settings default to Pipecat's normal behaviour | **Won't fix** | The starter agent (`example_flow.json`) must keep running unchanged. Our agent file sets both settings explicitly, and a test checks that. |
| K3 | Duplicate stages, a tool twice, a tool both in a stage and global | **Fix** | Refused at load. |
| K4 | `global_tools` as text gives a letter-by-letter message | **Fix** | Type-checked: "global_tools must be a list of tool names". |
| K5 | hand_off after a booking replies `handed_off: true` while the card stays booked | **Fix (wording)** | The reply says `handed_off` only when the status changed; the goodbye covers both. |
| K6 | Two identical bookings in the file load without complaint | **Won't fix** | Only our code writes the file, one call at a time (decision 48). |
| K7 | Damaged-line messages use raw Python text | **Fix** | Messages name the missing or bad field. |
| K8 | A saved booking's length isn't checked against its visit type | **Won't fix** | Only our code writes the file, from the catalog's own length. |
| K9 | `{options}` or `{outcome}` used in a stage that can't have them errors mid-call | **Won't fix (now)** | Only possible by editing the stages. The editor (next step) is where stage edits are made and checked. |
| K10 | run_tool with an unknown tool name raises a raw KeyError | **Fix** | A clear error naming the known tools. |
| K11 | Couldn't check how one-tool-at-a-time reaches the AI service | **Fix (test)** | Covered by the new builder test of the real OpenAI request (R14). |
| K12 | choose_option accepts the number 1; "Morning" with a capital M | **No change needed** | Both are plain values read safely. |

## Proving the expected failures

Done per process step 7, after the fixes, with the tester's tests unchanged.

**Where the interface sheet lives.** The tester's tests read the sheet they were given from `INTERFACE.md` at the top of the repo, where it sat in their working folder. It was first filed as `tester-interface-sheet.md` in this folder, so it was moved to `INTERFACE.md` (unchanged: the sheet for build `349b652`).

**Without an adapter:** 33 of the tester's 296 tests fail. 27 of them send change_choice in the old `what` / `new_value` shape that decision 51 replaced. All 24 tests that failed against the build now pass, and all 2,848 older independent tests and all builder tests pass.

**With the throwaway adapter** (never committed): it plays the AI's part by sending each old-shape change_choice in the new shape. `what: "time", days: [...]` becomes `days: [...]`; an empty value becomes "any"; extra fields go along exactly as sent. With it, **6 tests still fail, each from an agreed change:**

| Test | Fails because | Agreed in |
| --- | --- | --- |
| `test_voice_agent_builder::test_clinic_agent_loads_with_safe_settings` | the global tools now include turn_down_doctors | decision 53 (R7) |
| `test_voice_agent_builder::test_global_functions_are_exactly_what_the_interface_shows` | tool descriptions changed (change_choice's fields, turn_down_doctors, hand_off wording, date year) | decisions 50, 51, 53; R1, R10 |
| `test_voice_agent_builder::test_every_stage_function_is_what_the_interface_shows` | turn_down_doctors moved from the booking stage to the global tools | decision 53 (R7) |
| `test_voice_identity::test_found_returning_patient_moves_on_with_their_record` | expects "Thank you, James" in the reply; that sentence was dropped because the stage reset wipes it before anyone hears it (stage 2's instructions now carry the thank-you) | R10 |
| `test_voice_placeholders::test_booking_card_shows_caller_wishes_and_agreed_choices` | expects the caller's first words ("knee MRI") on the card after the visit was accepted; the card now shows the accepted visit's name | decision 53 (R4) |
| `test_voice_stage_moves::test_registry_destinations_match_the_interface[turn_down_doctors]` | turn_down_doctors can now also move to (stay in) visit_type | R11 |

While proving this, the adapter run found **one more real gap** (fixed): `near: true` sent with the place "any" was accepted. Now it's refused like near with no place.

**Next:** these 33 tests, and the interface sheet, go to a fresh tester with a written spec-change note (`round-2-spec-changes.md`), as in the rules-module rounds. The builder doesn't edit them.
