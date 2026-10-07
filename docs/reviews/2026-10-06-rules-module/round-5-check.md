# Round 5 independent check: catalog and rules module

| | |
| --- | --- |
| **Date** | Wed 7 Oct 2026 |
| **Version checked** | Commit `395cb9f` ("Fix the round-4 findings: the AI says who is turned down") |
| **Who** | One fresh AI agent (not from earlier rounds) acting as both tester and reviewer. It never saw the build or fix conversations. It got the process, the round-4 report and triage (to verify, not trust), all five [spec-change notes](round-5-spec-changes.md), the code, both test folders and the change since `f4595f7`. It was told not to read the builder's build log. |
| **Its tests** | [`backend/tests_independent/`](../../../backend/tests_independent/): 13 older files updated for the round-5 spec (or for unused imports), plus new `test_round5_turn_down.py`, `test_round5_notes.py` and `test_round5_values.py` (297 tests). |
| **Evidence** | Probe scripts in [`round-5-probes/`](round-5-probes/). |
| **Result** | 1,724 tests in all (198 builder, 1,526 independent): 1,700 pass, 24 fail (all real problems or one spec gap). |
| **What happened next** | See [`triage.md`](triage.md), round 5 section. |

The agent's report follows. The builder session saved it (agents can't write files here). The only edit: in its closing file list, the scratch folder paths were shortened to where the files now live in the repo.

---

## 1. Verdict

**Not ready to tag 0.1.0 yet.** Most of the round-4 work holds up:

- The new "turn doctors down" instruction behaves as the spec says.
- The "whom you turned down" notes are now true across the whole catalog.
- The data checks no longer crash on bad input.
- Speed has not got worse.

Two must-fix problems remain. Both are small fixes.

1. **A crash.** The search crashes when nothing is open for a visit in the 14-day window and the caller has turned any doctor down. This is new: the round-4 fix to the "no other doctor" note caused it.
2. **The spec's own safety-net promise is false.** The spec says that if the AI wrongly passes "not Dr. Chen" as a doctor's name, it "matches nobody" and the agent gets a "doctor not found" note. In fact "not Dr. Chen" becomes a wish *for* the Chens: the caller is offered only Dr. Daniel Chen, the doctor they just refused. "another doctor" is heard as Dr. **Andre** Patel and offers only him.

There are also six should-fix items, listed in Part B. The most visible are:
- times of day are still guessed silently in one case;
- the card summary calls a doctor the caller just picked "turned down";
- a note has wrong grammar for several doctors.

## 2. Part A: independent tester

### Numbers

| | Builder tests | Independent tests | Total |
|---|---|---|---|
| **Before** (as handed over) | 198 pass | 1,204 pass, **47 fail** | 1,449 |
| **After** (my updates and new files) | 198 pass | 1,502 pass, **24 fail** | 1,724 |

**The builder's claim mostly holds.** All 47 failures came from tests that used the removed interface. After I rewrote them as the AI would now call the code, 44 of the 47 pass.

The other 3 (the "No, not Dr. Chen" tests) still fail, and they are a real problem. The spec now promises such words give a "doctor not found" note, and they don't (must-fix 2).

The claim also missed something. Six test cases were still *passing* but no longer tested anything. They passed "someone else" or "" to `change_choice` (the card's "the caller changed their mind" method), which now turns nobody down. So "naming a turned-down doctor brings them back" passed without anyone ever being turned down. I fixed them.

### Edited tests

| Test (file) | What changed | Why |
|---|---|---|
| `round2_reference.py` (my model of the spec) | A name brings turned-down doctors back only if it fits one doctor. It also accepts the new "The only doctor matching…" wording. | Round 5, section 3 |
| `test_round3_wishes.py`: `someone_else_whole_catalog` (2 cases), `someone_else_twice…`, `who_can_list…`, `someone_else_after_a_time_change…` | `change_choice("doctor", "")` became `turn_down_doctors(current=True)` | "" no longer turns anyone down. The new call is what the AI makes for "someone else". |
| `test_round3_wishes.py`: `turned_down_doctor_asked_for_again…` | Same change, plus a check that he really is turned down | It was passing without testing anything |
| `test_round3_wishes.py`: `someone_else_without_a_chosen_doctor…` | Adds: `current=True` with only a *named* doctor is refused and changes nothing | Keeps the intent in the new form |
| `test_round4_turned_down.py`: chosen / carried-over / on-offer "someone else" tests | The 10 spoken phrases became the instruction forms (`current`, `provider_ids`, `on_offer` and mixes) | The code no longer reads phrases |
| `test_round4_turned_down.py`: `…ordinary_filler_words` (4 cases) | Reversed: now expects nobody turned down, a `doctor_not_found` note and no narrowing | Round 5, section 2 reverses round 4 on purpose |
| `test_round4_turned_down.py`: `not_dr_name_turns_down_every_match` | Passes all 7 Chen ids. Checks the summary lists all 7 by full name, sorted. | Section 4 |
| `test_round4_turned_down.py`: `negated_name_never_becomes_a_wish…` (now 3 cases) | Same intent. Now expects the spec's `doctor_not_found`. | **Still fails: real problem** |
| `test_round4_turned_down.py`: `visit_type_change_forgets…` | Turns doctors down by instruction. Checks `not_doctor_names` is gone. | That field was removed |
| `test_round4_turned_down.py`: `naming_a_doctor_turned_down_by_name…` | Renamed `naming_one_of_several…`. All Chens turned down by id, then "Dr. Daniel Chen". | It used the removed field |
| `test_round4_turned_down.py`: `naming_…_brings_them_back` (3 cases), `named_back_stays_back…` | Use `current=True`, and check the summary | They were passing without testing anything |
| `test_round4_turned_down.py`: `no_other_doctor_note_names_only…` | Passes the surname's ids | It used the old "not Dr. X" |
| `test_round4_words.py`: `language_change_is_latest…` | "any" now expects a `bad_input` note. Only "" clears. | Section 2 |
| 9 older files | Removed unused imports | R4-9 said these were the tester's to fix |

### New files (297 tests)

- **`test_round5_turn_down.py`** (89 tests):
  - every instruction form and mix, including duplicate ids and ids with spaces;
  - 10 kinds of refusal, each proven to change nothing on the card, plus mixes where one part is impossible;
  - the stage returned, and the place carried over;
  - turning down everyone on offer, for every visit type;
  - `change_choice("doctor", …)` with 13 phrases, on two visit types;
  - naming back: full-name spellings, a surname that fits several doctors, a surname that fits one doctor, the same-name pairs (both Dr. Michael Satos and both Dr. Maria Garcias), and "named back, chosen, then 6 different changes";
  - picking a doctor from a "no other doctor" offer, for every visit type.
- **`test_round5_notes.py`** (25 tests):
  - the "only possible with…" note for every visit type, for three callers (new, returning with no referrals, returning with every referral);
  - the wish in that note is each place, each language, each of the 15 dates, each weekday, and morning and afternoon;
  - each against 5 or more sets of turned-down doctors;
  - the "The only doctor matching 'Dr. X'…" note for every shared surname;
  - the "no other doctor" note for every visit type, in 4 set-ups;
  - a fully booked fortnight.
- **`test_round5_values.py`** (183 tests):
  - language values: one name, "Mandarin Chinese", "Klingon", 13 refused sentences, "" and spaces;
  - morning and afternoon together, in 10 forms;
  - "no preference" vs "any day" (11 and 6 phrases), including as a time of day;
  - house numbers we don't have and every address we do have;
  - named-date wording;
  - every doctor word built from the catalog's specialties, plus 11 words that must match nothing;
  - 32 kinds of broken catalog data, 9 odd top-level shapes and 11 broken patient records, all requiring a clear catalog error and not a crash;
  - one catalog error listing 11 problems, and one patient error listing 4.

### Remaining failures, most serious first

1. **Crash when nothing is open** (3 tests in `test_a_fully_booked_fortnight_with_a_turned_down_doctor…`). **Code bug.**
   - Repro: book every open time of the skin doctors, then search with any doctor turned down.
   - Result: `IndexError` (Python's "list index out of range" error).
   - It worked before round 4: the new "no other doctor" note builds its list of names from the doctors with open times. There are none, and joining an empty list crashes.
2. **Words passed as a name become a wish for a doctor** (11 tests: `test_words_passed_as_a_name…` 8 cases, `test_a_negated_name…` 3 cases). **Code bug** (the spec says "matches nobody").
   - "not Dr. Chen", "No, not Dr. Chen" and "anyone but Dr. Chen" offer only Dr. Daniel Chen.
   - "another doctor" offers only Dr. Andre Patel for a New Patient Consultation.
   - A "check with the caller" note does appear, but the options are already narrowed to the wrong doctor.
3. **Morning and afternoon still guessed silently** (3 tests). **Code bug** (section 5: "a time wish with both 'morning' and 'afternoon' in it" is refused).
   - `days=["Thursday morning", "Friday afternoon"]` gives mornings on both days.
   - So does `change_choice("time", days=[…same…])`.
   - `days=["Thursday afternoon"]` with `time_of_day="morning"` also gives mornings, with no note.
4. **A picked doctor is still called "turned down"** (2 tests). **Code bug** (section 1: "once chosen, that doctor is off the list for good, even after later changes").
   - Turn everyone down, pick from the "no other doctor" offer: the summary reads "not: Dr. Kenji Kim…" and also "Agreed so far: …, Dr. Kenji Kim…".
   - If the next change is a doctor change, he stays on the list for good.
5. **Grammar for several doctors** (3 tests, 224 cases; the names are right in all 455). **Code bug.**
   - Example: "The only doctor matching 'Dr. Garcia' who can do this **is** Dr. Carlos Garcia and Dr. Maria Garcia, whom you turned down."
6. **"Chinese" gives a false note** (1 test). **Spec gap**: the spec covers "Mandarin Chinese" but not "Chinese" alone.
   - The agent says "None of the doctors available to you for Annual Physical speaks Chinese." Yet Mandarin speakers are available and are offered.
7. **An empty sentence** (1 test). **Code bug, minor.**
   - On a fully booked fortnight, "Dr. Garcia" gives "…Doctors who can: ."

## 3. Part B: independent reviewer

### Triage check

| # | Result | Evidence |
|---|---|---|
| R4-1 (doctor named back is lost) | **Mostly fixed** | Named back, chosen, then 6 kinds of change: all pass. But a doctor *picked* from a "no other doctor" offer is still listed as turned down (failure 4). The self-naming note ("matching 'Dr. Daniel Smith' … is Dr. Daniel Smith") still appears if a carried-over doctor is also on the turned-down list. I could only reach that by setting the card's fields directly. |
| R4-2 (notes name the wrong doctors) | **Fixed, but caused a crash** | Every "only possible with…" note is true across places, languages, 15 dates, weekdays and times of day, for 3 callers (thousands of cases). The "no other doctor" names are right. But that change caused the crash (failure 1). The doctor version has wrong grammar (failure 5). |
| R4-3 ("someone else" phrases) | **Partly fixed** | `turn_down_doctors` works in every form, and every refusal changes nothing. But "not Dr. X" and "another doctor" still turn into doctor wishes through name matching (failure 2). |
| R4-4 (data-check holes) | **Fixed** | 52 kinds of broken input all give a clear catalog error, never a crash. One error lists everything. Small leftovers are NIT 10. |
| R4-5 (language sentences) | **Fixed** | 13 sentences are refused with a "how to pass it" note. Leftovers: "Chinese" (failure 6), and NIT 11. |
| R4-6 (morning or afternoon) | **Partly fixed** | Refused for one spoken value. Still guessed for a two-entry list or clashing fields (failure 3). |
| R4-7 (three "no preference" lists) | **Fixed** | One list plus a separate "any day" list, with no overlap (17 phrases tested). See NIT 12. |
| R4-8 (doctor words) | **Fixed** | The regular rule plus 3 irregular words. 26 words (and their plurals) match; "orthopedician" matches nothing. |
| R4-9 (small items) | **Fixed** | "9999 Geary", "9999 Market" and "4455 Market St" are ambiguous and don't narrow. "Dr. Chen" doesn't bring back a turned-down Dr. Daniel Chen. I removed the unused imports. |
| R4-extra (named dates) | **Fixed** | 4 weekend dates, two dates, and weekday mixes are all worded as the spec says. |

### New findings

**MUST FIX**

1. **Crash when nothing is open and someone is turned down.** VERIFIED (probe `p3_edges.py` A, failure 1).
   - Where: `options.py:338-343`, then `_join([])` at line 115.
   - Fix: only add the "no other doctor" note when someone actually has open times (`if turned_down and not valid and every_valid`).
2. **The spec's safety net for AI mistakes doesn't hold.** VERIFIED (`p1_phrases.py`, `p2_another.py`, failure 2).
   - Where: the surname fallback in `fuzzy.py:180-185` turns "not Dr. Chen" into "the Chens". "doctor" counts as a title word (`fuzzy.py:42`), so "another doctor" is matched as the single word "another", which sounds like "Andre".
   - Expect a live reviewer to try exactly this. It is round 4's headline problem again, through a different door.
   - Fix (pick one):
     - give doctor values the same "this is a sentence, not a name" refusal that language values already have (`options.py:423`);
     - or never narrow options on a surname-only or sounds-alike guess: just add the note and let the agent ask.

**SHOULD FIX**

3. **Silent morning/afternoon guess in lists.** VERIFIED (failure 3).
   - Where: `options.py:158` keeps the first time of day it sees, and `card.py:230` does the same. The explicit `time_of_day` field silently beats a spoken one (`options.py:184`).
4. **"Once chosen, off the list" isn't enforced at the moment of choosing.** VERIFIED (failure 4).
   - The card has no "choose" step: the tool layer writes `choices` directly. So the list is only cleaned at the next non-doctor change (`card.py:287-290`).
   - The comment at line 289 ("The caller picked this doctor…") and the method's own description (`card.py:251-253`) read as if this happens on choosing.
   - Fix: add a small `BookingCard.choose(option)` method that sets the choices and removes that doctor from the list.
5. **The "no other doctor" note has no length limit.** VERIFIED (`p4_samename.py`, `p6_scale.py`).
   - With every doctor turned down, a New Patient Consultation reads out 19 names. On the big catalog it is 14,083 characters.
   - Two doctors with the same name are shown once, with no way to tell them apart.
   - Elsewhere, "Doctors who can" lists stop at 3 names ("…and 4 more") and add locations to same-name doctors. Reuse that (`_who_can`, `NAMES_TO_READ`) at `options.py:340-343`.
6. **Plural grammar** in `_turned_down_note`, `options.py:509-511`. VERIFIED (failure 5).
7. **"Chinese" and other near-misses give false "nobody speaks" notes.** VERIFIED.
   - "Chinese", "español" and "Portugese" (a typo) each give "None of the doctors… speaks X", although speakers of Mandarin, Spanish and Portuguese are available.
   - Every unknown name is assumed to be a language nobody speaks (`options.py:439-443`).
   - Farhaan should decide whether "Chinese" maps to Mandarin, or whether unknown names should get a softer "I don't know that language" note.
8. **Decision 23 is only half applied.** JUDGEMENT; needs Farhaan's decision.
   - Round 5 stopped the code reading phrases for doctors and languages. But `parse_time_phrase` (`card.py:47, 58-96`) still reads English, with a list of filler words.
   - Example: "Thursday would be good" works, but "Thursday is fine" and "Thursday works" are refused. "Thursday, Friday" becomes one day called "Thursday Friday".
   - Nothing is guessed silently (unknown phrases are refused), so this is safe. But an interviewer who reads "the code doesn't parse free speech" will find this in a minute.
   - Either move time phrases to the AI as well (days and time of day as plain fields only), or write down why time is the exception.

**NIT**

9. **An empty sentence**, "Doctors who can: .", when nothing is open (`options.py:544`). VERIFIED.
10. **Data-check leftovers.** VERIFIED.
    - An empty `neighbourhood: ""` is refused, but leaving the field out is fine (`catalog.py:227, 235`).
    - A location whose id is broken adds one "works at unknown location" line for every doctor who works there.
    - Patient dates of birth aren't checked to be YYYY-MM-DD, so a record with "12/03/1984" loads but can never be found. Repeated patient ids aren't caught either (`patients.py:94-103`). The spec doesn't require these checks.
11. **Language name tidiness.** VERIFIED.
    - "ASL" is shown as "Asl", and "Cantonese Chinese" as "Cantonese chinese" (`.capitalize()` lower-cases the rest).
    - "English Spanish" silently uses English.
12. **A third word list.** JUDGEMENT. `NOT_A_LANGUAGE` (`options.py:423`) repeats much of the "no preference" vocabulary ("any", "none", "whatever", "dont", "mind", "preference"), a separate list that could drift.
13. **A plain string as `provider_ids`** is refused one letter at a time: "No doctor has the id p, r, o, v, _, 0, 0, 1." VERIFIED (`card.py:258`).
14. **Doctor names are matched twice per search** (`turned_down_ids`, then `_doctor_wishes`). Harmless at this size.
15. **Builder tests check only the friendly path for the new rule.**
    - `test_r4_phrases_are_never_read_as_instructions` uses only "someone else", which happens to match nobody.
    - Nothing tests "not Dr. X", "another doctor", a full calendar, plural notes, or a two-entry time list.

**Speed** (VERIFIED, `p6_scale.py`). Fake catalog of 500 locations and 2,000 doctors:

| Search | Time |
|---|---|
| Load the catalog | 0.03 s |
| Skin check | 62–131 ms |
| Annual Physical (about 720 doctors offer it) | 318–435 ms |
| Annual Physical, everyone turned down | about 430 ms |
| Card summary with 300 doctors turned down | 13 ms |
| Real catalog, Annual Physical | 6 ms |

That is in line with earlier rounds (100–370 ms on other machines). No slowdown.

**Code checker:** pyflakes finds nothing in `clinic/`, the builder tests or the independent tests.

## 4. What's solid

- **`turn_down_doctors`** follows the spec in all 9 forms and mixes. All 12 refusal cases leave the card exactly as it was, and the messages are plain.
- **Naming back:**
  - full names in five spellings bring the doctor back;
  - "Dr. Chen" doesn't, and gives the exact spec sentence;
  - a surname that fits one doctor does;
  - same-name pairs count as one name;
  - named back, chosen, then 6 kinds of change: the doctor stays back, nothing calls them turned down, and the summary is clean.
- **"Only possible with…" notes** are true for every place, language, date, weekday and time of day, across the whole catalog, for 3 kinds of caller. They start with a capital, and their lists are written "A, B and C".
- **The "no other doctor" note** names exactly the right doctors, with the right "option"/"options", even when unrelated doctors are also turned down.
- **Language refusals, "any day" vs "no preference", house numbers, named dates and doctor words** all behave as the spec says.
- **Data checks** survive every odd input I tried (lists as ids, NaN, infinity, huge numbers, booleans, None, wrong top-level shapes). One error lists every problem.

## 5. Files

**New test files** (in `backend/tests_independent/`): `test_round5_turn_down.py`, `test_round5_notes.py`, `test_round5_values.py`.

**Changed test files** (in `backend/tests_independent/`):
- `round2_reference.py`, `test_round3_wishes.py`, `test_round4_turned_down.py`, `test_round4_words.py`;
- unused imports only: `test_round2_places.py`, `test_slots.py`, `test_round3_places.py`, `test_round3_other.py`, `test_round2_other.py`, `test_options.py`, `test_rules.py`, `test_round2_names_and_times.py`, `test_facts_and_robustness.py`.

**Probe scripts** (evidence, in [`round-5-probes/`](round-5-probes/)). Each was run from the agent's scratch copy (`common.py` points at it).

| Script | What it shows |
|---|---|
| `common.py` | Shared setup for the probes |
| `p1_phrases.py` | Phrases passed as doctor names |
| `p2_another.py` | "another doctor" sounds like Andre |
| `p3_edges.py` | The crash, the summary, the time guesses, languages |
| `p4_samename.py` | Same-name doctors and the long "no other doctor" note |
| `p5_plural.py` | Plural grammar |
| `p6_scale.py` | Timings |
| `p7_negated_unique.py` | A negated unique name, and patient data gaps |

Nothing in `clinic/` or `tests/` was touched.
