# Spec changes after the fourth check (Wed 7 Oct 2026)

The round-4 check found that the "someone else" area kept producing false or silly sentences. The cause was the code trying to understand the caller's own words ("someone else, please", "no, not Dr. Chen", "any language"). That goes against the plan's decision 23: **the AI understands speech; the code follows instructions and checks them.** Farhaan decided the code should stop reading phrases. The AI now gives a clear instruction, and the code follows it exactly.

This note **adds to and overrides** the earlier notes (`build-decisions.md`, `spec-changes-round-2.md`, `spec-changes-round-3.md`, `spec-changes-round-4.md`) where they disagree. It describes behaviour, not code.

## 1. Turning doctors down is its own instruction

`BookingCard.turn_down_doctors(catalog, provider_ids=(), on_offer=False, current=False)`. The AI says exactly who, using any mix of:

- `provider_ids`: these doctors (the tool layer turns a spoken name into ids, and asks the caller "which one?" if the name fits several doctors);
- `on_offer=True`: every doctor in the options currently on offer (`BookingCard.remember_offer`);
- `current=True`: the chosen doctor, or if none is chosen, the doctor carried over from earlier.

It counts as a doctor change: it clears doctor, place and time, carries the place over as a weaker wish, clears any doctor wish, marks the doctor as the latest change, and returns the stage to go to (`booking`, or `visit_type` if no visit type is chosen).

If the instruction can't be followed, it raises `ValueError` with a plain message and **changes nothing**:

- nothing given ("Say which doctors to turn down…");
- `current=True` with no chosen or carried-over doctor;
- `on_offer=True` with nothing on offer;
- an id that isn't a doctor in the catalog.

Turned-down doctors are left out of later searches for the rest of the call, except:

- **nobody else can do the visit**: they're offered after all, with a `no_other_doctor` note that names only the doctors who can do it ("…; Dr. Linda Nguyen is the only option." / "…; A, B and C are the only options.");
- **the caller names one again** (see 3);
- **the caller picks one anyway** (e.g. from a `no_other_doctor` offer, or after naming them again): once chosen, that doctor is off the list for good, even after later changes.

A change of visit type starts the list again.

## 2. `change_choice` never reads instructions from the words

- `change_choice("doctor", X)`: X is only ever a doctor's name, or `""` for no doctor wish. "someone else", "not Dr. Chen" and similar are **no longer understood**. They are treated as a name, which matches nobody, so the agent gets a `doctor_not_found` note (the mistake is visible, not guessed at). Passing `""` no longer turns anyone down.
- `change_choice("language", X)`: X is one language name ("Spanish", "Mandarin Chinese" counts as Mandarin), or `""` to clear the wish. "any" is **no longer** read as "clear".
- The "turned down by name" list on the card (`Preferences.not_doctor_names`) has been **removed**. Only `not_provider_ids` remains.

## 3. Naming a turned-down doctor again (replaces round-4 change 4)

A doctor name brings a turned-down doctor back **only if the name picks out that one doctor**: "Dr. Daniel Chen", "Daniel Chen", "Dr. Daniel Chen's". Two doctors with exactly the same full name count as one name.

A name that fits several different doctors ("Dr. Chen", which fits seven) does **not** bring back a turned-down Chen. If the only matching doctor who can do the visit was turned down, the note is a `wish_conflict`: "The only doctor matching 'Dr. Chen' who can do this is Dr. Daniel Chen, whom you turned down. Check whether the caller wants that doctor after all."

A doctor named back and then chosen stays back after any later change (day, place, language). Nothing then calls them turned down, and the card summary no longer lists them under "not:".

## 4. Notes about turned-down doctors

- "X is only possible with …, whom you turned down." names only turned-down doctors who **really have open times meeting that wish**.
- It always starts with a capital letter. For days and times the subject is the day phrase without "on": "Wednesday 7 October is only possible with Dr. Daniel Chen, whom you turned down."; "The morning is only possible with …".
- The card summary's "not: …" lists the doctors still turned down, by full name, sorted.

## 5. Values that aren't what the instruction asks for are refused

These give no options and a `bad_input` note saying how to pass the value (the AI then retries):

- a language value that isn't one or two words naming a language ("any language", "not Spanish", "no Spanish please", "don't mind"). An unknown but real-looking name ("Klingon") is still kept, and gives the true "none of the doctors… speaks Klingon";
- a time wish with both "morning" and "afternoon" in it ("Thursday morning or Friday afternoon", "morning or afternoon"). The note says to search one day at a time, or leave the time empty.

## 6. Smaller changes

- **"No preference":** one list for "no preference" (clears day and time, place, doctor) and a separate list for "any day" (clears the day only; "any day" as a time of day means no time wish). They don't overlap. "any time works" now counts as no preference.
- **A house number we don't have** ("near 9999 Geary", "9999 Geary Blvd") means somewhere on that street. Both Geary clinics are mentioned (ambiguous, a note), and the search is **not** narrowed to them. A house number we do have still picks that clinic ("4455 Geary Blvd").
- **Named dates:** "Nothing is open on Saturday 10 October for Skin Cancer Screening; here are other options." (no "in the next 14 days" when only actual dates were asked for; weekday names still get it).
- **Doctor words:** the regular rule (dermatology → dermatologist, allergy → allergist, physical therapy → physical therapist) plus three irregular words: dentist, orthopedist, pediatrician. "orthopedician" is no longer produced.
- **Data checks:** the catalog and our map data are fully checked before anything is built, and one `CatalogError` lists every problem:
  - opening hours with a time that doesn't exist ("8:00-25:00");
  - an id that isn't text (e.g. a list), reported rather than crashing;
  - optional fields of the wrong kind when present (`capabilities` must be a list of text; `required_capability` text);
  - map data: latitude a number from −90 to 90, longitude from −180 to 180, landmarks as [latitude, longitude], `also_called` a list of text, `neighbourhood` text;
  - doctors pointing at unknown locations or visit types.

  Patient data is checked the same way: every record must be a record with text `id`, `name` and `date_of_birth`, and `referrals_on_file` (if present) a list of text. Every problem is listed in one `CatalogError`.
