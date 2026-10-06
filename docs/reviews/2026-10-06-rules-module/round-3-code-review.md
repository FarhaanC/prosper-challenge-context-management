# Round 3 independent code review: catalog and rules module

| | |
| --- | --- |
| **Date** | Tue 6 Oct 2026, late evening |
| **Version reviewed** | Commit `e94e6d6` ("Fix the round-2 findings in the rules module") |
| **Who** | A fresh AI agent (not the round-1 or round-2 reviewers) that never saw the build or fix conversations. It checked every round-2 triage item, acted as the **verifier** for the two items the builder had left unchanged, hunted for new bugs and slop, and judged the builder's tests. It read the process, the earlier reports, the triage (to verify, not trust), the plan, the code, both test folders and the full change since `d4983c2`. It was told not to read the builder's build log. |
| **Evidence** | Its probe scripts are in [`round-3-probes/`](round-3-probes/). Paths at the top of each need adjusting to rerun them. |
| **What happened next** | See [`triage.md`](triage.md), round 3 section. |

The agent's report follows. The builder session saved it (agents can't write files here); it is unedited.

---

## 1. Verdict

It's much more solid than round 2. Every round-2 demo scenario I re-ran now behaves correctly. I also confirmed the builder's claim about the independent tests: I built my own scratch copy with the three agreed changes undone (notes as text, the old identity answers, the old handling of far-off dates), and **all 632 independent tests passed**. The builder's 133 tests pass, and pyflakes (a code checker) finds nothing. Speed is fine at the plan's scale: 110–200 ms per search on a generated catalog of 500 locations and 2,000 doctors.

But the "someone else, please" fix (R2-8) is only half built. It breaks the module's headline promise that every note is true: there are now two simple ways to make the agent say something false out loud. The new doctor-word rule for specialties also brings in wrong matches ("podiatrist" becomes Pediatrics, "hematologist" becomes Dermatology). In a live review, the design and the identity check would land well. A probing engineer who tries "someone else" during the options, or "actually, the first doctor is fine", would find a false note within minutes. **Not ready to tag 0.1.0 yet.** The fixes are small, maybe half a day with tests, and need a quick targeted re-check rather than a full round 4.

## 2. Triage check

| # | Result | Evidence |
|---|---|---|
| R2-1 | Fixed | Named Dr. Chen, then "the Midtown one": Dr. Kim at Midtown, with a true note. |
| R2-2 | Fixed | All the reported cases work. New edge cases are in finding 4. |
| R2-3 | Fixed | "main", "Bay Area", "Glen Park", "Cole Valley", "on the way to", "anywhere", "mid town" and "Downtown SF" all behave. Small gaps are in finding 9. |
| R2-4 | Fixed | I tried about 20 name and date-of-birth combinations. No answer depends on the name alone, so the identity check doesn't reveal who is a patient. One small slip in the step order (finding 8). |
| R2-5 | Fixed | Measured: Saturday 155 ms, a date outside the window under 1 ms, the heaviest case 200 ms. |
| R2-6 | Fixed | |
| R2-7 | Fixed | |
| R2-8 | **Partly, and broke something** | Works only if the caller had already *chosen* an option. Finding 1. |
| R2-9 | **Fixed, but broke something** | "physician" no longer matches Physical Therapy, but the new doctor-word rule makes new wrong matches (finding 2). |
| R2-10 | Fixed | Small wording issue in finding 9. |
| R2-11 | Fixed | Missing fields, repeated ids and the site rotation are all handled. Wrong field *types* still crash (finding 9). |
| R2-12 | Mostly | `iter_open_slots` and `open_slots` are now used only by tests. |
| R2-13 | Fixed | |
| R2-14 | Fixed | |
| R2-15 | Fixed | |
| R2-16 | Fixed | |
| R2-17 | Not changed | Verdict below. |
| R2-18 | Noted, fine for now | |
| R2-19 | Fine | Left for the tester. |
| R2-T | **Partly** | Test section, T1–T3. |

**Verifier verdicts on the two "Not changed" items:**
- **R2-9, "gynecologist": OK to leave.** Nothing is booked wrongly: the lookup returns "not sure" and the AI already has the 21 exact specialty names. The real problem is the reverse one: the doctor-word rule now matches words it shouldn't (finding 2). Fix that, and "gynecologist" can stay unrecognised.
- **R2-17, doctor nicknames: OK to leave.** A nickname table would be a hack tied to this catalog. "Dr. Li" and "Dr. Chen Wei" return "not found", which is safe because the agent asks again. One condition: the "Doctors with that surname" note must stop cutting the list short (finding 3). Otherwise "Dr. Liz Nguyen" gets a note that never mentions Dr. Elizabeth Nguyen.

## 3. New findings (most serious first)

**1. MUST FIX: "someone else" is half built, and it makes notes false.** card.py:171-173, options.py:306-343, options.py:257-260. VERIFIED (scratch scripts I wrote and ran outside the repo).
- **(a) It only works for a chosen doctor.** A caller usually says "someone else" while *hearing* the options, before choosing one. Then nobody is turned down.
  - Repro: Skin Cancer Screening with Dr. Daniel Chen named → options are all Chen → `change_choice("doctor", "")`. Option 3 is Dr. Daniel Chen again.
  - The same happens for a carried-over doctor.
- **(b) Naming the turned-down doctor again gives a false note.** Choose Dr. Kim → `change_choice("doctor", "")` → `change_choice("doctor", "Dr. Kenji Kim")` ("actually, he's fine").
  - The note says *"Dr. Kenji Kim has no open times for Skin Cancer Screening in the next 14 days"*. He has plenty.
  - Cause: the turned-down list is never cleared, and `_why_doctor_cant` takes "turned down" to mean "no times".
- **(c) A false place note.** Turn down Kim, then ask for "the Midtown one".
  - The note says *"Midtown Medical Group has nothing available for Skin Cancer Screening in the next 14 days"*. Kim has times there.
- **(d) The AI must pass an empty string to mean "someone else".** In practice it may pass the caller's words.
  - "someone else" gives "I couldn't find a doctor called someone else".
  - "another doctor" sounds like Dr. Andre Patel, so his name comes up.
  - "not Dr. Chen" offers **only** Dr. Chen.
- **Fix:**
  - Give "turn this doctor down" its own explicit setting, used when the caller hears options too.
  - Naming a doctor takes them off the turned-down list.
  - Build the "nobody can" notes from the full list *before* turned-down doctors are removed, and say "only Dr. Kim, whom you turned down, works there".
  - Add tests for all four cases.

**2. SHOULD FIX: the doctor-word rule creates wrong specialty matches.** catalog.py:227-237 and line 327. VERIFIED.
- What happens:
  - "podiatrist" (foot doctor) becomes Pediatrics, because the rule invents the word "pediatrist";
  - "hematologist" (blood) becomes Dermatology;
  - "nephrologist" (kidney) becomes Neurology;
  - "audiologist" (hearing) becomes Radiology.
- The 0.85 spelling-similarity allowance is too generous for long words that differ only in their first syllable. The rule also invents "generist" for General, and `endswith("ology") or endswith("y")` repeats itself (anything ending in "ology" already ends in "y").
- Fix: match the derived doctor words exactly (keep spelling forgiveness for the 21 real names only), drop the "-ist" form for "-ics", and add these four as "must NOT match" tests.

**3. SHOULD FIX: the "Doctors with that surname" note cuts the list short without saying so.** options.py:499-502. VERIFIED.
- "Dr. Dan Chen" matches 7 Chens, but the note names 3, with no "and 4 more".
- "Dr. Liz Nguyen" never names Elizabeth Nguyen.
- This is round-1 item 10 coming back in a different place.
- Fix: list the matching doctors who actually offer this visit type, or add "and N more".

**4. SHOULD FIX: everyday time phrases get rejected; there are three different "no preference" lists.** card.py:44-66, options.py:43, catalog.py:50. VERIFIED.
- Results:
  - "this afternoon" is stored as day "this";
  - "Thursday afternoon please" is stored as day "Thursday please";
  - "don't mind" isn't recognised, because the list says "dont mind" but the text is never tidied first;
  - each of these gives `bad_input`.
- The place list and the doctor list *do* tidy the text first, so "don't mind" works for those but not for time.
- Also, `days=["any time"]` doesn't clear "morning", while the same words passed as the plain value do.
- Fix: one shared "no preference" check that tidies the text, and drop filler words ("please", "this", "in the") before splitting.

**5. SHOULD FIX: language can't be the "latest change" through the card.** card.py:36-41. JUDGEMENT.
- `CHANGEABLE` has no "language" entry. So "newest wish wins" for a language only works if the tool layer sets `latest` by hand.
- The two language tests do exactly that (round-2 reviewer point T2, still open).
- Fix: add "language" to `change_choice`, or document that the tool layer must set `latest`.

**6. NIT: the module docstring doesn't match the code.** options.py:19 says turned-down doctors are "left out entirely". Line 305 says "unless nobody else can do it". The code follows line 305.

**7. NIT: the same list is written twice.** catalog.py:53-61: the "near" phrases appear both in `NEAR_PHRASE` and inside `FILLER_PREFIX`, so the two lists can drift apart.

**8. NIT: identity step order.** patients.py:153. VERIFIED.
- After "offer to register or speak to staff", another try without a spelled name goes *back* to "spell your last name".
- On the third try, a correct name and date of birth isn't looked up at all.
- There's no limit on tries once a spelled name is given.
- Passing only the first name together with a spelled surname returns "incomplete".
- All small, but expect a question on it.

**9. NIT: smaller items.**
- Wrong field *types* crash with plain Python errors instead of a clear catalog error: a duration of "abc", `languages: null`, a record that isn't a dict. A `location_ids` string gives "works at unknown location l".
- "near Geary" and "near Market" aren't recognised (streets need a street word or "on").
- "Marin" becomes North Gate (it's 91% like "Marina").
- "st" counts as a street word, so a generated "St. Mary's Clinic" would break at scale.
- The note reads *"Nothing is open today … in the next 14 days"*.
- `_a("Ukrainian")` gives "an Ukrainian".
- `card.summary()` doesn't show turned-down doctors, so the AI loses them on a stage move.

## 4. Test quality

**T1. SHOULD FIX: the R2-8 test only covers the easy case.** `test_r2_8_…` only uses a *chosen* doctor, which is why finding 1 slipped through. This is the same "shaped to the code" pattern the round-2 reviewer flagged. VERIFIED.

**T2. SHOULD FIX: "must NOT match" coverage is still thin for specialties.** The only negatives are "astrology", "banana" and "physician". VERIFIED.

**T3. NIT: two wish tests still set `latest="language"` directly.** A real call can't produce that value (finding 5).

**T4. NIT: a mislabelled test, and old gaps that remain.**
- `test_r2_9_an_arabic_speaking_doctor` is really R2-14.
- Still missing:
  - a speed test at scale;
  - a "same answer every run" test across separate runs (today it runs twice in one go);
  - tests of natural time phrases;
  - a test of the identity step after "offer".

## 5. What's solid

- **Wish order:** all of the independent tester's random-combination comparisons pass once the agreed changes are undone. The R2-1 bug is truly gone.
- **Identity:** no answer reveals whether a name belongs to a patient. Misheard names, a spelled surname, "Jr", titles, and "Tyler" vs Taylor all behave.
- **Notes:** a plain record that copies, pickles and turns into JSON cleanly.
- **Places:** of 190 phrasings I tried, nothing silently restricts to a wrong clinic except "Marin".
- **Dates:** far-off dates are refused up front, and day-skipping really skips. Speed is fine at scale.
- **Rules:** each rule is written once, and `check_booking` handles odd ids safely.
- **Code hygiene:** pyflakes is clean, and the thresholds have names and reasons.

## 6. Likely Prosper questions

1. *"Caller hears three Dr. Chen options and says 'someone else'. What happens?"* No good answer yet (finding 1).
2. *"How do you know every note is true?"* Good, except after a doctor is turned down (finding 1).
3. *"Can your identity check reveal who is a patient?"* Good answer now.
4. *"Does it scale to 2,000 doctors?"* Good: measured 110–200 ms.
5. *"Why 0.75, 0.8 and 0.85, and what does 'podiatrist' map to?"* The thresholds are explained, but the podiatrist answer is wrong today (finding 2).
6. *"Named Dr. Chen, then 'the Midtown one'?"* Good.
7. *"What if the AI passes 'next Thursday' or 'this afternoon'?"* Half good: it's refused correctly, but common phrases fail too (finding 4).
8. *"Why hand-written place rules instead of letting the AI resolve the place?"* Defensible (predictable and testable), but the street words and landmark list are tuned to this catalog. Say so.
9. *"How does a language request become the newest wish?"* Weak (finding 5).
10. *"Why did you leave nicknames out?"* Good, once the surname note lists everyone (finding 3).
