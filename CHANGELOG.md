# Changelog

What each version adds, for someone reading the repository. The full story of how each part was built and checked is in [`docs/build-log.md`](docs/build-log.md).

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
