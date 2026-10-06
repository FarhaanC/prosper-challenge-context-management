# Round 4 targeted independent check: catalog and rules module

| | |
| --- | --- |
| **Date** | Tue 6 Oct 2026, night |
| **Version checked** | Commit `f4595f7` ("Fix the round-3 findings in the rules module") |
| **Who** | One fresh AI agent (not from earlier rounds) acting as both tester and reviewer, as the round-3 reviewer recommended a quick targeted re-check rather than a full round. It never saw the build or fix conversations. It got the process, the round-3 reports and triage (to verify, not trust), the plan, all four [spec-change notes](round-4-spec-changes.md), the code, both test folders and the change since `e94e6d6`. It was told not to read the builder's build log. |
| **Its tests** | [`backend/tests_independent/`](../../../backend/tests_independent/): `round2_reference.py`, `test_round3_identity.py` and `test_round3_places.py` updated for the round-4 spec, plus new `test_round4_identity.py`, `test_round4_turned_down.py` and `test_round4_words.py`. |
| **Evidence** | Probe scripts in [`round-4-probes/`](round-4-probes/). |
| **Result** | 1,412 tests in all (161 builder, 1,251 independent): 1,396 pass, 16 fail (all new tests, all real problems). It confirmed the 17 earlier failures came only from the four deliberate changes. |
| **What happened next** | See [`triage.md`](triage.md), round 4 section. |

The agent's report follows. The builder session saved it (agents can't write files here). The only edit: its closing list of scratch file locations was removed.

---

## 1. Verdict

**Not ready to tag 0.1.0 yet.** Most of the round-3 work holds up:

- The identity check passes every rule I threw at it, including privacy across 1,296 scripted calls.
- The doctor words, place rules and time phrases all behave.
- Speed is still fine on a big fake catalog (500 locations, 2,000 doctors): 100–210 ms per search.

But the "someone else" area still makes the agent say false or silly things out loud. That breaks the module's main promise that every note is true, and it's exactly what a probing Prosper engineer would try. There are three must-fix problems:

1. A doctor the caller asked for again is dropped after any later change, with a nonsense note.
2. The "whom you turned down" note and the "no other doctor" note name doctors who can't actually do the visit.
3. "Someone else, please" (the spec's own heading) isn't understood.

Each fix is small. My new tests already capture them, so a follow-up check only needs to rerun both test folders.

## 2. Part A: independent tester

**Tests before:** 1,193 in all (161 builder, 1,032 independent). 1,176 passed, 17 failed.

**Tests after:** 1,412 in all (161 builder, 1,251 independent). 1,396 pass, 16 fail. All 16 failures are my new tests, and each one is a real code problem. All 1,031 older independent tests pass, and the builder's 161 pass.

**The builder's claim is confirmed.** All 17 failures came only from the four deliberate changes in `spec-changes-round-4.md`. None was hiding a bug.

| Edited test | Why |
|---|---|
| `round2_reference.py` (my own model of the spec) | Change 1: when a wish can only be met by a turned-down doctor, it now expects a `wish_conflict` note ending "whom you turned down", and checks that every doctor named in it really was turned down and really fits. Change 4: a doctor the caller names again is no longer counted as turned down. This fixed 10 tests: 8 seeds of `test_random_combinations_latest_any_wish_including_carried` and the 2 versions of `test_someone_else_whole_catalog`. |
| `test_round3_identity.py::test_need_both_does_not_count` (6 versions) | Change 2: "after 3 unusable answers in a row … offer_new_or_staff". The test now gives two unusable answers and then expects the first miss. It also checks that a usable answer resets the count. |
| `test_round3_places.py::test_streets_not_ours…` | I removed "near Market" (change 3: it's now recognised). It's tested the right way round in my new file. |

**New test files:** `test_round4_identity.py` (31 tests), `test_round4_turned_down.py` (53) and `test_round4_words.py` (136). They cover:

- "someone else" in every spec phrase, for a chosen doctor, a carried-over doctor and doctors on offer;
- naming a doctor again;
- the turned-down note checked against the whole catalog for places, languages and every day in the window;
- the 3-unusable limit;
- time phrases, "no preference" forms, places that must and must not match, and doctor words;
- broken catalog data.

**Remaining failures, most serious first** (no skips, no "expected to fail" marks):

1. **A doctor named again is dropped after the next change** (`test_a_doctor_named_back_stays_back_after_another_change`).
   - Repro: new caller, Skin Cancer Screening, Dr. Daniel Chen chosen → "someone else" → "Dr. Daniel Chen" → choose his first option → `change_choice("time","Thursday")`.
   - The agent says *"Dr. Daniel Chen is only possible with Dr. Daniel Chen, whom you turned down."* and offers other doctors.
   - The card summary reads "doctor: Dr. Daniel Chen; … not: Dr. Daniel Chen".
   - Verdict: code bug (change 4 says naming him brings him back).
2. **False names and a lower-case sentence in the turned-down note** (`test_turned_down_note_for_days_whole_catalog`, 2 versions).
   - Repro: returning caller with all referrals, Mole Removal, Dr. Daniel Chen and Dr. Kenji Kim turned down, day 2026-10-07.
   - Note: *"on Wednesday 7 October is only possible with Dr. Daniel Chen and Dr. Kenji Kim, whom you turned down."*
   - Only Dr. Chen has that day. 15 wrong lists across the catalog, and the sentence starts with a small letter. Verdict: code bug.
3. **The "no other doctor" note lists the wrong doctors** (`test_no_other_doctor_note_names_only…`).
   - Repro: returning caller with all referrals, Annual Well-Woman Exam, `change_choice("doctor","not Dr. Nguyen")`.
   - Note: *"…Dr. Carlos Nguyen, Dr. Daniel Nguyen, … Dr. Nina Nguyen are the only option."* That's 8 doctors; only Linda Nguyen does this exam. It also says "option" for several. 19 visit types are affected. Verdict: code bug.
4. **Ordinary filler words break "someone else"** (4 tests). For "Someone else, please", "someone else please", "the other doctor" and "Another doctor, please":
   - the doctor is not turned down;
   - the agent says *"I couldn't find a doctor called Someone else, please here."*;
   - and offers the declined doctor again.

   Verdict: code bug (the spec says "a phrase like…", and its heading is "Someone else, please").
5. **A refused name becomes a wish for that doctor** (2 tests). "No, not Dr. Chen" and "anyone but Dr. Chen" make the agent offer **only** Dr. Daniel Chen. Verdict: code bug in spirit (the spec covers "not Dr. Chen"); less likely if the AI passes clean words.
6. **Broken data crashes or is silently misread** (6 tests):
   - hours "Mon-Fri 8:00-25:00" gives a plain Python error, not the clear catalog error;
   - an id written as a list crashes the checker itself;
   - `capabilities: "imaging"` (text instead of a list) loads as the letters i, m, a, g…, so MRIs silently become unbookable there;
   - a latitude of "abc" or empty crashes;
   - a patient record that is plain text crashes.

   Verdict: code gaps (the spec says wrong kinds of value are refused, listing every problem).

## 3. Part B: independent reviewer

### Triage check

| # | Result | Evidence |
|---|---|---|
| R3-1 | **Partly fixed, and broke something** | All 7 spec phrases work for a chosen doctor, a carried-over doctor and doctors on offer (30 tests pass). But filler words fail, a doctor named back is lost after the next change, and the new note names the wrong doctors (failures 1–4). |
| R3-2 | Fixed | 15 words that must match nothing, and 15 that must match, all pass. |
| R3-3 | Fixed | "Dr. Dan Chen" gives "…and 4 more". |
| R3-4 | Mostly | Every listed phrase works. Leftovers in findings 6 and 7. |
| R3-5 | Fixed, with a side effect | A language change works through the card, but see finding 5. |
| R3-6 | Fixed | The docstring (options.py:19-20) matches the code (lines 331-340). |
| R3-7 | Fixed | One list, `NEAR_WORDS`. |
| R3-8 | Fixed | All 31 identity tests pass, including the privacy scripts. |
| R3-9 | Partly | Addresses, "in", "Marin", "St Mary's", the today wording, "a Ukrainian", "Mandarin Chinese" and "SF" are all fixed. Field types are checked only for required fields (finding 4). |
| R3-T | Partly | The builder tests try one "someone else" phrase. Nothing tests "named back, then another change" or which doctors a note names. |

### New findings

**1. MUST FIX: a doctor named again is only back until the next change.** VERIFIED (probe `p2.py`, failure 1).
- Where: card.py:204-216 and options.py:333.
- Cause: the turned-down list never shrinks. Naming a doctor only overrides it while the name is still the "heard" wish. After the caller chooses him and changes the day or place, he becomes a carried-over wish, and those deliberately don't override a turn-down.
- Fix: in `change_choice("doctor", <a name>)`, remove the doctors matching that name from `not_provider_ids` and `not_doctor_names`. Also make sure the "only possible with" note can never name the same doctor as its subject.

**2. MUST FIX: notes name doctors who can't help.** VERIFIED (failures 2 and 3).
- Where: options.py:359 and options.py:338.
- Cause: the names come from "turned down and fits" without checking open times for that day (line 359), or from every turned-down doctor whether or not they offer the visit (line 338).
- Fix:
  - At line 359, name only turned-down doctors with times meeting this wish.
  - At line 338, take only turned-down doctors who are in the list of valid options. Use "options" when there are several.
  - Reword the time case so the sentence starts with a capital, e.g. "Tuesday 6 October is only possible with…".

**3. MUST FIX: "someone else" only works as an exact phrase, and refusals are misread.** VERIFIED (`p1.py`, failures 4 and 5).
- Where: card.py:48-49 and 205-215.
- Cause: the text is compared as one squashed word ("someoneelseplease" isn't in the list).
- Other effects:
  - "not him" or "not that doctor" silently turns nobody down, with no note;
  - "no, not Dr. Chen" becomes a wish *for* Dr. Chen.
- The round-3 reviewer raised exactly this (their finding 1d), and the triage marks it fixed.
- Fix: drop filler words before comparing; treat "not" or "but" before a name as a refusal; if a refused name matches nobody, add a note instead of ignoring it. Expect a Prosper question here.

**4. SHOULD FIX: the catalog checks still have holes.** VERIFIED (`p7.py`, failure 6).
- Where: catalog.py:154-163 (hours), 236-248 (an id that is a list crashes the checker), 276-289 (map data and `capabilities` not checked); patients.py:85-88.
- Also: `referrals_on_file: "Radiology"` (text instead of a list) becomes the letters R, a, d…, a silent wrong answer. A latitude of 999 loads without complaint.
- Fix: check these fields the same way as the required ones, and turn errors from reading the hours into catalog errors.

**5. SHOULD FIX: everyday language answers turn into false notes.** VERIFIED (`p8.py`).
- Where: options.py:416-426 and card.py:220.
- `change_choice("language","any language")` makes the agent say *"None of the doctors available to you for Skin Cancer Screening speaks Any language."*
- "not Spanish" and "no Spanish please" become a Spanish wish.
- Fix: treat "any language" as no preference, and refuse or flag "not X".

**6. SHOULD FIX: "morning or afternoon" silently means afternoon only.** VERIFIED behaviour; whether it's wrong is a JUDGEMENT call.
- Where: card.py:82-83 (the last time of day said wins).
- "Thursday morning or Friday afternoon" becomes afternoons on both days, with no note.
- Fix: if both times of day are said, set no time wish (or ask the AI to rephrase).

**7. NIT: three "no preference" lists remain.** VERIFIED.
- They are `fuzzy.NO_PREFERENCE`, `card.ANY_DAY` and an inline set at card.py:76.
- "anyday" and "anydayisfine" are in two of them, so the result depends on which list is checked first. The triage says "one shared check".

**8. NIT: the "orthopedist" exception is acceptable but over-dressed.** JUDGEMENT.
- Where: catalog.py:252-263.
- It's English, not something tuned to this catalog, so it's defensible. But the "general rule" has three special cases:
  - the "-al → -ist" ending exists only for "dental" and needs an exception for "general";
  - the "-ics → -ian" ending produces "orthopedician", which nobody says.
- A small explicit table of irregular words (dentist, orthopedist) next to the regular "-ology → -ologist" rule would be more honest and easier to defend.

**9. NIT: small items.**
- "near 9999 Geary" (wrong house number) gives "not recognised" rather than the two Geary clinics.
- "Dr. Chen" after turning down Dr. Daniel Chen brings him back, because every Chen counts as named.
- "another one" in the someone-else list could mean another *time*.
- Two leftover unused imports in the older independent test files (mine; harmless).

## 4. What's solid

- **Identity:** the 3-unusable limit, the reset, "stays offered", blank spellings, first name plus spelled surname, degree letters, and the found sentence all follow the spec. In 1,296 scripted calls, real and made-up names got identical replies at every step.
- **Turned-down notes for places and languages** are true across the whole catalog (over 20,000 combinations).
- **"Near" plus a street** ("near Geary", "near Market", "near Bryant") gives a note without narrowing, and a bare "Geary" isn't treated as a street. All 14 places that must not match are refused.
- **Doctor words:** all 15 must-not-match words, including podiatrist, hematologist, rheumatologist and psychologist, return nothing.
- **Time phrases** work through both the card and `Preferences.days`. Unclear ones are refused with a "how to phrase it" note.
- **Speed and tidiness:** speed is unchanged at scale, and the code checker (pyflakes) finds nothing in `clinic/`.
