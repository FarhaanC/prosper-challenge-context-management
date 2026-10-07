# Changelog

What each version adds, for someone reading the repository. The full story of how each part was built and checked is in [`docs/build-log.md`](docs/build-log.md).

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
