# Round 6 independent check: catalog and rules module

| | |
| --- | --- |
| **Date** | Wed 7 Oct 2026, evening |
| **Version checked** | Commit `18af256` ("Fix the round-5 findings: plain time fields, no sentence matching") |
| **Who** | One fresh AI agent (not from earlier rounds) acting as both tester and reviewer. It never saw the build or fix conversations. It got the process, the round-5 report and triage (to verify, not trust), all six [spec-change notes](round-6-spec-changes.md), the code, both test folders and the change since `395cb9f`. It was told not to read the builder's build log. |
| **Its tests** | [`backend/tests_independent/`](../../../backend/tests_independent/): 9 older files updated for the round-6 spec, plus new `test_round6_values.py`, `test_round6_notes.py` and `round6_reference.py` (435 tests). |
| **Evidence** | Probe scripts in [`round-6-probes/`](round-6-probes/). They were run from the agent's scratch copy (`common.py` and `mutate.sh` point at `../work/backend`). |
| **Result** | 2,186 tests in all (224 builder, 1,962 independent): 2,182 pass, 4 fail. |
| **What happened next** | See [`triage.md`](triage.md), round 6 section. |

The agent's report follows. The builder session saved it (agents can't write files here). The only edit: in its closing file list, the scratch folder paths were shortened to where the files now live in the repo.

---

## 1. Verdict

**Not ready to tag 0.1.0 yet. Two small things must be fixed first.**

Most of round 5 holds up:
- Days and times are now plain fields, and anything else is refused.
- A sentence passed as a doctor or a place is refused.
- `choose_option` (the new "the caller picked option N" method) works.
- The crash is gone, and the "no other doctor" note is short and true.
- After I rewrote the older tests to the new forms, all of them pass.

**Must fix:**
1. **The claim "no part of the code reads the caller's sentences" is false.** Places are still read as phrases ("near…", "close to…", "the X one", "on Geary", "…area", "…please"). Two-word language values are read too. An interviewer who reads the claim and then opens `catalog.py` will find this in a minute. The cheapest fix is to reword the claim honestly. The thorough fix is to make places plain fields as well. That second option is Farhaan's decision.
2. **Two-word language values are silently guessed.** "Spanish French" gives only Spanish speakers, with no note. So do "Spanish only" and "Cantonese Mandarin" (Mandarin). The round-6 spec says two language names are refused. This is the "guess silently" pattern the project promises not to do. The code fix is about three lines.

## 2. Part A: independent tester

### Numbers

| | Builder tests | Independent tests |
|---|---|---|
| **Before** (as handed over) | 224 pass | 1,417 pass, **109 fail** |
| **After** (my updates and 2 new files) | 224 pass | 1,958 pass, **4 fail** |

The whole run takes about 2 minutes 50 seconds.

**The builder's claim checks out, with one small difference.** It said 110 failures; I got 109. Its breakdown of 58 is exact: 33 sentence-as-name, 14 chosen doctor, 6 no-preference language, 3 "no other doctor", 2 unknown language. The other 51 tests used spoken time phrases. I rewrote all 109 to send what the AI would now send, and changed no code. All 109 then pass.

### Edited tests

| Test (file) | What changed | Why |
|---|---|---|
| `round2_reference.py` (my model of the spec) | Phrases and sentences now mean "refused". No-preference words count as empty in every field. Short day names are accepted exactly. An unused list was removed. | Round 6, sections 1–3 |
| `test_round2_other.py`: `any_time_clears_time_of_day_wish` | Now uses `days=[]` and `time_of_day=""`, or a no-preference word in each field. Added: "any time" as a day entry clears only the day. | Section 1 (plain fields); section 2 (each field on its own) |
| `test_round2_wishes.py`: `language_impossible_notes_true_whole_catalog` | Languages not in our records now expect the new "None of our doctors is listed as speaking…" sentence | Section 5 |
| `test_round3_wishes.py`: `time_change_only_what_is_mentioned` (11 cases), `time_change_then_options_honour_it` (5 cases) | Spoken phrases became plain fields. Each case keeps the phrase it stands for in a comment. | Section 1 |
| `test_round4_turned_down.py`: `filler_words` (4), `negated_name` (3) | Now expect one `bad_input` note (a "please send that again" note to the AI), no options, and nobody turned down | Section 3 |
| `test_round4_words.py`: `time_phrases_set_day_and_time` (7), `no_preference_time_phrases` (8), `only_what_is_mentioned`, `time_phrases_in_preferences_days`, `language_change_is_latest` | Plain fields. Phrases in `Preferences.days` are now expected to be refused. "any" as a language now clears the wish. **Added a check that options exist**: before, the loop over options passed even with zero options. | Sections 1 and 2 |
| `test_round5_notes.py`: `no_other_doctor_note_whole_catalog` (3) | New list format: three names with specialty, then "and N more". The count must add up. The checker is my own, written from the spec, in the new file `round6_reference.py`. | Section 5 |
| `test_round5_turn_down.py`: `change_choice_doctor_never_turns_anyone_down` (14) | Nobody may be added to the turned-down list. A chosen doctor now comes off it. | Section 4 |
| `test_round5_turn_down.py`: `words_passed_as_a_name` (26) | Now expect `bad_input` and no options, not `doctor_not_found` | Section 3 |
| `test_round5_turn_down.py`: `picking_…then_changing_the_day` | "any time" became `days=[], time_of_day=""` | It still passed, but the old value now means "day only". Changed for clarity. |
| `test_round5_values.py`: unknown language (1), language sentences (5 values moved to a new no-preference test), both times of day (6), stored wish (1), `days` argument (1), one time of day (3), no-preference (11) | New wording. The AI's mistake is tried in both plain fields. One `bad_input` note per bad value is accepted. Options are now required. Each field is cleared on its own. | Sections 1, 2 and 5 |

### New files (435 tests)

**`test_round6_values.py`** (374 tests):
- **Accepted day forms:**
  - every weekday, in lower, upper and mixed case, plus short forms ("thu", "thurs");
  - today and tomorrow;
  - all 15 dates in the window;
  - weekends, which get the true "Nothing is open…" note.
- **Refused day forms:** 33 kinds (phrases, other date formats, impossible dates), tried 3 ways each. Dates one day outside each edge of the window, and a year out, are refused with a note naming the window.
- **Time of day:** 5 accepted forms and 16 refused forms.
- **None keeps, empty clears:**
  - leaving a field out keeps it, and "" or [] clears it;
  - `new_value` (a single day given in place of the `days` list) works the same as `days=[that day]`;
  - giving both is refused, and the whole card is compared to prove nothing changed;
  - an unknown thing to change also changes nothing.
- **Late in the day:**
  - "today" at 4 pm;
  - "tomorrow" at 11:30 pm on a Friday (a Saturday);
  - the window moving with the clock.
- **"No preference":** 15 words, tried in every field. Day entries are skipped. Each field is independent of the others. A no-preference word never brings back a turned-down doctor.
- **Sentences:**
  - all 14 listed words, in 6 forms each, as a doctor and as a place;
  - the spec's examples;
  - a sentence never brings a turned-down doctor back (checked against the bare name, which does);
  - every real doctor name, place, landmark and street address is never treated as a sentence;
  - 10 made-up doctors whose names contain the words inside longer words ("Otherson", "Butler", "Notley"…) still match.
- **`choose_option`:**
  - it puts the option on the card, and accepts the number as a number;
  - 7 bad numbers, stale options and an empty offer are refused, changing nothing;
  - a turned-down doctor comes off the list when picked, and stays off after 4 kinds of change;
  - turning the chosen doctor down does put them on the list;
  - the summary never lists the chosen doctor.
- **Patient data:** 15 bad birthdays, 4 real ones (leap days included), repeated ids, the real file loads, and every problem is listed once.

**`test_round6_notes.py`** (61 tests):
- **No empty or broken sentence:** 82 visit types × 21 sets of wishes × 3 callers, checked for 7 kinds of broken text.
- **A fully booked fortnight:** 3 visit types × 21 sets of wishes. No crash, a plain "no open times" note, no empty list.
- **"Doctors who can":** checked across the whole catalog.
- **Same-name doctors:** a test catalog where two doctors share a name *and* a specialty.
- **"The only doctors matching 'Dr. X'":** every shared surname × every visit type × 3 callers.
- **Languages:**
  - 8 languages not in our records, across the whole catalog, get the exact sentence, and options are still offered;
  - our 7 languages in 3 cases never get that sentence;
  - two language names are refused, and "Mandarin Chinese" still means Mandarin.

I also checked that the new tests can actually fail. I made small changes to a copy of the code (`probes/mutate.sh`) and ran the tests against it. Each change made at least one new test fail.

### Remaining failures, most serious first

1. **`test_two_language_names_are_refused`.** **Code bug.**
   - Repro: `Preferences(language="Spanish French")` for Annual Physical.
   - Result: 3 options, all with Spanish speakers, and no note.
   - The spec (section 6) says this should be refused.
2. **The two `same_name_same_specialty` tests.** **Code bug** (section 5). It only shows on a bigger catalog; in the real one, same-name doctors all have different specialties.
   - Repro: add a second Dr. Daniel Chen (Dermatology), then turn everyone down.
   - The note reads "Dr. Daniel Chen (Dermatology, Downtown Health Center and Richmond Care Center), **Dr. Daniel Chen (Dermatology)**, …".
   - The second doctor gets no locations, so the caller can't tell them apart.
3. **`test_every_problem_is_listed_once_in_one_error`.** **Code bug, minor.** A patient id used 3 times gives "Patient id p5 appears more than once." twice. The catalog check does the same.

## 3. Part B: independent reviewer

### Triage check

| # | Result | Evidence |
|---|---|---|
| R5-1 (crash) | **Fixed** | No crash on a fully booked fortnight for 3 visit types and 21 sets of wishes |
| R5-2 ("not Dr. Chen" as a name) | **Fixed in the search** | All 14 words in 6 forms, for doctor and place, are refused. But `answer_question` (the "look up a fact" tool) still turns "another doctor" into Dr. Andre Patel. See new finding 5. |
| R5-3 (both times of day) | **Fixed** | Through plain fields; every mix is refused |
| R5-4 (picked doctor still "turned down") | **Fixed** | Picking takes them off the list, and they stay off after later changes |
| R5-5 (long "no other doctor" note) | **Partly fixed** | Three names, then "and N more": now 178 characters at scale (was 14,083). But two doctors with the same name and specialty can't be told apart (failure 2). Three other doctor lists still have no limit (new finding 4). |
| R5-6 (plural grammar) | **Fixed** | Whole catalog, every shared surname |
| R5-7 ("Chinese" gave a false note) | **Fixed** | 8 unknown languages × whole catalog. The sentence is true, and options are still offered. |
| R5-8 (decision 23) | **Partly fixed** | Days and times: fixed. But the "no part reads sentences" claim is false (must-fix 1). |
| R5-9 ("Doctors who can: .") | **Fixed** | Never empty |
| R5-10 (data-check leftovers) | **Fixed** | An empty neighbourhood loads. 15 bad birthdays are refused. Repeated ids are caught, but listed more than once (failure 3). |
| R5-11 ("ASL", "English Spanish") | **Partly fixed** | "ASL" is kept, and "English Spanish" is refused. But "Spanish French" and "Spanish only" are silently read as Spanish (must-fix 2). |
| R5-12 (no-preference for language) | **Fixed** | 15 words in every field. But the card still stores some of them (finding 6). |
| R5-13 (one id read letter by letter) | **Fixed** | `provider_ids="prov_001"` gives `['prov_001']` |
| R5-14 (names matched twice) | **Left, as agreed** | Still matched twice; harmless |
| R5-15 (builder tests only tried the friendly path) | **Fixed** | 224 builder tests. Small leftover: NIT 12. |

### New findings

**MUST FIX**

1. **The "the code reads no sentences" claim is not true.** VERIFIED.
   - `catalog.resolve_place` (the code that works out which place the caller meant) still reads place phrases:
     - near-words like "on the way to", "not far from", "closer to" and "around" (`catalog.py:54`);
     - filler at the start, like "somewhere", "the one", "a clinic" (`:57`);
     - filler at the end, like "area", "side", "please" (`:63`);
     - "on X" for a street, the word "district", and city words.
   - `change_choice` itself says the location value is "the caller's place words" (`card.py:156`).
   - The claim appears in triage R5-8 and in the round-6 spec's opening paragraph.
   - Fix: either reword the claim ("days, times, doctors and turning down are plain instructions; place words are still matched against our place names"), or give places plain fields, such as a place name plus a "near: yes/no" flag.
2. **Two-word language values are guessed.** VERIFIED (`probes/p2_language_two_words.py`, failure 1).
   - `_known_language` (`options.py:438-443`) uses whichever of the two words is a known language and drops the other.
   - Results: "Spanish French", "French Spanish", "Spanish Klingon", "Spanish only", "only Spanish", "Spanish ideally" and "Spanish preferred" all give Spanish speakers. "Cantonese Mandarin" gives Mandarin.
   - Fix:
     - accept an exact known name;
     - accept "Mandarin Chinese" through a one-line list of alternative names;
     - keep an unknown name with no known word in it ("Haitian Creole");
     - refuse everything else.

**SHOULD FIX**

3. **Same-name, same-specialty doctors: only the first gets locations.** VERIFIED (failure 2, `p1_same_name_list.py`).
   - `_who_can` (`options.py:294-296`) changes a label while still counting how often that label appears.
   - So the second one counts as unique.
   - Fix: count first, using `Counter` (Python's ready-made counting tool), then add the locations.
4. **Three more doctor lists have no length limit.** This is the same problem R5-5 fixed for one note. VERIFIED (`p4_scale.py`).
   - `_same_name_note` (the "several doctors share this name" note): with "Dr. Chen" on the big catalog it lists **57 doctors (5,605 characters)**. The most in the real catalog is 4.
   - The "only doctors matching … whom you turned down" note lists all names: 15 at scale.
   - The "No doctor matching … can do this" reasons list every matching doctor.
   - Reuse `NAMES_TO_READ` (the "read three, then 'and N more'" setting).
5. **`answer_question` skips the sentence guard.** VERIFIED (`p3_misc.py` C).
   - "not Dr. Chen" lists all 7 Chens, with the self-contradicting message "No doctor is called exactly 'not Dr. Chen'; these are the closest (exact)".
   - "another doctor" returns Dr. Andre Patel ("sounds alike").
   - For places, "not far from Union Square" and "the Midtown one please" are answered here but refused by the search.
   - The same AI makes the same mistakes in both tools.
6. **Some "no preference" words are stored as wishes.** VERIFIED (`p3_misc.py` A).
   - After "I don't mind", "anywhere" and "whatever", the summary reads "Caller asked for: doctor: I don't mind; place: anywhere; language: whatever".
   - Day and time words, by contrast, are emptied.
   - The spec says these words mean the same as "", and the summary is pasted into the AI's instructions.
   - Fix: store "" in `change_choice`.
7. **"not far from" now contradicts decision 24.** VERIFIED. **Spec gap.**
   - Decision 24 lists "not far from X" as a near-phrase.
   - Round 6 refuses any place value containing "not". So the search now refuses "not far from Union Square", and the note tells the AI to use "near".
   - The behaviour is acceptable, but the spec should say decision 24 changed.
   - The leftover handling for it (`NEAR_WORDS` "not far from"; "please" in `GENERIC_PLACE_WORDS` and `FILLER_SUFFIX`) is now dead code for searches. `answer_question` still uses it.

**NIT**

8. **Stale comments.** VERIFIED.
   - The `options.py` opening comment still gives the Klingon example with the old sentence.
   - The `BAD_INPUT` comment (`options.py:54`) says "a day/time value", but it is now also used for doctor, place and language values.
9. **Repeated ids are listed once per extra copy** (patients and catalog). "p1" and "p1 " (with a space) are both accepted. VERIFIED (failure 3).
10. **Weekday words are looser than the comment says.** VERIFIED.
    - Any 3-letter-or-longer start of a weekday, plus a trailing "s", is accepted: "thursdays", "wednes", "frid", even "thus" (Thursday).
    - It's harmless, but the comment says only "thu" and "thurs".
11. **`CHANGEABLE` accepts 13 names for 5 things** ("reason", "service", "slot", "clinic"…). The tool layer defines one fixed list of field names, so the extra names are unnecessary. JUDGEMENT.
12. **A builder test has a branch that never runs.** `test_r5_long_no_other_doctor_list_is_cut_short` has `"appt_001" if "appt_001" in catalog.visit_types else …`; `appt_001` always exists. VERIFIED.
13. **Hard to follow by ear.** JUDGEMENT. "Dr. Daniel Chen (Dermatology, Downtown Health Center and Richmond Care Center), Dr. Kenji Kim (Dermatology) and 1 more" has an "and" inside a list joined by "and".
14. **Two same-name doctors collapse into one name.** In the "only doctors matching" note, the two Dr. Maria Garcias become one name: "are Dr. Carlos Garcia and Dr. Maria Garcia" (three doctors, two names). Naming her back then asks "which one?", so it is harmless. JUDGEMENT.

**Code checker:** pyflakes finds nothing in `clinic/`, `tests/` or `tests_independent/`.

### Speed

VERIFIED with `probes/p4_scale.py`: a made-up catalog of 500 locations and 2,000 doctors. The busiest visit type, New Patient Consultation, is offered by 716 doctors.

| Search | Time |
|---|---|
| Load the catalog | 0.03 s |
| Skin check | 21–24 ms |
| New Patient Consultation, no wishes | 423–568 ms |
| …with Thursday morning and Spanish | 358–440 ms |
| …with "Dr. Chen" (57 matches) | 363–484 ms |
| …near a neighbourhood | 428–526 ms |
| …with everyone turned down | 463–553 ms (the note is now 178 characters) |
| …with "Klingon" | 459–535 ms |
| …on a Saturday date | 520–619 ms |
| `answer_question` for "Dr. Chen" | 8–14 ms |
| Real catalog, Annual Physical | 8 ms |

That's about the same as round 5 (318–435 ms, on another machine). About half a second is fine for now, but it would be noticeable in a voice call at this scale.

## 4. What's solid

- **Plain day and time fields:**
  - every accepted form works and every refused form is refused, with a note on how to send it;
  - the window edges are exact and move with the clock;
  - leaving a field out keeps it, "" or [] clears it, and `new_value` with `days` is refused, changing nothing.
- **"No preference"** works in every field, independently, and never brings back a turned-down doctor.
- **Sentence refusal** catches every listed word in every form I tried. It never catches a real doctor name, place, landmark or address, or a name that only contains the word inside a longer word.
- **`choose_option`** sets the card, refuses stale or unknown options without changing anything, and keeps the picked doctor off the turned-down list.
- **Notes:**
  - "no other doctor", "Doctors who can", "the only doctors matching" and the unknown-language sentence are true and well formed across the whole catalog, for 3 kinds of caller;
  - no empty or broken sentence appears in about 5,000 searches;
  - a fully booked fortnight is handled cleanly.
- **Patient data:** dates of birth are checked properly, including leap days.

## 5. Files

**New test files** (in `backend/tests_independent/`):
- `test_round6_values.py`
- `test_round6_notes.py`
- `round6_reference.py` (my list checker, shared by two test files)

**Changed test files** (same folder):
- `round2_reference.py`
- `test_round2_other.py`
- `test_round2_wishes.py`
- `test_round3_wishes.py`
- `test_round4_turned_down.py`
- `test_round4_words.py`
- `test_round5_notes.py`
- `test_round5_turn_down.py`
- `test_round5_values.py`

**Probe scripts** (evidence, in [`round-6-probes/`](round-6-probes/); each was run from the agent's scratch copy with `python3 <name>`):

| File | What it shows |
|---|---|
| `common.py` | Shared setup for the probes |
| `p1_same_name_list.py` | Same-name, same-specialty doctors |
| `p2_language_two_words.py` | Two-word language guesses |
| `p3_misc.py` | Summary words, same-name notes, "not far from", `answer_question`, repeated ids |
| `p4_scale.py` | Timings and note lengths at scale |
| `p5_small.py` | One id, loose weekday words, the builder test's dead branch, stale comments |
| `mutate.sh` | Checks that the tests catch small code changes |
| `independent-tests-before.txt`, `failing-tests-before.txt` | The 109 failures as handed over |

Nothing in `clinic/` or `tests/` was touched.
