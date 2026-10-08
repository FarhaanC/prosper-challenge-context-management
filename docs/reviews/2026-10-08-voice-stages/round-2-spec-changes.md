# Spec changes after round 1 (for the round-2 tester)

What changed in the interface and behaviour since build `349b652`, from the triage (`triage.md`) and decisions 50–55. Tests written against the old interface need updating only where these changes reach them. `INTERFACE.md` at the top of the repo is regenerated for the new build.

## change_choice has a new shape (decision 51)

- **Old:** `{"what": "time", "days": [...], "time_of_day": ...}`, `{"what": "doctor", "new_value": "Dr. Chen"}`, and so on.
- **New:** the same wish fields as start_booking, each sent only if it changes:
  - `doctor_name`
  - `place` (with `near`)
  - `days`
  - `time_of_day`
  - `soonest`
  - `language`
  - `visit_type` (a different kind of visit, in the caller's words), with an optional `specialty`.
- **Several fields can go in one call.** For example `{"days": ["Friday"], "time_of_day": "afternoon", "place": "Midtown"}`.
- **`"any"` drops a wish:** `doctor_name: "any"`, `place: "any"`, `days: ["any"]`, `time_of_day: "any"`, `language: "any"`. An empty string or empty list counts as not sent.
- **These are refused** (the card and the options on offer stay as they were):
  - nothing sent;
  - `specialty` without `visit_type`;
  - `near` without a real place (including the place `"any"`);
  - a field it doesn't have (e.g. `what`).
- **The order things are applied in:** the visit type first, then language, time, place, doctor. The strongest kind sent becomes the "latest" change.
- **Where the call goes after a change is unchanged:**
  - before the caller is identified, or in the visit_type stage: recorded, and the call stays;
  - in the booking stage: fresh options, and the booking stage is rebuilt;
  - a visit-type change from the booking stage: back to visit_type.
- **A time change** resets "soonest" unless `soonest` is sent in the same call.

## turn_down_doctors is available in every stage (decision 53)

- It is a global tool now: it is no longer in the booking stage's own list.
- Before options are on offer it works by `doctor_name` (or `doctor_id`). It records without moving, as change_choice does: before identification, and in the visit_type stage.
- It can move to `visit_type` (stay) or `booking`.

## start_booking (decisions 52, 53)

- **New optional `specialty` field.** One of the 21 names, matched as list_visit_types matches them; an unknown name is refused. When it's sent and the caller is found or registered, stage 2's `{visit_types}` lists that specialty's visit types.
- **The success reply is `{"ok": true}`** (no "say": the stage reset wipes it). Stage 2's instructions tell the AI to thank the caller by first name.
- **Wishes are kept on a failed identity try.** Wishes and the visit description sent with a try that doesn't find the caller are recorded, as long as every value is usable. A refused value still records nothing.

## What the AI is shown

- **`{today}`** is now e.g. "Tuesday 6 October 2026 at 9 AM (clinic time, San Francisco)": it includes the year.
- **New `{visit_types}` placeholder.** Shows the listed specialty's visit types with ids, each "can book" or "can't book (reason)"; or "Not looked up yet: call list_visit_types…".
- **Stage 1 now shows `{specialties}` too.**
- **A wrong-year date** gets: "Tuesday 15 October 2024 is outside the booking window (6 October to 20 October 2026)."
- **"Place not recognised" notes** (an unknown place name) are now under "Fix first (don't read this to the caller…)", not "Tell the caller first".
- **After a visit-type change, `{options}` has no search to show** (it raises an error, as before any search) until a new visit type is accepted.
- **The card's visit description** becomes the accepted visit type's name when choose_visit_type is accepted (decision 53).
- **The goodbye wording (`{outcome}`):**
  - **Booked:** the read-back, then "Confirm the day, time and doctor in one short sentence (not the whole read-back again)…"
  - **Hand-offs:** "A member of staff will call the caller back about this…". The words "putting through" are no longer used.
  - **The end stage's instructions** end with "speak only. Don't call any tool…".

## The order of a call (decision 55)

- **Once the call is booked or handed off,** every tool except answer_question and hand_off is refused, and changes nothing.
- **Until start_booking succeeds,** list_visit_types, choose_visit_type, choose_option and confirm_booking are refused ("Identify the caller first…").
- **Any tool, any time:** a field the tool doesn't have is refused, naming the fields it does have.

## Smaller changes

- **answer_question:**
  - its reply has `ok` (true when found);
  - `about` and `name` must be text.
- **choose_option:**
  - the option number must be digits ("2" or 2);
  - "Option 2" is refused.
- **hand_off:**
  - the reply's `handed_off` is true only when the call's status changed (it stays "booked" after a booking);
  - its description and the goodbye say staff will call back.
- **The bookings file:**
  - `booked_at` is the call's clinic time, to the minute;
  - damaged-line messages name the problem: "missing start", "unknown doctor id …", "isn't a date and time", "isn't a number of minutes", "not a JSON record".
- **Load-time checks (agent file):**
  - `parallel_tool_calls` must be true or false;
  - `global_tools` and `tools` must be lists of names, with no repeats, and no tool both in a stage and global;
  - no two stages may have the same name;
  - anything in braces must be a known placeholder (so `{Options}` and `{booking card}` are refused);
  - placeholders in the persona or a role message are refused.
- **The always-available tools** are now answer_question, change_choice, turn_down_doctors and hand_off.
- **The booking stage's own tools** are choose_option and confirm_booking.
- **run_tool with an unknown tool name** raises a ValueError naming the tools.
