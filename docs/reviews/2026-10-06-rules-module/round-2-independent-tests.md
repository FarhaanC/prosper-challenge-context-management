# Round 2 independent test report: catalog and rules module

| | |
| --- | --- |
| **Date** | Tue 6 Oct 2026, early morning |
| **Version tested** | Commit `d4983c2` ("Fix all 17 findings from the rules-module review") |
| **Who** | A fresh AI agent (not the round-1 tester) that never saw the build or fix conversations. It got the plan, the round-1 spec, the round-1 test report, the [spec changes](round-2-spec-changes.md) from Farhaan's decisions, the raw data, the code (to learn how to call it) and the round-1 independent suite to take over. It did not see the builder's tests or the triage. |
| **Its tests** | [`backend/tests_independent/`](../../../backend/tests_independent/): round-1 files updated where the spec changed (listed below), plus `round2_reference.py` and five new `test_round2_*.py` files. |
| **Result** | 632 tests: 601 passed, 31 failed (11 separate problems). It confirmed that all 30 earlier failures came only from the date-of-birth spec change. |
| **What happened next** | See [`triage.md`](triage.md), round 2 section. |

The agent's report follows. The builder session saved it (agents can't write files here); the only edit is that scratch folder paths were shortened to repo paths.

---

### 1. Summary

**Before my changes:** 296 tests, 266 passed and 30 failed.
**After my changes:** 632 tests (the 296 old ones plus 336 new ones), 601 passed and 31 failed.
- All 296 old tests now pass.
- The 31 failures are all new tests. They come from **11 separate problems**.

**Verdict.** The core is still solid. Round 1's whole-catalog rule checks, time-slot rules and repeatability all still hold.

Most of the new behaviour works as specified:
- the name-plus-date-of-birth identity check, with no names leaked;
- notes saying a doctor can't do a visit (I checked 1,101 of them against the raw data, and every reason was true);
- the option numbering, `SlotTaken`, `clinic_now`, catalog checks, `alternatives_for`, specialty words and `answer_question`.

I compared about 4,800 random wish combinations against my own model of the "newest wish wins" order. Every single disagreement came from one bug: **a location change never becomes the strongest wish.** That is exactly the situation the order was designed for.

The second weak area is place words. One phrase the spec lists isn't understood, and a few short words get matched to the wrong clinic.

### 2. Tests I edited

| Test(s) | Old expectation | New expectation | Reason |
|---|---|---|---|
| `test_card.py`: `test_demo_skin_check_then_knee_mri`, `test_time_change_keeps_doctor_and_place_when_they_fit`, `test_read_back_matches_card` | `lookup("James Wilson")` gives a caller | `lookup("James Wilson", "1984-03-12")` | Spec change 2: *"need_date_of_birth: the name matches but no date of birth was given. No caller details are returned."* |
| `test_options.py`: `test_knee_mri_returning_with_referral`, `_with_old_garcia_wish`, `_near_downtown`, `_closer_to_downtown_baseline_phrase`, `_the_midtown_one`, `_the_sunset_one_not_possible`, `test_options_disappear_after_booking` | same | same, with James Wilson's date of birth | same line |
| `test_rules.py`: `test_obgyn_bookable_for_returning_emily_brown`, `test_knee_mri_returning_no_referral_refused`, `test_knee_mri_james_wilson_two_options` | same | date of birth added (Emily: 1988-01-19) | same line |
| `test_patients.py::test_exact_name_found_with_referrals` (6 tests) and `test_misheard_names_found` (9 tests) | name alone gives "found" | name alone gives `need_date_of_birth` (new check added); name plus date of birth gives "found" | same line |
| `test_patients.py::test_same_name_needs_date_of_birth` | name alone gives "several" with 2 candidates | `need_date_of_birth`, and no candidate list at all | *"There is no list of candidate names in any result"* |
| `test_patients.py::test_returned_caller_does_not_share_list_with_record` | name only | date of birth added | same as row 1 |

**The builder's claim is confirmed.** All 30 old failures came only from looking a patient up by name alone:
- 17 tests expected "found" or "several" and now got `need_date_of_birth`;
- 13 tests then crashed on the empty caller.

Once I added the date of birth, every one of them passed with no other change. So none of them was hiding a code bug.

I also corrected 2 of my own new tests:
- **"Mei Wang".** I first said it must not match Mei Wong. But Wang and Wong are exactly 75% alike, so the spec's own rule says it matches.
- **"Garcias'".** This odd plural form is now replaced with a normal possessive.

**One warning about the old suite.** Two round-1 tests now pass for the wrong reason: `test_language_note_is_true_when_doctor_wish_also_set` and `test_named_place_note_is_true_when_doctor_wish_also_set`. They search for the old note wording, which no longer exists. My new comparison tests check the real behaviour instead.

### 3. Failures that remain, most serious first

**F1. A location change never becomes the strongest wish.** (11 tests: `test_location_change_beats_a_said_doctor`, `test_latest_location_set_directly_beats_said_doctor`, `test_four_way_clash_each_latest[location]`, 8 random-combination seeds)
- **Spec:** the most recent change (`latest`, set to "doctor", "location", "time" or "language") is strongest of all.
- **Reproduction:**
  - A new caller wants Skin Cancer Screening and says "Dr. Daniel Chen". The visit type is chosen; no option is picked yet.
  - Then: `change_choice("location", "the Midtown one")`. `latest` becomes `"location"`.
  - `find_options` offers **3 options with Dr. Daniel Chen at Downtown and Richmond**.
  - The note says *"Midtown Medical Group isn't available with Dr. Daniel Chen."*
  - Expected: Dr. Kenji Kim at Midtown, and a note that Dr. Chen isn't available there.
- **Cause, in plain terms:** the code calls the place wish "place", but the card records the change as "location". The two words never match, so a location change never gets promoted.
- **Verdict:** code bug.
- **How serious:** high. It is round-1's F1 again, whenever the doctor was *said* rather than *picked*. The caller asks for Midtown and gets their old doctor elsewhere. Every other `latest` value worked in all 4,800 combinations.

**F2. "On the way to" isn't understood.** (3 tests)
- **Spec:** "on the way to" is listed as a "near" phrase.
- **Reproduction:** `resolve_place("on the way to Downtown")` gives `none`. `find_options` adds the note *"I don't recognise the place 'on the way to Downtown'…"*.
- **Cause:** "way" is treated as a street word, like "Broadway".
- **Verdict:** code bug.
- **How serious:** medium. The agent asks again instead of using the place.

**F3. Short words get matched to the wrong clinic.** (7 tests)
- **Spec:** decision 24 says "Unknown places are reported, not guessed." Mission Bay Health Center is at 4874 Main St.
- **Reproductions:**

| What the caller says | What the module decides | What happens |
|---|---|---|
| "the one on Main" / "on Main" | North Gate Health Center | options limited to North Gate ("Main" is spelled close to "Marina") |
| "Marina Boulevard" | Mission Bay Health Center | options limited to Mission Bay |
| "Bay Area" | Mission Bay Health Center | options limited to Mission Bay |
| "Glen Park" | Golden Gate Park | options ranked by distance from the wrong place |
| "Cole Valley" | Noe Valley | options ranked by distance from the wrong place |

- **Verdict:** code bug. Spelling-closeness matching is too loose on short words.
- **How serious:** medium. "The one on Main" quietly limits the options to the wrong clinic.

**F4. A language note that isn't true.** (2 tests)
- **Spec:** "Every note must be true."
- **Reproduction:** a new patient wants Skin Cancer Screening with a Hindi speaker. The note says *"None of the doctors who offer Skin Cancer Screening speaks Hindi."* But Dr. Wei Sato does offer it and speaks Hindi; he just isn't taking new patients. The same happens for Full Body Skin Exam and Cosmetic Consultation.
- **Verdict:** code bug in the wording. The decision itself is right.
- **How serious:** medium-low. The agent says something false out loud.

**F5. "Any time" doesn't clear a "morning" wish.** (1 test)
- **Spec:** "'any day' / 'any time' clears the day or time wish."
- **Reproduction:** set the time of day to "morning", then call `change_choice("time", "any time")`. The day list is cleared, but **"morning" stays**.
- **Verdict:** spec ambiguity that leans towards a bug.
- **How serious:** low-medium. The caller says "any time is fine" and still only gets mornings.

**F6. "Closest alternatives" when the options are sorted by time.** (1 test, 36 visit types)
- With `soonest=True` and a clinic that can't do the visit, the note says *"these are the closest alternatives"*. But the options are sorted by time, not distance.
- **Verdict:** code bug in the wording. **How serious:** low.

**F7. Grammar in a spoken note.** (1 test)
- The note reads *"A Arabic-speaking doctor isn't available with Dr. Kenji Kim."* (should be "An"). **How serious:** low.

**F8. Crashes on strange inputs.** (2 tests)
- `check_booking` crashes ("TypeError", meaning the input has the wrong shape) when the visit type, doctor or location is passed as a list or dict.
- `Catalog` crashes with a `KeyError` (a missing field) instead of the expected `CatalogError` when a location has no "hours" field at all.
- **Spec:** unknown visit types should be refused "never with a crash", and broken data should raise `CatalogError`.
- **How serious:** low.

**F9. A carried-over doctor marked as the latest change.** (1 test)
- Setting `latest="doctor"` directly while the doctor is only carried over: the code still treats it as weak.
- **Verdict:** spec ambiguity. `change_choice` never produces this, but the spec says `latest` can be "set directly".

**F10. "Downtown SF" and "downtown San Francisco" aren't recognised.** (2 tests)
- These are my own realistic phrasings, not from the spec.
- **Verdict:** spec gap. **How serious:** low, because the agent just asks again.

### 4. Spec gaps and ambiguities (nothing failed)

- **Plain-value time changes.** `change_choice("time", "morning")` or `"Thursday morning"` is stored as a *day*. The next search then returns "bad input". The spec only defines a plain weekday.
- **Changing only the time of day wipes the day.** `change_choice("time", time_of_day="afternoon")` with no day clears an existing "Thursday" wish.
- **"Near" plus an ambiguous place.** "Near the Mission" or "near Market Street" limits options to both matching clinics. That clashes with "near doesn't restrict".
- **A new caller can get stuck.** A genuinely new caller whose name is close to a record (Mei Wang vs Mei Wong) gets `dob_mismatch` every time. The spec says the agent "never quietly treats the caller as new", so this could loop forever. It needs a rule such as "after 2 mismatches, hand off".
- **The layer above must check `status`.** If it passes the empty caller from a `need_date_of_birth` result straight into the rules, the module crashes. That is exactly how the 30 old failures broke.
- **Doctor names the matching doesn't handle:**
  - nicknames: "Dr. Dan Chen" and "Dr. Sam Kim" give every doctor with that surname, with `first_name_matched` False;
  - "Dr. Li" finds no one (Dr. Wei Lee);
  - surname first ("Dr. Chen Wei") finds no one.
- **Single partial words pick one clinic.** "Valley", "Gate", "Union" and "Square" each choose a single location.
- **"Nearest other times" isn't literally true.** The note for an impossible day says this, but the options are simply the soonest overall.
- **Odd day values.** "20261013" is accepted as a date. A day of `None` gives a "bad input" note mentioning "None".

### 5. What I covered, and what I couldn't

**Covered:**
- **Wish order and true notes:** comparison against my own model over 12 seeds × 120 random combinations (and 4,800 in a separate run).
  - Every `latest` value, said vs carried-over wishes, all 4 wishes together on every visit type.
  - The time-change table end to end for every visit type, day and the first 4 doctor/location pairs.
  - Doctor and location changes end to end.
  - All 1,101 "this doctor can't do it" notes checked reason by reason.
- **Identity:** all 6 statuses; date formats; whether any name, id, date of birth or referral leaks; titles; misspellings that should and shouldn't match; reversed names; same name with the same or a different date of birth; broken patient records.
- **Places:** every spec phrasing, about 100 San Francisco phrasings, wrong-match and unknown checks, distance order, and `soonest`.
- **Doctor names:** quality labels, first name vs surname, possessives, fallbacks; every full name, surname and first name in the catalog.
- **Day and time values:** accepted and rejected forms, "any", case, the 14-day window.
- **Other:** note kinds and `to_dict` shapes; option numbering; `remember_offer` and `offered`; `SlotTaken` (overlaps, lunch, weekends, unopened blocks); `clinic_now`; catalog checks with deliberately broken copies of the data; `alternatives_for`; specialty words; `answer_question`.

**Couldn't test:**
- the layer above this module (tools, stage moves, Pipecat);
- how the AI turns speech into these fields;
- exact free times, because they come from a scrambling formula. As in round 1, I used the module's calendar only as the source of open times.

**Files** (nothing in `clinic/` or `data/` was changed):
- My new tests: `backend/tests_independent/round2_reference.py` (my own model of the wish order) and the five `test_round2_*.py` files.
- The edited old tests: `test_card.py`, `test_options.py`, `test_rules.py` and `test_patients.py` in the same folder.
