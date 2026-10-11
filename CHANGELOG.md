# Changelog

What each version adds, for someone reading the repository. The full story of how each part was built and checked is in [`docs/build-log.md`](docs/build-log.md).

## 0.3.0 — silence handling, the code-spoken read-back, and the editor (Sun 11 Oct 2026)

New: the Phase 1 editor, and three changes from the voice calls.

- **The editor** (`frontend/`, served by the agent at http://localhost:7860/editor after `npm run build`):
  - the stages as boxes; solid arrows for the AI's own moves, dashed arrows for where a tool's code can move the call;
  - a side panel to edit a stage (name, start, ends the call, instructions, tools, arrows) or the agent (name, model, voice, persona, always-available tools);
  - Save, which runs the agent's own checks and lists every problem in plain words;
  - Test call, which opens the call page beside the editor;
  - the call inspector: the stage, the booking card, every tool call with a short result, every line the code said, and the tokens of each AI reply, updated about once a second.
- **Silence:** "Are you still there?" after 20 s, a goodbye and hang-up after 15 s more, and a 10-minute cap per call (decision 64).
- **The read-back is said by the code** after an option is picked (66), and the booking stage says "Let me check" before searching again (67).
- **Fixes from the reviews:** a caller talking over a line the code says (such as the greeting) no longer jams the call (69); a noise no longer switches the silence check off (70); a "yes" to "Are you still there?" isn't taken as agreeing to the booking (71).
- **Agent file checks** now refuse arrow names the AI service can't use (73), and every problem is worded in stages, arrows and tools.
- **New patients' names** are saved from the letters the caller confirmed, spelled one name at a time, with a word per letter if needed, and marked for staff to check if still unsure (77, 78). Look-alike visit types have our own one-line descriptions and a usual choice (79). The agent no longer promises a booking before it's checked (80).
- **Fixes from the last voice call:** a late rough draft from speech-to-text no longer cancels the agent's answer, and an answer cut off that way is asked for again (81; it caused 25 s of silence); the caller's name isn't said before it's spelled (82); an exact time is searched as morning or afternoon and the caller is told (83).
- **Call log:** new lines for silence, the time limit, what the code said, and tokens per AI reply, and a line when an answer is asked for again.
- **Tests:** builder tests for all of the above; independent: a review of 64/66/67, and one round on the editor (91 tests, 29 of them in a real browser). See `docs/build-log.md`, step 3.

## 0.2.0 — the stages and tools in the voice agent (Thu 8 Oct 2026)

New: the voice agent books through the rules module.

- **`backend/clinic_agent.json`: the agent as data.** Three stages plus an end:
  - identify the caller (new patients' names spelled back; returning patients by name and date of birth);
  - choose the visit type (the specialty's visit types are ready when it's clear);
  - offer up to 3 valid options, read back, and confirm.

  The conversation is wiped on every stage move; each stage's instructions carry what matters, filled in from the booking card. The greeting is spoken by the code the moment the call connects.
- **`backend/call/`: the 9 tools the AI calls,** in plain Python, so the typed test runs will use the same code.
  - start_booking, list_visit_types, choose_visit_type, choose_option and confirm_booking move the booking forward.
  - change_choice can carry several changes in one call; turn_down_doctors handles "someone else".
  - answer_question and hand_off are always available.
  - Every value from the AI is checked, and a refused value changes nothing.
  - The code, not the AI, decides when to move stage.
- **Bookings** are saved to `backend/bookings.jsonl` and reloaded at start-up, so a booked time is never offered again. **Call logs** go to `backend/call_logs/`, one line per stage move and tool call. Neither is committed.
- **The agent format** gains per-stage `tools`, `global_tools`, `{placeholders}`, `history`, `parallel_tool_calls` and `respond_immediately`. Everything is checked at load, with every problem listed at once.
- **`bot.py`:** one session per call, one tool call at a time, English-only speech-to-text.
- **Tests:** 381 builder tests and 3,480 independent tests (632 of them for this step, from two rounds by fresh agents); all pass. Verified by real voice calls (see the build log).
- **`INTERFACE.md`:** the tool interface sheet given to the independent testers.

## 0.1.0 — the catalog and rules module (Wed 7 Oct 2026)

New: `backend/clinic/`, plain Python with no voice code. The voice agent and the typed test runs will both call it.

- **Catalog.** The given catalog is loaded unchanged, plus our own fake map data (`backend/data/location_extras.json`). Both are fully checked at load, and one clear error lists every problem.
- **Fake patients and identity.** There are 6 returning patients (`backend/data/patients.json`). The caller gives name and date of birth, and gets the same reply for every miss. Spelling the last name is the third try; after that the caller is offered to register as new or speak to staff.
- **Fake open times.** They are the same every run: 2 weeks ahead, in San Francisco time. A time can't be booked twice.
- **The six booking rules.** Each is written once, with plain-English reasons. The final check runs before anything is saved.
- **Options.** `find_options` returns up to 3 options (doctor + location + time) that already pass every rule. The caller's wishes are applied newest first. Any wish that can't be met becomes a short note, and every note is true.
- **The booking card.**
  - Changing one choice clears what depended on it.
  - Turning doctors down is a clear instruction (`turn_down_doctors`).
  - Choosing an option is a checked step (`choose_option`).
  - A summary goes into each stage's instructions, and the read-back is built from the card.
- **Facts.** `answer_question` gives small facts about a location, doctor or visit type.
- **What comes in from the AI.**
  - Names are matched forgivingly against our records.
  - Two fixed word lists are read: "no preference" words and words no name has.
  - Everything else is a plain instruction (ids, yes/no, a weekday or date, morning or afternoon).
  - Anything else is refused with a note saying how to send it.
- **Tests:**
  - 276 builder tests (`backend/tests/`);
  - 2,848 independent tests written by fresh agents that never saw the build (`backend/tests_independent/`);
  - run both with `python -m pytest` from `backend/`.
- **Requirements:** `tzdata` (time zones on Windows). Tests need `pytest` (`backend/requirements-dev.txt`).
