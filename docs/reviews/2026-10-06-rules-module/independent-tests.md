# Independent test report: catalog and rules module

| | |
| --- | --- |
| **Date** | Mon 5 Oct 2026, late evening (work planned for Tue 6) |
| **Version tested** | Commit `2725eca` ("Add catalog and rules module with builder tests") |
| **Who** | A fresh AI agent that never saw the build conversation. It worked from the plan (`03-phase-2-plan.md`), the catalog findings (`01-findings-and-decisions.md`), the build decisions in [`spec-given-to-tester.md`](spec-given-to-tester.md) and the raw `catalog.json`. The builder's own tests were removed from its copy. It could read the code only to learn how to call the functions, not to work out the expected answers. |
| **Its tests** | [`backend/tests_independent/`](../../../backend/tests_independent/). Its own copy of the rules, written straight from `catalog.json`, is in `reference.py`. |
| **Result** | 296 tests: 271 passed, 25 failed (11 separate problems). |
| **What happened next** | See [`triage.md`](triage.md). |

The agent's report follows. It could not write files itself, so the builder session saved it. The only edit: its opening note about its scratch folder paths was shortened to the repo path.

---

The tests are in `backend/tests_independent/`. Run `python -m pytest tests_independent` from the `backend` folder. Every test uses a fixed "now" of Tuesday 6 Oct 2026, 09:00. Nothing in `clinic/` or `data/` was changed.

## 1. Summary

**296 tests: 271 passed, 25 failed.** The 25 failures come from **11 separate problems**. Some problems fail several tests, for example 5 spellings of the same patient-lookup bug.

**Verdict.** The core is solid. I wrote my own small copy of the 6 rules straight from catalog.json. I compared it with the module across:
- all 82 visit types, 50 doctors and 8 locations;
- 24 kinds of caller: new, returning with no referrals, returning with each specialty's referral, and returning with all referrals.

They agreed everywhere. Every option the module offered passed every rule and the final check. The dead ends, the knee MRI, OB/GYN and "skin check with Dr. Garcia" cases all behave as the spec says. The time-slot rules held for every doctor and location.

The weak spot is **what happens when two wishes meet**: a doctor wish together with a day, language or place wish. There the module sometimes ignores what the caller just asked for, or tells the agent something false. That is exactly the "sounded right, was wrong" problem the project exists to fix, so it matters more than the count suggests.

## 2. Failures, most serious first

### F1. Changing the location is ignored if the old doctor doesn't work there
- **Test:** `test_card.py::test_location_change_to_place_old_doctor_does_not_work`
- **Spec:** the plan's change table says a location change clears "location, slot (and doctor, if they don't work there)". Decision 26 says the old doctor becomes a wish, honoured only "if they still fit".
- **Code:** I set up a card for Skin Cancer Screening with Dr. Daniel Chen at Downtown. Then I ran `change_choice("location", "the Midtown one")` and searched again with the card's preferences.
  - All 3 options are with Dr. Daniel Chen, at Downtown or Richmond.
  - The note says *"Midtown Medical Group has no doctor available for Skin Cancer Screening."*
  - That is false. Dr. Kenji Kim does skin screening at Midtown, and the module offers him when there's no doctor wish.
- **Verdict:** code bug. The old doctor is treated as a must-have and the new place as optional. It should be the other way round.
- **How serious:** high. The caller asks for Midtown and is told Midtown can't do it.

### F2. False "nothing available" notes when a doctor wish narrows the search
- **Tests:** `test_options.py::test_nothing_open_note_is_true_when_doctor_wish_also_set`, `test_language_note_is_true_when_doctor_wish_also_set`, `test_named_place_note_is_true_when_doctor_wish_also_set`
- **Spec:** wishes that can't be met become plain notes, and "nothing is silently kept or dropped" (decision 26). So the notes have to be true.
- **Code:** the module applies the doctor wish first. It then writes its notes about that one doctor, but words them as if they were about every doctor. Examples:
  - **Day:** Echocardiogram, wished-for doctor Dr. David Chen, day "Monday". The note says *"Nothing is open for 'Monday' in the next two weeks."* Without the doctor wish, the same search offers Dr. Linda Ramirez on Monday 12 Oct. I found **35 false claims like this** across the catalog.
  - **Language:** Skin Cancer Screening, "Dr. Daniel Chen" plus Spanish. The note says *"None of the available doctors for this speaks Spanish."* Dr. Kenji Kim and Dr. Daniel Smith both do.
  - **Place:** "Dr. Daniel Chen" plus "the Midtown one" gives the same false Midtown note as F1.
- **Verdict:** code bug. Keeping the doctor is a fair choice. But the note should say something like "Dr. Chen has nothing Monday; Dr. Ramirez does", not "nothing is open". This will show up after every time change, because decision 26 keeps the old doctor as a wish.
- **How serious:** high. "Anything Monday?" gets a confident, wrong "no".

### F3. "Mr. Wilson" identifies a patient by surname alone
- **Test:** `test_patients.py::test_title_plus_surname_does_not_identify` (5 spellings)
- **Spec:** decision 29 says "a surname alone does not identify a patient".
- **Code:** `lookup("Mr. Wilson")` returns James Wilson, with his Radiology and Orthopedics referrals. So do "Mrs. Johnson", "Ms Brown", "Mr Khan" and "Mr. Taylor". The check that a name has two words counts "Mr." as a word, but the name matching then throws "Mr." away.
- **Verdict:** code bug.
- **How serious:** medium-high. A stranger gets someone else's record and referrals.

### F4. "Closer to downtown", the caller's own words in the baseline call, isn't understood
- **Tests:** `test_places.py::test_everyday_near_phrasings` ("closer to Downtown" and "the one near Downtown"), `test_options.py::test_knee_mri_closer_to_downtown_baseline_phrase`
- **Spec:** baseline problem 4 must be fixed. Decision 24 lists the "near" words: near, close to, around, next to, not far from, by.
- **Code:** both phrases come back as "unknown place". For James Wilson's knee MRI, the first option offered is **Midtown**, with the note "I don't recognise the place 'closer to downtown'". "closest to downtown" and "somewhere near downtown" do work.
- **Verdict:** partly a spec gap, because "closer to" isn't on the decision 24 list. But it fails quietly, on the demo's own phrase. If the AI passes the caller's words through as they are, the demo breaks.
- **How serious:** medium.

### F5. "Dr. Grace" finds the three Garcias, not Dr. Grace Rodriguez
- **Tests:** `test_names.py::test_every_first_name_alone_finds_its_holders`, `test_facts_and_robustness.py::test_doctor_facts_first_name_grace`
- **Spec:** forgiving name matching that returns every match, so the agent can ask "which one?".
- **Code:** "Dr. Grace" returns Maria Garcia, Maria Garcia and Carlos Garcia. "Grace" and "Garcia" get the same sounds-alike code, and a close surname match beats an exact first-name match. This is the only one of the catalog's 31 first names that fails.
- **Verdict:** code bug.
- **How serious:** medium. The agent offers the wrong doctors and answers questions about the wrong people.

### F6. answer_question shows 3 of the 7 Dr. Chens and says "ask which one"
- **Test:** `test_doctor_facts_seven_chens_not_silently_cut`
- **Spec:** "Always return *all* matches for duplicate names". But answer_question is also meant to return "small results only".
- **Code:** it returns David, Daniel and Wei Chen, with the message *"Several doctors share this name; ask which one."* Emily, Lucas, Michael and Nina Chen are dropped without a word.
- **Verdict:** the spec contradicts itself here. The most reasonable fix is to say how many there are, e.g. "7 doctors called Chen".
- **How serious:** medium. The agent may ask "David, Daniel or Wei?" when the caller means Emily.

### F7. An unknown visit type crashes instead of saying no
- **Tests:** `test_can_book_unknown_visit_type_does_not_crash` (4 cases), `test_find_options_unknown_visit_type_does_not_crash` (2 cases)
- **Code:** if the AI passes a visit type that doesn't exist ("appt_999", an empty value, or a name like "MRI - Knee" instead of an id), `can_book_visit_type` and `find_options` stop with an error instead of giving an answer. `check_booking` handles the same input politely.
- **Verdict:** a robustness gap. The spec doesn't cover it directly, but choose_visit_type is meant to "reject with a reason", and the AI can invent ids.
- **How serious:** low to medium, depending on whether the layer above catches the error.

### F8. Changing the time with a plain value loses it
- **Test:** `test_change_time_new_value_not_silently_dropped`
- **Spec:** the plan says change_choice "records the new value as a preference". Decision 23 says days are stored as structured fields.
- **Code:** `change_choice("time", "Thursday")` clears the slot but stores nothing. The wish only survives if it's passed as `days=["Thursday"]`.
- **Verdict:** spec ambiguity. It should either record the value or refuse it, not drop it silently.
- **How serious:** low to medium.

### F9. "Ahmad Kim" is identified as Ahmed Khan
- **Test:** `test_different_surname_not_matched_by_sound_alone`
- **Verdict:** a judgement call on my part. "Kim" and "Khan" only share a sounds-alike code. Decision 29 allows misheard spellings, but a different surname is more than a spelling. The same looseness turns "James Wilkins" into James Wilson and "Emily Bryan" into Emily Brown. I didn't make those two failing tests.
- **How serious:** medium, because the caller gets the wrong record and referrals.

### F10. A blank place wish gives a strange note
- **Test:** `test_blank_place_hint_is_no_wish`
- A place wish of just spaces gives "I don't recognise the place '   '" instead of being treated as no wish.
- **How serious:** low.

### F11. The list of alternatives repeats names and mislabels doctors
- **Test:** `test_alternatives_list_does_not_repeat_a_name_unexplained`
- **Code:** Annual Physical plus "Dr. Linda Ramirez" gives *"Family Medicine doctors who can: Dr. Maria Garcia, Dr. Maria Garcia, Dr. Wei Chen and 15 more."*
  - The same name is read out twice with nothing to tell the two apart.
  - Pediatrics and Internal Medicine doctors are called "Family Medicine doctors".
- **How serious:** low.

## 3. Spec gaps and ambiguities (nothing failed)

- **The plan and decision 26 disagree on a time change.** The plan clears only the slot. Decision 26 also clears the doctor and location, keeping them as wishes. The code follows decision 26, so be ready to explain why.
- **"The Mission"** is treated as ambiguous by the code, but your own location file lists it as a nickname for Mission District. One of them should change.
- **Neighbourhood names** ("the Hayes Valley one", "the Marina one") rank options by distance but don't restrict them to that location. Decision 24 doesn't say whether a neighbourhood counts as naming one of our locations.
- **A wrong first name returns nobody.** "Dr. John Garcia" finds no doctors, with no fallback to the Garcias.
- **A wrong date of birth quietly makes the caller a new patient**, with no "that date didn't match" signal. Dates must also be written exactly as YYYY-MM-DD.
- **The "soonest" wish is stored but never used.** There's also no way to clear a day or time wish ("any day is fine").
- **After a visit-type change, the old location stays a hard limit** for the new visit type. That follows decision 26, but it may surprise callers.
- **`match_specialty` rejects "Allergy", "dermatologist" and "cardiologist".** That's fine only if the AI always uses the exact 21 names.
- **Addresses aren't searchable**, e.g. "the one on Geary".
- **`read_back` crashes on an incomplete card.** It's only meant to be called after choose_option.
- **"now" has no time zone.** The layer above must pass San Francisco local time.

## 4. What I covered, and what I couldn't

**Covered:**
- **All 6 rules**, yes and no cases. My own copy of the rules was compared with the module across the whole catalog, and `check_booking` was run on all 32,800 combinations of visit type, doctor and location.
- **Callers:** new vs returning, and referrals, including lower-case spellings.
- **Named cases:** the 8 visit types no doctor offers, the 6 a new patient can't actually book, the knee MRI, OB/GYN for Emily Brown, and a Mammogram for a new patient.
- **Doctor names:** every full name, surname and first name, misheard names, and names that shouldn't match.
- **Patient lookup:** misspellings, surname only, titles, unknown callers, two patients with the same name, dates of birth.
- **Places:** about 55 phrasings, covering "near X", "the X one", ambiguous names, landmarks, nonsense, odd casing and empty strings.
- **Time slots:**
  - opening hours, lunch, weekends;
  - closing time vs visit length, 2-hour notice, the 2-week horizon;
  - one location per doctor per day;
  - the same results on every run, even across separate runs;
  - double booking, and bookings of different lengths.
- **find_options:**
  - checked for every visit type and 3 kinds of caller;
  - only valid options, at most 3, spread across different doctor and location pairs, soonest first;
  - wishes for day (11 forms), time of day, language (7), doctor and place, including wishes that can't be met and wishes that conflict.
- **The booking card:** the change table, both on its own and end to end.
- **Read-back, answer_question, and bad input.**

**Couldn't test:**
- **The layer above this module:** start_booking, choose_option, confirm_booking, saving the booking to a file, stage moves and Pipecat.
- **The AI itself:** how it turns speech into the structured wishes.
- **The 2,000-doctor scale test.**
- **Exact free times.** Which slots count as "taken" comes from a fixed scrambling formula I can't predict independently, so I checked the slot rules instead of specific times.
