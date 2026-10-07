# Round 7 independent check: catalog and rules module

| | |
| --- | --- |
| **Date** | Wed 7 Oct 2026, night |
| **Version checked** | Commit `37c5b8a` ("Fix the round-6 findings: near is a plain yes/no") |
| **Who** | One fresh AI agent (not from earlier rounds) acting as both tester and reviewer. It never saw the build or fix conversations. It got the process, the round-6 report and triage (to verify, not trust), all seven [spec-change notes](round-7-spec-changes.md), the code, both test folders and the change since `18af256`. It was told not to read the builder's build log. |
| **Its tests** | [`backend/tests_independent/`](../../../backend/tests_independent/): 18 older files updated for the round-7 spec, plus new `test_round7_places.py`, `test_round7_values.py` and `test_round7_notes.py` (868 tests). |
| **Evidence** | Probe scripts and test-run logs in [`round-7-probes/`](round-7-probes/). They were run from the agent's scratch copy (`common.py` and `mutate.py` point at `../work/backend`). |
| **Result** | 3,104 tests in all (256 builder, 2,848 independent): 3,082 pass, 22 fail. |
| **What happened next** | See [`triage.md`](triage.md), round 7 section. |

The agent's report follows. The builder session saved it (agents can't write files here). The only edit: in its closing file list, the scratch folder paths were shortened to where the files now live in the repo.

---

## 1. Verdict

**Not ready to tag 0.1.0 yet. One small thing must be fixed first.** Everything else is minor or only shows up in a much bigger catalog. It can go in a later version.

What I checked from round 7 works:
- **Places:** a place is now a name plus a yes/no "near" setting. Turning near on ranks by distance without limiting the search to that place. Turning it off limits the search to that place.
- **Language values:** two-word mixes like "Spanish French" are refused instead of guessed.
- **Change names:** `change_choice` (the tool for changing part of a booking) accepts only its five names.
- **Sentence guard:** `answer_question` (the fact-lookup tool) now refuses a sentence passed as a name, the same way the search does.
- **Doctor lists:** every list reads at most three names, then "and N more", and the counts add up.
- **Weekdays and repeated ids:** weekday words follow the exact table, and a repeated id is reported once.

**Must fix:**
1. **Some place phrases are still read, which breaks both the round-7 spec and the claim.** The spec says "…location", "…clinic" and "…office" are not place names and should get "I don't recognise the place". But "Midtown office", "Downtown location", "Richmond clinic", "Sunset hospital" and "Richmond branch" are still accepted as our clinics.
   - **Cause:** the list of filler words in place names (`GENERIC_PLACE_WORDS` in `catalog.py`) still contains 8 words that appear in none of our place names: office, location, hospital, site, branch, centre, of, and. They are left over from the old phrase reader.
   - **Fix:** about one line. Keep only words that appear in our own names. "Clinic" also needs a decision from Farhaan, because it is part of two real names (Mission District Family Clinic, Sunset Community Clinic).
   - **18 of my tests fail on this.** Behaviour is harmless, but this is exactly the claim this round was meant to make true, and an interviewer would see the word list straight away.

## 2. Part A: independent tester

### Numbers

| | Builder tests | Independent tests |
|---|---|---|
| **Before** (as handed over) | 256 pass | 1,770 pass, **192 fail** (1,962 tests) |
| **After** (my updates and 3 new files) | 256 pass | 2,826 pass, **22 fail** (2,848 tests) |

The whole run takes about 2 minutes 53 seconds. The code checker (pyflakes) finds nothing in either test folder or in `clinic/`.

**The builder's claim mostly checks out.** All 192 failures went away when I changed only the tests, to send what the AI now sends. No code fix was needed, so they really did come from agreed changes. But the triage said 204 failures and I got 192. The triage's numbers look stale: `catalog.py` was edited about 7 minutes after the other files.

### Edited tests

| File | What changed | Why |
|---|---|---|
| `test_places.py`, `test_round2_places.py`, `test_round3_places.py` | Each phrase became a name plus near. "near Downtown" became ("Downtown", near=True); "the Midtown one" became "Midtown"; "the one on Geary" became "Geary Street". The near-phrase tests now also check that the phrase itself is "not recognised". | Section 1 |
| `test_options.py`, `test_card.py`, `test_round2_wishes.py`, `test_round2_other.py`, `test_round3_other.py`, `test_round3_wishes.py`, `test_round5_turn_down.py` | The same change to names plus near. **Seven of these tests were passing without testing anything:** an unrecognised phrase quietly meant "no place wish". They now test the place again. | Section 1 |
| `test_round4_words.py` | "near Geary" became ("Geary Street", near=True). Added: bare "Geary" with near is not recognised. Linking and city words became names. | Section 1 reverses round-4 change 3 |
| `test_round5_values.py` | House numbers now come with a street word and near. | Section 1 |
| `test_round6_values.py` | "Every real place is not a sentence" now tries each name with near on and off. | Section 1 |
| `test_round6_notes.py` | The sentence-quality battery uses names plus near. The "only doctors matching" list may now read "and N more". | Sections 1 and 5 |
| `test_round5_notes.py` | The "whom you turned down" checker accepts "A, B, C and N more" and checks that the count adds up. | Section 5 |
| `round6_reference.py` (my shared checker) | Places inside a label are split on " / ". New shared checker for capped name lists. | Section 5 |
| `round2_reference.py` (my model of the spec) | Place names replace place phrases, and near never restricts. The weekday table is now exactly the spec's. | Sections 1 and 6 |
| `test_facts_and_robustness.py` | "provider" is no longer accepted as a question type. Added a test that it's refused with the how-to message. | Section 4 |

### New files (868 tests)

- **`test_round7_places.py`** (410 tests):
  - every location name, neighbourhood and nickname, with near on (ranks, doesn't restrict) and off (restricts), checked against distances from `location_extras.json`;
  - every landmark is always "near";
  - forgiving spelling and short words that must match exactly;
  - shared names with near on and off;
  - every street × 7 street words × near on and off;
  - bare street names are not streets;
  - house numbers we have and don't have;
  - 25 phrase forms × 6 names are not recognised, with the exact note wording;
  - near with any other kind of change is refused, changing nothing;
  - near goes back to off when the chosen place is carried over (5 kinds of change), and stays on for a place that was only said;
  - the summary shows "near".
- **`test_round7_values.py`** (424 tests):
  - the language accept/refuse table (25 refused forms, unknown names keep their capitals, "Mandarin Chinese" means Mandarin);
  - "no preference" words stored as empty, for doctor, place and language;
  - the five change names and 16 refused synonyms;
  - the three question types for `answer_question` and 12 refused ones;
  - the sentence guard: 14 words × 4 forms × 4 names, plus every real doctor and place passes;
  - the weekday table (70 accepted forms, 23 refused);
  - repeated ids in the catalog and patient data, including ids that differ only by spaces.
- **`test_round7_notes.py`** (34 tests):
  - the same-name note across the whole catalog: count, three-name limit, title, specialty and exact places;
  - "Doctors with that surname" for every surname;
  - the "can't do this" reasons across the whole catalog: each reason true, each group capped, every doctor counted once;
  - a test catalog with two Dr. Daniel Chens in Dermatology;
  - a test catalog with 20 Dr. Okafors, to check every list stays capped.

**The new tests can fail.** I made 13 small changes to a copy of the code (`probes/mutate.py`). Each change made extra tests fail, compared with the 22 that fail on the real code. Examples: near ignored, near not reset, four names read, "frid" accepted, the guard removed.

### Remaining failures, most serious first

1. **18 × `test_each_listed_phrase_form_is_not_recognised[{x} location / {x} clinic / {x} office]`.** **Code bug** (section 1). For "clinic" it is partly a gap in the spec (see must-fix 1).
   - Repro: `catalog.resolve_place("Midtown office")` gives Midtown Medical Group.
   - Expected: kind `none` (not recognised).
2. **2 × same-name, same-specialty labels.** **Code bug** (section 5). It only shows in a bigger catalog than the real one.
   - Repro: two Dr. Daniel Chens in Dermatology, neither taking new patients, and the caller asks for "Dr. Daniel Chen".
   - The note reads: "…can do this: **Dr. Daniel Chen and Dr. Daniel Chen** aren't taking new patients."
   - The "Doctors with that surname" note also lists "Dr. Daniel Chen (Dermatology)" twice.
3. **2 × `answer_question(catalog, "visit type", …)`.** **Code bug, minor** (section 4). It is refused, although the spec says "case and spaces ignored" for both tools, and `change_choice` accepts "Visit Type".

## 3. Part B: independent reviewer

### Triage check

| # | Result | Evidence |
|---|---|---|
| R6-1 (phrases still read) | **Partly fixed** | The near flag works, and 22 of the 25 listed phrase forms are not recognised. "…location", "…clinic" and "…office" still are (must-fix 1). |
| R6-2 (two-word languages guessed) | **Fixed** | All 25 refused forms are refused, and nothing is guessed |
| R6-3 (same-name labels, first only) | **Fixed where it was found** | "Doctors who can" and "no other doctor" pass with the twin doctors. Two other lists still lack places (failure 2). |
| R6-4 (doctor lists uncapped) | **Fixed** | Every doctor list stays at three or fewer, on the whole catalog and on the 20-Okafor catalog. Small leftover: the "Doctors with that surname" note has its own copy of the "three, then N more" code instead of using the shared helper `_a_few`, so the triage's "one helper used by every list" isn't quite true. |
| R6-5 (`answer_question` had no guard) | **Fixed** | 14 words × 4 forms × doctor and place |
| R6-6 (no-preference words stored as wishes) | **Fixed** | 13 words × 3 fields; never shown in the summary |
| R6-7 ("not far from") | **Partly fixed** | Spec gap remains. Section 1 lists "not far from…" as "not recognised", but the sentence guard (still in force) refuses it as `bad_input` (a "please resend" note). The behaviour is fine; the spec contradicts itself. |
| R6-8 (stale comments) | **Fixed** | Small new ones: see NIT 7 |
| R6-9 (repeated ids) | **Fixed** | 2, 3 and 5 copies, ids differing only by spaces, catalog and patients |
| R6-10 (weekday words) | **Fixed** | An exact table. A trailing "." is still stripped, which is harmless. |
| R6-11 (13 change names) | **Partly fixed** | `change_choice`: exactly five. `answer_question`: refuses "visit type" (failure 3). |
| R6-12 (builder test branch) | **Fixed** | It now uses a named constant |
| R6-13 ("and" inside lists) | **Fixed** | Places are joined with " / " |
| R6-14 (same-name doctors collapse) | **Left, as agreed** | Still "are Dr. Carlos Garcia and Dr. Maria Garcia" for three Garcias (`p4_review.py`) |
| R6-extra ("any day") | **Fixed** | "any day", "any", "whenever" as a day clear only the day |
| "204 failures are all agreed changes" | **True in substance, number stale** | 192, not 204, and all were fixed by test-only updates |

### The claim check

The claim: *"names (doctors, places, languages) are matched forgivingly against our own records; everything else is a plain instruction, and the code reads no phrases."*

I read every function that takes text from the AI:
- `change_choice`, `turn_down_doctors` and `choose_option` (card);
- the day, time and language checks and the sentence guard (options);
- `resolve_place`, `match_providers` and `match_specialty` (catalog);
- `answer_question` (facts);
- `lookup` (patients);
- `means_no_preference` and `person_match` (fuzzy).

**Clean:**
- Doctor names: titles, "'s" and spelling are handled forgivingly.
- Specialty and visit-type names, and patient names.
- Days and times: an exact table.
- Ids, the five change names, and near (a yes/no setting).

**Still reading phrases or words beyond name matching:**
1. **Leftover place filler words** (`catalog.py:48-51`): office, location, hospital, site, branch, centre, of, and. None of them is in our names, so "Downtown location" is a phrase being read. VERIFIED (must-fix 1). ("the" is also in none of our names, but the spec's own examples use "the Castro" and "the Mission", so I count it as allowed.)
2. **The "no preference" list** (`fuzzy.py:49-55`) holds whole phrases: "anytimeworks", "eitherisfine", "itdoesntmatter", "notfussed", "anywhereisok"…
   - The spec allows this list, so it isn't a bug.
   - But it is phrase reading, so the claim should say so: "…apart from one fixed list of 'no preference' words (treated as empty) and a list of sentence words (refused)."
   - JUDGEMENT.
3. **The sentence guard** (`NOT_NAME_WORDS`, plus `NOT_A_LANGUAGE` for languages) reads words, but only to refuse. Fair, and allowed by the spec. It belongs in the same clause of the claim.
4. **Languages** are matched only by capital letters, not forgivingly. A misspelling like "Spansh" becomes an unknown language. The claim says names are matched forgivingly. The note is still true, because it lists our languages. JUDGEMENT.

### New findings

**MUST FIX**
1. Leftover place filler words. VERIFIED (above).

**SHOULD FIX**
2. **Same-name, same-specialty doctors aren't told apart** in the "can't do this" reasons or in "Doctors with that surname". This only happens in a bigger catalog. Route both lists through one shared labelling helper, as `_who_can` (the function that builds "Doctors who can") already does. That also removes the duplicated "three, then N more" code. VERIFIED.
3. **`answer_question` refuses "Visit Type".** Normalise it the same way `change_choice` does. VERIFIED.
4. **Reword the claim** to name the "no preference" list and the sentence-word list (claim check, points 2 and 3). JUDGEMENT.
5. **The "could mean A or B" note for a shared place name has no length limit.**
   - On a test network with 40 extra neighbourhoods called "Mission …", one note named 42 clinics in 1,097 characters (`p4_review.py`).
   - The spec caps only doctor lists, so this is JUDGEMENT. Same fix as the doctor lists: read three, then "and N more".
6. **Spec gap:** "not far from…" (R6-7 row). Change one line of the spec, not the code.

**NIT**
7. **Stale wording:**
   - the `PlaceMatch` docstring says "What a caller's place words resolved to" (`catalog.py:131`);
   - the `place_unknown` / `place_ambiguous` comments say "place words" (`options.py:64-65`).
   VERIFIED.
8. **`near` accepts any truthy value.** `near="false"` (the word, as text) is taken as on. The tool layer should pass a real true/false, but a type check costs one line. VERIFIED.
9. **An unknown language plus any word is kept as one language.** "French only" gives "…listed as speaking French Only." It's true but odd, and inconsistent with "Spanish only" being refused. JUDGEMENT.
10. **For a landmark, or a house number we don't have, the search treats the place as near, but the card keeps near off.** So the summary reads "place: Union Square" without "near". JUDGEMENT.
11. **Copy-paste:**
    - the same tidy-the-spaces line, `" ".join(str(x or "").split())`, appears 11 times in `card.py` and `options.py`;
    - two date checkers do the same job: `_is_date` in `options.py` and `_is_iso_date` in `patients.py`;
    - the earth radius is a bare number (3958.8) in `distance_miles`.
    VERIFIED.
12. **The builder's own "phrases not read" test** tries 8 phrases, but none of "…location", "…clinic" or "…office", which is why must-fix 1 slipped through.

### Speed

VERIFIED with `probes/p3_scale.py`: a made-up catalog of 500 locations and 2,000 doctors. The busiest visit type, New Patient Consultation, is offered by 716 doctors.

| Search | Time |
|---|---|
| Load the catalog | 0.03 s |
| Skin check | 24–36 ms |
| New Patient Consultation, no wishes | 411–524 ms |
| …with Thursday morning and Spanish | 367–436 ms |
| …with "Dr. Chen" / "Dr. Chenn" | 302–354 ms |
| …with a neighbourhood, near on / off | 447–540 / 298–420 ms |
| …with a shared street, near on | 470–642 ms |
| …with everyone turned down | 451–563 ms |
| …with "Klingon" / a Saturday date | 448–665 ms |
| `answer_question` | 4–16 ms |
| Real catalog, Annual Physical | about 7 ms |

That's about the same as round 6. The longest doctor-list notes at scale are 178–378 characters, and none reads more than three names.

## 4. What's solid

- **Near is a true yes/no:**
  - all 21 names of our 8 locations restrict with near off and rank (without restricting) with near on;
  - all landmarks are always near;
  - every street, house number and shared-name case behaves as the spec says;
  - near resets correctly, and refusals change nothing.
- **22 of 25 phrase forms** are no longer read, and each gets the exact "Pass just a place name" note.
- **Languages:** nothing is guessed; every refused form gets the how-to note, and unknown names get the true sentence with their capitals kept.
- **Notes:** every doctor list in the real catalog, and in the two test catalogs, reads at most three names with a correct count. The same-name note gives each doctor's true title, specialty and places.
- **Data checks:** repeated ids are reported once, even when they differ only by spaces.
- **Clean code:** the code checker finds nothing, and none of the old phrase-reading regexes or near-word lists is left.

## 5. Files

**New test files** (in `backend/tests_independent/`): `test_round7_places.py`, `test_round7_values.py`, `test_round7_notes.py`.

**Changed test files** (same folder): `round2_reference.py`, `round6_reference.py`, `test_card.py`, `test_facts_and_robustness.py`, `test_options.py`, `test_places.py`, `test_round2_other.py`, `test_round2_places.py`, `test_round2_wishes.py`, `test_round3_other.py`, `test_round3_places.py`, `test_round3_wishes.py`, `test_round4_words.py`, `test_round5_notes.py`, `test_round5_turn_down.py`, `test_round5_values.py`, `test_round6_notes.py`, `test_round6_values.py`.

**Probes and evidence** (in [`round-7-probes/`](round-7-probes/), each run from the agent's scratch copy with `python3 <name>`):

| File | What it shows |
|---|---|
| `common.py` | Shared setup for the probes |
| `p1_place_phrases.py` | Which place phrases are still read |
| `p2_misc.py` | Question and change names, near passed as text, the language table |
| `p3_scale.py` | Timings and note lengths at scale |
| `p4_review.py` | R6-14, the leftover words, "not far from", twin labels, the uncapped place note at scale, the "no preference" phrases, "French only" |
| `mutate.py` | Checks that the new tests catch small code changes |
| `builder-before.txt`, `independent-before.txt`, `failing-before.txt` | The test runs as handed over (the 192 failures) |
| `all-after.txt`, `failing-after.txt` | The final run (the 22 failures) |
| `independent-tests-changes.diff` | Every change I made to the independent tests |

Nothing in `clinic/` or `tests/` was touched.
