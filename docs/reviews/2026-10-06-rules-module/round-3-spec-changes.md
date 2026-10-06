# Spec changes after the second review (6 Oct 2026, evening)

Round 2 found more problems. Farhaan made two more decisions, and the builder fixed everything. This note lists what the module should now do. It **adds to and overrides** `build-decisions.md` and `spec-changes-round-2.md` where they disagree. It describes behaviour, not how the code does it.

## 1. Identity: a step-by-step check (Farhaan's decision; replaces section 2 of the round-2 note)

The goal: a returning caller is identified by full name AND date of birth, the replies never reveal who is a patient, a misheard name gets a fair second chance, and nobody gets stuck.

`PatientDirectory.lookup(name, date_of_birth, spelled_last_name=None)` (date of birth is now a required argument) returns a result with `status` and `caller`, and `to_dict()`:
- `incomplete`: the name has fewer than two words (titles like "Mr." and endings like "Jr" don't count) or the date of birth is missing or not written YYYY-MM-DD. **Nothing is looked up**, so this answer is the same for real and made-up names.
- `not_found`: no record has this name AND this date of birth. **Same answer whether the name or the date was wrong.**
- `found`: exactly one record matches; `caller` is set (returning patient; referrals copied, not shared with the record).
- `same_name_and_birthday`: two or more records share the name and the date of birth. Don't guess: the call goes to staff.
- There are no other statuses (no `need_date_of_birth`, `dob_mismatch` or `invalid_date_of_birth` any more), and no list of names in any result.

Name matching: forgiving by spelling (about 75% letter similarity per word: "Willson", "Kahn", "Sara Jonson" match), never by sound alone ("Ahmad Kim" is not Ahmed Khan; "Robert Tyler" is not Robert Taylor). With `spelled_last_name` (letters, possibly with spaces or hyphens, e.g. "B R O W N"), the spelled surname may differ from the record by at most one letter (one added, removed or changed), and the first name is matched forgivingly as above.

`IdentityCheck` (one per call; the booking card keeps one in `card.identity`) has `attempt(directory, name, date_of_birth, spelled_last_name=None)`, returning an `IdentityStep` with `status`, `say` (the sentence for the agent) and `caller`, and `to_dict()`:
1. `need_both`: name or date missing or unusable. Doesn't count as a try.
2. First miss: `try_again` ("Sorry, I couldn't find you. Could you tell me your full name and date of birth once more?").
3. Second miss: `spell_last_name` (ask them to spell their last name and repeat the date of birth). From now on, an attempt without `spelled_last_name` returns `spell_last_name` again without counting.
4. Miss after spelling: `offer_new_or_staff`: the agent offers to register them as a new patient or put them through to staff. The caller chooses.
- Any time: `found` (caller set) or `hand_to_staff` (same name and birthday).

## 2. Notes are plain records (Farhaan's decision; replaces section 6 of the round-2 note)

Each note in `OptionsResult.notes` is a `Note` with two fields, `kind` and `say` (the sentence). It is NOT a string: use `note.say` for the text. `str(note)` gives the sentence. Notes can be copied, pickled and compared, and `to_dict()` gives `{"kind", "say"}`. Kinds: `not_bookable`, `bad_input`, `doctor_not_found`, `doctor_name_guess`, `doctors_same_name`, `no_other_doctor` (new), `place_unknown`, `place_ambiguous`, `wish_impossible`, `wish_conflict`, `no_times`.

## 3. Dates outside the booking window are refused

A date (YYYY-MM-DD) before today or after today + 14 days gives no options and a `bad_input` note naming the window. Only YYYY-MM-DD is accepted ("20261013" is refused). Blank or `None` days are ignored.

## 4. Other clarified behaviour

- **The newest wish wins, whatever it is.** `Preferences.latest` (or `BookingCard.change_choice`, which sets it to "doctor", "location" or "time") promotes that kind of wish to strongest, even if it's a carried-over choice. The names are shared constants `DOCTOR`, `LOCATION`, `TIME`, `LANGUAGE` in `clinic.card`.
- **Time changes:** `change_choice("time", value)` splits a spoken value into day and time of day ("Thursday morning" → days ["Thursday"], time "morning"; "afternoon" → time only). **Only what's mentioned changes:** "afternoon" keeps an earlier "Thursday". "any day" clears the day; "any time" clears the day and time of day. The `days=` and `time_of_day=` arguments still work.
- **"Someone else, please":** `change_choice("doctor", "")` while a doctor is chosen turns that doctor down for the rest of the call (`Preferences.not_provider_ids`). They aren't offered again. If nobody else can do the visit, a `no_other_doctor` note says so and that doctor stays. Changing the visit type clears the list.
- **Doctor wishes of "any", "anyone", "no preference"** mean no doctor wish.
- **Notes say only true things, in plain wording:**
  - a language nobody available can meet: "None of the doctors available to you for X speaks Y." (Only doctors this caller can actually book, with open times, count.)
  - clashes: "Dr. X isn't available at Y.", "No Spanish-speaking doctor is available with Dr. X.", "There's nothing on Wednesday with Dr. X." ("an Arabic-speaking doctor", not "a Arabic").
  - a place nobody can serve: "…these are the closest alternatives" only when options are ranked by distance; otherwise "…here are other options".
- **Places:**
  - Place words of 4 letters or fewer must match exactly ("main" is not "marina"; "none" is not "Noe Valley").
  - A place name is picked only if the caller said its first distinctive word, or all its words: "Mission" is ambiguous (Mission Bay / Mission District), "Union" is Union Square (Downtown Health Center), but "Bay", "Valley", "Gate" or "Square" alone pick nothing.
  - Streets from our addresses are matched only when the caller says a street word ("Mission Street", "Geary Blvd") or "on X" ("on Main" is Mission Bay Health Center, 4874 Main St; "the one on Geary" is ambiguous). A street word that isn't one of our streets ("Marina Boulevard") is not recognised. "the main one" is not a street.
  - "anywhere", "no preference", "none", "don't mind" → no place wish (`PlaceMatch.kind == "any"`), no note.
  - "near" plus an ambiguous name ("near Market Street", "near the Mission") gives a `place_ambiguous` note but does NOT narrow the options.
  - "on the way to X" counts as "near X". City words ("SF", "San Francisco") are ignored. "mid town" fits "Midtown".
- **Specialty words:** the usual word for the doctor is built from each specialty's name (dermatologist, pediatrician, allergist, dentist, orthopedist, psychiatrist, physical therapist…). "physician" matches nothing.
- **Catalog checks:** `Catalog(raw, extras)` raises `CatalogError` listing every problem, now also for missing required fields (e.g. a location with no "hours") and repeated ids.
- **Fake schedule:** a doctor works at one of their sites per working day, rotating day by day through the booking window, so a doctor with up to 10 sites works at each at least once.
- **`check_booking`** refuses any id that isn't a known id string (lists, dicts, None) politely.
