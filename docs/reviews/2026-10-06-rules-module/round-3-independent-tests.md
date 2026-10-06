# Round 3 independent test report: catalog and rules module

| | |
| --- | --- |
| **Date** | Tue 6 Oct 2026, late evening |
| **Version tested** | Commit `e94e6d6` ("Fix the round-2 findings in the rules module") |
| **Who** | A fresh AI agent (not the round-1 or round-2 testers) that never saw the build or fix conversations. It got the plan, the round-1 spec, both spec-change notes ([round 2](round-2-spec-changes.md), [round 3](round-3-spec-changes.md)), the round-2 test report, the raw data, the code (to learn how to call it) and the independent suite to take over. It did not see the builder's tests or the triage. |
| **Its tests** | [`backend/tests_independent/`](../../../backend/tests_independent/): older files updated where the spec changed (listed below), `round2_reference.py` updated, and four new `test_round3_*.py` files. |
| **Result** | 1,032 tests: 1,014 passed, 18 failed (8 separate problems). It confirmed that all 155 earlier failures came only from the three agreed changes. |
| **What happened next** | See [`triage.md`](triage.md), round 3 section. |

The agent's report follows. The builder session saved it (agents can't write files here). The only edits: scratch folder paths were shortened, and its closing note about scratch locations was removed.

---

I updated the old tests to the round-3 spec and added 400 new ones. 18 of the new tests fail on real problems in the code. None is a crash or a broken booking rule. The worst is a false sentence the agent would say out loud, after a caller turns a doctor down and then asks for them again.

## 1. Summary

- **Before my changes:** 632 tests. 477 passed and 155 failed.
- **After my changes:** 1,032 tests (the 632 old ones plus 400 new). 1,014 pass and 18 fail.
  - All 632 old tests pass.
  - The 18 failures are all new tests. They come from 8 separate problems.

**Verdict.** The core is solid:
- Across the whole catalog, no option breaks a booking rule, the time-slot rules hold, and the window is right.
- "Newest wish wins" now works, including the location change round 2 found broken and a carried-over choice marked as the latest change. I checked about 1,000 random wish combinations and about 6,000 change sequences against my own model, and found no disagreement.
- The step-by-step identity check works as specified. In my privacy tests, a made-up name and a real name with the wrong birthday get the same reply at every step.

What remains is at the edges:
- one false note after "someone else, please";
- "someone else" not working once the doctor is only carried over (after a change);
- wrong guesses for some doctor words;
- a few realistic place phrases that aren't understood;
- two small identity issues.

## 2. Tests I edited

| Test(s) | Old expectation | New expectation | Reason |
|---|---|---|---|
| `test_options.py`: 15 tests (day/language whole-catalog, the Garcia, Zhivago and Sunset cases, ambiguous/unknown place, Klingon, the "who can" list, and two "recognise" checks that were waiting to break) | the note itself searched as text | the note's `.say` searched | s2: *"It is NOT a string: use `note.say` for the text."* |
| `test_options.py`: `test_language_note_is_true_when_doctor_wish_also_set`, `test_named_place_note_is_true_when_doctor_wish_also_set` | searched for old wording, so they passed for the wrong reason | rewritten to check behaviour: options are all Dr. Daniel Chen, no "impossible" note, and exactly *"No Spanish-speaking doctor is available with Dr. Daniel Chen."* / *"Midtown Medical Group isn't available with Dr. Daniel Chen."* | Round 2's warning; spec s4 clash wordings |
| `test_card.py::test_demo_skin_check_then_knee_mri`; `test_round2_places.py::test_the_mission_gives_ambiguous_note`; 4 tests in `test_round2_wishes.py` | note searched as text | `.say` | s2 |
| `test_patients.py`: 7 tests | `lookup(name)` with no birthday gives `need_date_of_birth` / `not_found` | birthday is a required argument; missing birthday, one-word names and title-plus-surname give `incomplete` for every birthday; a two-word unknown name gives `not_found` | s1: *"date of birth is now a required argument"*; *"incomplete: the name has fewer than two words… or the date of birth is missing"* |
| `test_round2_identity.py`: 12 tests | `need_date_of_birth`, `dob_mismatch`, `invalid_date_of_birth`, `several` | `incomplete`, `not_found`, `same_name_and_birthday`; a wrong birthday must give the same `to_dict()` as a made-up name | s1: *"There are no other statuses"*; *"Same answer whether the name or the date was wrong."* |
| `test_round2_names_and_times.py::test_date_outside_window_is_impossible` (renamed `…_is_bad_input`) | `wish_impossible` with options | `bad_input` and no options | s3 |
| `test_round2_names_and_times.py::test_notes_are_strings_with_kinds_everywhere` | each note is a string | each note is a `Note`, not a string; `to_dict()` gives kind and say; `str(note)` gives the sentence (the old name was kept) | s2 |
| same file: the list of note kinds, plus 3 tests | — | `no_other_doctor` added; `.say` used | s2 |
| `test_round2_wishes.py`: 2 language-note tests | searched for "None of the doctors who offer…" | the new wording, and true only if no doctor this caller can book (with open times) speaks it; the exact sentence is checked | s4: *"None of the doctors available to you for X speaks Y."* |
| `round2_reference.py` (my model of the spec) | latest promoted only a said wish | latest promotes even a carried-over wish; out-of-window dates expect `bad_input`; turned-down doctors are left out; "any/anyone/no preference" means no doctor wish | s3, s4 |

I also fixed 3 mistakes in my own new tests:
- two Dr. Maria Garcias meant "isn't available at X" wasn't true for that name;
- one test mixed a bad time with an unknown place, so the place note never appeared;
- one example needed a better-chosen day.

**The builder's claim is confirmed.** All 155 failures came from the three agreed changes:
- notes as records (most of them);
- the identity rework (about 75);
- the window (1).

Nothing else needed changing to make them pass. The two language-note tests also needed the new wording from s4, which goes with the notes change. None of the 155 was hiding a code bug.

## 3. Failures that remain, most serious first

**F1. A false note about a turned-down doctor** (`test_turned_down_doctor_asked_for_again_gets_a_true_note`)
- **Spec:** "Notes say only true things."
- **Reproduction:**
  - New caller, Skin Cancer Screening, Dr. Daniel Chen chosen.
  - `change_choice("doctor", "")`, then `change_choice("doctor", "Dr. Daniel Chen")`.
  - Note: *"Dr. Daniel Chen has no open times for Skin Cancer Screening in the next 14 days."*
  - He does have open times. He was turned down.
- **Verdict:** code bug. Keeping him excluded follows the spec ("for the rest of the call"); the sentence is what's wrong.
- **How serious:** medium. The agent tells the caller something untrue. The caller also can't change their mind and get him back.

**F2. "Someone else" after a change offers the same doctor again** (`test_someone_else_after_a_time_change_does_not_offer_the_same_doctor`)
- **Reproduction:**
  - Dr. Daniel Chen chosen, then `change_choice("time", "Thursday")`. The doctor is now a carried-over wish.
  - The caller hears his Thursday times and says "someone else": `change_choice("doctor", "")`.
  - Nobody is turned down. All 3 options are Dr. Daniel Chen.
- **Verdict:** spec gap that leans towards a bug. The spec only covers a doctor who is *chosen*.
- **How serious:** medium. It's a very natural flow, and the caller hears the doctor they just declined.

**F3. Doctor words guessed as the wrong specialty** (4 tests)

| What the caller says | What the module picks |
|---|---|
| podiatrist (foot doctor) | Pediatrics |
| hematologist (blood doctor) | Dermatology |
| nephrologist (kidney doctor) | Neurology |
| audiologist (hearing) | Radiology |

- **Spec:** the doctor words are built from each specialty's name, and "physician" matches nothing. That shows near-misses mustn't map to a different specialty.
- **Verdict:** code bug. These words are within one or two letters of words the module builds.
- **How serious:** medium-low. The agent would offer the wrong department's visit types.

**F4. A full clinic address isn't recognised** (6 tests)
- "4874 Main St", "481 Mission St", "near 481 Mission St" and "4455 Geary Blvd" all give `place_unknown`. "Main St" alone works.
- **Cause, in plain terms:** the house number counts as a word that has to match a street name.
- **Verdict:** code bug. The spec says streets are matched when a street word is said; I added the house-number case myself.
- **How serious:** low-medium. A caller reading the address off a letter is asked again. The number would even settle shared streets like Geary.

**F5. The little word "in" breaks a place phrase** (3 tests)
- These are unknown: "the Midtown one in SF", "downtown in San Francisco", "the clinic in the Marina".
- These work: "the one in the Marina", "downtown SF".
- **Spec:** "City words ('SF', 'San Francisco') are ignored."
- **Verdict:** code bug. **How serious:** low; the agent asks again.

**F6. A spelled surname of only spaces counts as a try** (`test_blank_spelling_counts_as_no_spelling`)
- After 2 misses, `attempt(..., spelled_last_name="   ")` goes straight to `offer_new_or_staff`.
- **Spec:** "an attempt without spelled_last_name returns spell_last_name again without counting."
- **Verdict:** code bug. **How serious:** low. A returning caller is offered "new patient or staff" one step early.

**F7. The Vietnamese surname "Do" is treated as a title** (`test_vietnamese_surname_do_is_a_name_not_a_title`)
- A patient named "Anh Do" always gets `incomplete`. "Do" (as in the D.O. degree) is in the list of title words, and so are "Pa", "NP" and "MD".
- **Spec:** only "titles like 'Mr.' and endings like 'Jr'" don't count.
- **Verdict:** code bug. It isn't in the fake data, but "Do" is a very common surname in San Francisco.
- **How serious:** medium for a real clinic. Because `need_both` never counts as a try, this caller loops on "Could I have your full name…?" and never reaches staff.

**F8. "I don't mind" isn't a no-preference place** (1 test, my own phrasing)
- It gives `place_unknown`, while "don't mind" gives no place wish.
- **Verdict:** spec gap. **How serious:** low.

## 4. Spec gaps and ambiguities (nothing failed)

- **Some callers can loop forever on `need_both`.** It never counts as a try. A one-word name ("Cher"), the "Do" case, or an AI that can't format the birthday leads to `need_both` every time, with no route to staff. That clashes with the goal "nobody gets stuck".
- **Correct details after 2 misses aren't accepted unless spelled.** The caller gets `spell_last_name`. That's literally what the spec says, but it's harsh.
- **The `found` step's sentence is empty.** The spec calls `say` "the sentence for the agent".
- **"Someone else" said as words.** `change_choice("doctor", "someone else")` gives the note *"I couldn't find a doctor called someone else here."* Only `""` is defined.
- **Time phrases that give `bad_input`:**
  - "this afternoon";
  - "Thursday, morning" (the comma);
  - "Thursday or Friday";
  - "don't mind" with an apostrophe. The code's own list has "dont mind" without one, so it looks intended.
- **"SF" on its own** gets a "don't recognise" note, although city words are "ignored".
- **Language names of two words** ("Mandarin Chinese") become "Mandarin chinese" and match nobody.
- **"Hayes" or "Civic" alone** picks Midtown, by the first-distinctive-word rule. That's fine, but worth knowing.

## 5. What I covered, and what I couldn't

**Covered:**
- **Identity:**
  - every status and every step in order;
  - tries that count and don't count;
  - one letter out on a spelled surname passes, two don't (changed, added and removed letters, swapped letters, B/D);
  - titles and "Jr";
  - the same name with the same or different birthdays;
  - privacy: whole scripted calls compared reply by reply, real versus made-up names;
  - `to_dict()`, copying and pickling (saving and loading a copy).
- **Newest wish wins:**
  - through `change_choice` with doctors the caller only named and with carried-over ones;
  - whole-catalog comparison against my model, plus exact checks of the spec's clash wordings.
- **"Someone else":** across the whole catalog, including the `no_other_doctor` case.
- **Time changes:** 11 phrasings, plus a whole-catalog follow-through.
- **Places:** about 130 phrases, including every spec phrase, "near" plus an ambiguous name not narrowing the options, and about 40 that must not pick a place.
- **Other:**
  - note records: copying, pickling, equality, `to_dict()`, and grammar across the catalog;
  - the window edges and date formats;
  - catalog checks with 18 kinds of broken data;
  - the schedule rotation, including a fake doctor at 10 sites;
  - `check_booking` with 30 odd inputs;
  - regressions from rounds 1 and 2.

**Couldn't test:**
- the tool and stage layer and Pipecat;
- how the AI turns speech into these fields;
- exact free times, which come from a scrambling formula. As before, I used the module's calendar only as the source of open times.

Nothing in `clinic/` or `data/` was changed. New test files: `test_round3_identity.py`, `test_round3_wishes.py`, `test_round3_places.py`, `test_round3_other.py`. Edited: `round2_reference.py`, `test_options.py`, `test_card.py`, `test_patients.py`, `test_round2_identity.py`, `test_round2_names_and_times.py`, `test_round2_places.py`, `test_round2_wishes.py`.
