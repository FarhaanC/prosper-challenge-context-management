# Triage: review of decision 77 (new patients' names from confirmed letters)

Build reviewed: `39845de`, made after Farhaan's Sun 11 voice call (the agent read back "F, A, R, H, A, A, N" and saved "Farhan"). One fresh reviewer (Farhaan's choice). Before deciding N4 and N5, Farhaan asked for research into how other voice-AI phone agents capture names, and for the challenge brief to be checked on visit types; he then accepted the builder's recommendation: decisions 78–80.

| # | Finding (short) | Sev. | Decision | What was done |
| --- | --- | --- | --- | --- |
| N1 | Letters joined by hyphens ("C-H-I-D-A", as speech-to-text wrote them in the call) were saved as written | high | Fix | Hyphens between single letters count as gaps; "F-A-R-H-A-A-N" and "C-H-I-D-A." become "Farhaan", "Chida". Tested with the call's own forms. |
| N2 | Letters mixed with words ("F, A, R, H, double A, N") were saved as a name | med | Fix | Refused, with how to send it ("double A" is A, A; "A as in apple" is A). Field descriptions say the same. |
| N3 | A returning caller who registers as new could reuse the third-try last name, and nothing said to spell both names | med | Fix | The tool's description says to confirm both names' spelling first; a call with only the old last name is refused (both names needed); N1 covers hyphenated forms. Tested. The optional "refuse the same third-try value" was not built: the AI must still send a first name, and the read-back is what confirms it. |
| N4 | The visit-type stage was told to explain differences the data doesn't have, and had no way out of "any of them" | med | Fix (decision 79, Farhaan) | The brief's data notes name these look-alikes as messiness to handle, but give no descriptions. We added our own one-line descriptions for 9 look-alike groups (`backend/data/visit_type_notes.json`, checked at load like the map data), each with a "usual" choice. The agent describes a visit only from that line; after one more "any", it books the usual choice, says which, and says it can be changed. |
| N5 | Spelling could loop forever | med | Fix (decision 78, Farhaan after research) | Letters first; if wrong, a word per letter ("A as in apple"); if still wrong, no more asking: start_booking with `name_not_confirmed`, the name as heard is saved for that part and marked, the booking file has `"name_confirmed": false`, and the goodbye says staff will check the spelling. |
| N6 | 313 independent failures unrecorded; decision 77 missing; build log out of date | med | Fix | Decisions 77–80 recorded; the adapter result is below; build-log and defence-notes updated. |
| N7 | "Mary Ann" lost its space; "McDonald" became "Mcdonald"; "exactly" was untrue | low–med | Fix | Names with a space or hyphen are sent as words (descriptions say so); a name sent with mixed capitals is kept as sent; "exactly" removed. |
| N8 | Curly apostrophes and separate accent marks were refused | low | Fix | Curly and back-tick apostrophes become ', and accents are joined to their letters (NFC) before checking. |
| N9 | Stray words and sentences were accepted as names; the test that seemed to cover it didn't | low | Fix | A short list of words that are never names ("yes", "double", "as", "space", …), at most 3 words and 40 letters, no hyphen or apostrophe at the start or end. The test now uses a sentence without punctuation. |
| N10 | `full_name` unused for new patients; log shows two names | low | Fix | Its description now says what it's for (finding returning patients; the heard name when spelling can't be confirmed). A `saved_name` in the reply was tried and removed: the next stage is already told the saved name, and the tester's tests (rightly) expect a bare `{"ok": true}`. |
| N11 | Tests missed the cases that matter | low | Fix | Added: the call's hyphenated forms, "double A", "A as in apple", spoken "apostrophe", stray words, curly apostrophe, mixed capitals, the unconfirmed path end to end (booking file and goodbye), the register-as-new path, the whole first name in the thank-you, the descriptions in the list, and the notes file's load-time checks. The instruction tests still only prove the text is there; what the AI does is for the voice call and the AI-played callers. |
| N12 | Docstring, the thank-you used only "Mary" of "Mary Ann", refused calls drop wishes | low | Fix / won't fix | Docstring corrected; the thank-you uses the whole spelled first name. Dropping the wishes on a refused call stays (a refused value changes nothing, decision 54; the wishes are still in the stage's conversation). |

## The independent tests

On `39845de`, 312 older independent tests failed because their new-patient callers send no letters. **Proved, not claimed (P3):** a throwaway adapter that plays the AI by adding the letters (taken from the first and last word of `full_name`) leaves 3 failures across the voice and editor tests (694 tests), on the fixed version too:
- `test_choose_option_handler_stays`: decision 66 (known).
- `test_log_lines_record_every_stage_move_and_tool_call_in_order`: the adapter's own added letters appear in the logged message, so the logged message no longer equals what the test sent. That's the adapter, not the code.
- `test_saving_unchanged_agent_with_windows_line_endings`: needs the Windows line endings of a Windows checkout (the Linux-side copy differs).

The editor's inspector tests were pointed at the call logs that existed when they were written (newer calls from Sun 11 change which log is "newest"). All 2,848 older rules-module tests pass.

## Spec-change note for the next fresh tester

- A new patient (`returning` false) needs `spelled_first_name` and `spelled_last_name` (the letters the caller confirmed), or `name_not_confirmed` true with `full_name` as heard. The saved name is built from the letters. See INTERFACE.md (start_booking).
- Look-alike visit types carry `description` and `usual_choice` in `visit_types_for`, and a "  What it is: …" line under them in `{visit_types}`.

## After the fixes: Farhaan's call (Sun 11, 22:42)

**Found by the call, not by any test or the review:** the AI sent the confirmed letters as a list (`["F", "A", "R", …]`) instead of one text. The field descriptions said "one per entry", the same words the `days` field uses for a real list, so the AI copied that form. The code refused it twice with "spelled_first_name must be text" (no example), and the agent gave up, telling the caller staff would follow up, without calling hand_off.

**Fixed:** a list of letters is read like the same letters as text; the descriptions say "as one text with commas between letters"; a value of another kind is refused with the example. A test replays the call's exact values. Builder 457 pass; adapter run as above (the line-endings failure is gone on this copy).

**Lesson:** the tool schema says "string", but the AI service doesn't enforce it, so the wording of a description can change the shape of what comes back. Every tool test so far had sent the shape the code expected.

**To check in testing:** the agent promised "a member of staff will follow up" without handing off (no hand_off call), which is a promise the code never made.
