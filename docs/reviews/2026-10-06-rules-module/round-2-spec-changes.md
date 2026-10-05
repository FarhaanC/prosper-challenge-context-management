# Spec changes after the first review (6 Oct 2026)

The first independent test round and code review found problems. Farhaan (the candidate) made four decisions, and the builder fixed everything. This note lists what the module should now do. It **adds to and overrides** `build-decisions.md` where they disagree. It describes behaviour, not how the code does it.

## 1. When wishes meet: the newest wins, and notes are always true (Farhaan's decision)

The caller's wishes (a doctor, a place, a day/time, a language) narrow the valid options, strongest first:
1. the most recent change (`Preferences.latest`, set to "doctor", "location", "time" or "language" by `BookingCard.change_choice`, or set directly);
2. other things the caller said: doctor (`doctor_name_heard`), then place (`location_hint`), then day/time (`days`, `time_of_day`), then language;
3. choices carried over from earlier in the call (`preferred_provider_id`, `preferred_location_id`).

- A wish is applied only if at least one bookable option survives it, together with every stronger wish already applied. Otherwise it is set aside, and a note explains why.
- **Every note must be true.** A note saying a wish can't be met for anyone (e.g. "Nothing is open on Monday…", "None of the doctors who offer X speaks Klingon.") may only appear when no valid option anywhere meets that wish. When the wish only clashes with a stronger wish, the note says so (e.g. "Dr. Daniel Chen isn't available at Midtown Medical Group.").
- The change table, as before: changing the visit type clears everything and goes to `visit_type`; changing doctor, location or time clears doctor, location and time and goes to `booking` (or `visit_type` if no visit type is chosen yet). Whatever was chosen and isn't the thing being changed is carried over as a weaker wish. The card holds at most one doctor wish (heard name OR carried-over id) and one place wish (hint OR carried-over id) at a time.
- `change_choice("time", "Thursday")` (a plain value) records "Thursday" as the day wish. "any day" / "any time" clears the day or time wish. An unknown thing to change raises `ValueError` and clears nothing.

## 2. Identity: name AND date of birth (Farhaan's decision; replaces decision 29)

`PatientDirectory.lookup(name, date_of_birth=None)` returns a result whose `status` is one of:
- `not_found`: no record has this name. The caller is a new patient. A surname alone (with or without a title like "Mr.") never matches. A name that only *sounds* like a record but is spelled differently ("Ahmad Kim" vs Ahmed Khan) does not match. Close misspellings do match (about 75% letter similarity per word, e.g. "Kahn" for Khan, "Willson" for Wilson, "Sara Jonson" for Sarah Johnson), but clearly different names don't ("Robert Tyler" is not Robert Taylor).
- `need_date_of_birth`: the name matches but no date of birth was given. No caller details are returned.
- `invalid_date_of_birth`: the date wasn't given as YYYY-MM-DD.
- `dob_mismatch`: the name matches, the date doesn't. No caller details. The agent asks again; it never quietly treats the caller as new.
- `found`: name and date of birth match exactly one record; `caller` is set (returning patient, referrals copied, not shared with the record).
- `several`: more than one record has the same name AND date of birth (shouldn't happen).

There is no list of candidate names in any result: reading one patient's name to another caller would be a privacy problem.

## 3. Places

- Treated as "near" (rank by distance, don't restrict): near, nearby, close to, **closer to**, closest to, around, next to, not far from, by, **the one near**, on the way to.
- A location's neighbourhood counts as one of its names: "the Hayes Valley one" means Midtown Medical Group (restrict); "near Hayes Valley" ranks by distance from it.
- "District" phrasing works: "the Marina District" means North Gate Health Center (neighbourhood Marina), and "Richmond District" means Richmond Care Center. "Castro District" is the Castro landmark.
- Streets from our addresses: "near Mission Street" means North Beach Specialty Center (481 Mission St), *not* Mission District. "the one on Geary" is ambiguous (Downtown Health Center and Sunset Community Clinic are both on Geary Blvd).
- **"the Mission" is ambiguous** (Farhaan's decision): the agent asks. The "The Mission" nickname was removed from `location_extras.json`.
- A blank place (spaces only) is no wish: no note.

## 4. Doctor names

- `Catalog.match_providers(heard)` returns the best tier of matches, each with a quality (`exact`, `close spelling`, `sounds alike`, via `.describe()`), `.is_exact`, and `.first_name_matched`. `find_providers_by_name` returns just the doctors from the same tier.
- An exact first name beats a sounds-alike surname ("Dr. Grace" is Dr. Grace Rodriguez, not the Garcias). At equal quality, the surname wins ("Dr. Garsha" is the three Garcias, not Grace).
- A possessive is ignored ("Dr. Garcia's" is the Garcias).
- A wrong first name falls back to the surname ("Dr. John Garcia": the Garcias, with `first_name_matched` False).
- In `find_options`, an approximate match produces a note of kind `doctor_name_guess`, so the agent checks with the caller.

## 5. Day and time values

- Accepted days: weekday names and short forms ("Thursday", "thu", "thurs"), "today", "tomorrow", dates as YYYY-MM-DD. Accepted times: "morning" (before 12:00), "afternoon" (12:00 or later). Blank values and "any" mean no wish. Case doesn't matter.
- Anything else ("next Thursday", "lunchtime", "evening", "Oct 13") makes `find_options` return **no options** and a note of kind `bad_input` saying how to phrase it, so the AI retries. "evening" is no longer supported.

## 6. Notes have a kind

Each note in `OptionsResult.notes` is a string (it can be read, joined and searched) with a `.kind` attribute. Kinds: `not_bookable`, `bad_input`, `doctor_not_found`, `doctor_name_guess`, `doctors_same_name`, `place_unknown`, `place_ambiguous`, `wish_impossible`, `wish_conflict`, `no_times`. `OptionsResult.to_dict()` gives notes as `{"kind": ..., "say": ...}`.

## 7. Other behaviour

- **Option numbers keep counting up through a call:** `find_options(..., first_option_number=N)` numbers options from N. `BookingCard.remember_offer(options)` records what's on offer; `BookingCard.offered(option_id)` returns that option only if it's currently on offer (older ones return None), and `next_option_number` advances.
- **`soonest=True`** ranks options by time even when a place was named.
- **`alternatives_for(catalog, caller, visit_type_id)`** returns a primary-care visit (General, Family Medicine or Internal Medicine) the caller can book: a new-patient visit for new patients, a follow-up for returning ones. The agent must not promise it leads to a referral.
- **`Schedule.book(provider, start, minutes)`** raises `SlotTaken` if any block it needs isn't free (already booked through the agent, or not an open block).
- **`clinic_now()`** returns the current San Francisco time as a plain datetime. All times in the module are San Francisco local time.
- **`Catalog(raw, extras)` checks its data** and raises `CatalogError` listing every problem: a location without coordinates, unreadable opening hours, a doctor pointing at an unknown location or visit type. `PatientDirectory` raises `CatalogError` for a record missing id, name or date of birth.
- **Unknown visit types** are refused politely, never with a crash, by `can_book_visit_type`, `find_options` and `check_booking`.
- **`answer_question(catalog, "doctor", name)`** returns every doctor in the best tier (e.g. all 7 Dr. Chens) and a message with the count; approximate matches are flagged in the message.
- **`Catalog.match_specialty`** also accepts the word for the doctor: "dermatologist", "pediatrician", "allergist", "physical therapist", and either half of "Allergy/Immunology".
- **The 2-week window:** times are offered for today plus the next 14 days.
- **"Doctors who can: …" lists** in notes name each doctor with their specialty; two doctors with the same name get their locations added.
