# Spec changes after the fifth check (Wed 7 Oct 2026)

The round-5 check found a crash, one more way the code could misread the AI's words, and that the plan's rule "the AI understands speech; the code follows clear instructions" (decision 23) still wasn't applied to days and times. **Farhaan decided the AI fills plain fields for days and times too.** After this round, no part of the code reads the caller's sentences.

This note **adds to and overrides** the earlier notes (`build-decisions.md`, `spec-changes-round-2.md` … `spec-changes-round-5.md`) where they disagree. It describes behaviour, not code.

## 1. Days and times are plain fields (replaces the time-phrase rules from rounds 2–4)

`BookingCard.change_choice("time", new_value="", days=None, time_of_day=None)`:

- `days`: a list where **each entry is one** of: a weekday name ("Thursday"; short forms "thu", "thurs" are accepted), "today", "tomorrow", or a date written YYYY-MM-DD. `[]` clears the day wish.
- `time_of_day`: "morning" (before 12:00), "afternoon" (12:00 or later), or "" to clear it.
- Leaving a field out (`None`) **keeps** it. So `time_of_day="afternoon"` alone keeps an earlier "Thursday".
- `new_value`, if given, is **one day entry** (the same as `days=[new_value]`). Giving both `new_value` and `days` is refused with `ValueError`, changing nothing.
- The AI does the understanding: "this afternoon" → `days=["today"], time_of_day="afternoon"`; "Thursday or Friday morning" → `days=["Thursday", "Friday"], time_of_day="morning"`.

The same values go in `Preferences.days` and `Preferences.time_of_day`. When options are searched, **anything else is refused**: no options and a `bad_input` note saying how to pass it. That includes:

- a day entry that is a phrase ("Thursday morning", "this afternoon", "Thursday or Friday", "next Thursday", "Thursday works");
- a time of day that isn't exactly one of the two ("evening", "morning or afternoon").

No phrase is read any more: there's no "this afternoon", no "Thursday, Friday" splitting, and no filler words.

## 2. "No preference" words count as empty, for every kind of wish

One fixed list ("I don't mind", "no preference", "any", "any day", "any time", "whenever", "whatever"…; spaces, capitals and apostrophes ignored) means the same as `""` in **every** field:

- doctor;
- place;
- language (round 5 refused these for language; that's reversed);
- each day entry (it's skipped);
- time of day.

Each field is independent: "any time" as a day entry clears the day only, not the time of day.

There is no separate "any day" list any more.

## 3. Sentences passed as a doctor's name or a place are refused (replaces round 5, section 2)

If a doctor value or place value contains a word no name has, the search is refused with a `bad_input` note and **no options**. The words are: not, but, except, without, another, other, else, someone, somebody, anyone, anybody, different, instead, please.

Examples: "someone else", "not Dr. Chen", "No, not Dr. Chen", "anyone but Dr. Chen", "another doctor", "the other one", "Dr. Chen please", "anywhere but Downtown".

- For a doctor, the note says to pass just the name, or "" for no wish, and that turning doctors down is `turn_down_doctors`.
- Such a value never brings a turned-down doctor back.
- `change_choice("doctor", …)` itself still never turns anyone down.
- A value that is a "no preference" word on its own ("anyone") is not a sentence: it means no wish.

(Round 5 said such words "match nobody" and give `doctor_not_found` with options. That wasn't true for "not Dr. Chen" or "another doctor", which the spelling matcher turned into wishes for Dr. Chen and Dr. Andre Patel.)

## 4. Choosing an option

New `BookingCard.choose_option(option_id)`:

- puts that option's doctor, place and time on the card and returns the option;
- refuses (`ValueError`, changing nothing) an option number not currently on offer;
- **takes the chosen doctor off the turned-down list at that moment**.

A chosen doctor is never on the turned-down list: any later change also removes them, even a doctor change, unless that change is turning them down (`turn_down_doctors(current=True)`). The card summary never lists the chosen doctor under "not:", even if the card's choices were filled in directly.

## 5. Notes

- **"No other doctor"** (everyone who can do the visit was turned down): it now reuses the "Doctors who can" list.
  - It reads up to three names with their specialty, then "and N more".
  - Same-name doctors get their locations added.
  - It ends "is the only option." for one doctor and "are the only options." for more.
  - Example: "No other doctor can do Annual Well-Woman Exam for you; Dr. Linda Nguyen (OB/GYN) is the only option."
  - It's only given when someone has open times. With nothing open in the window, there's no such note and **no crash**; the usual "There are no open times…" note is given.
- **A list of two or three names** reads "A, B and C" (it used to be "A, B, C").
- **Several doctors turned down for a name:** "The only doctors matching 'Dr. Garcia' who can do this are A and B, whom you turned down. Check whether the caller wants one of them after all." The one-doctor wording is unchanged.
- **A language not in our records** ("Klingon", "Chinese", "español", "ASL"): "None of our doctors is listed as speaking Chinese. Our doctors speak Arabic, English, Hindi, Mandarin, Portuguese, Spanish and Vietnamese."
  - It's kind `wish_impossible`, and options are still offered.
  - The name keeps the caller's capitals ("ASL").
  - A language we have, but that nobody available to this caller speaks, keeps the old sentence: "None of the doctors available to you for X speaks Hindi."
- **A doctor wish nobody can meet, with nothing open at all:** the "Doctors who can: …" sentence is left out rather than left empty.

## 6. Smaller changes

- **Language:** two language names ("English Spanish") are refused like other non-names. "Mandarin Chinese" still means Mandarin.
- **`turn_down_doctors(provider_ids="prov_001")`:** a single id on its own (not in a list) is accepted.
- **Map data:** an empty `neighbourhood` ("") is fine.
- **Patient data:**
  - `date_of_birth` must be a real date written YYYY-MM-DD ("12/03/1984" and "1990-02-30" are refused);
  - a repeated patient id is refused;
  - every problem is still listed in one `CatalogError`.
