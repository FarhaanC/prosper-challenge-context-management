# Round 7: the disputed tests (verifier's ruling, then the tester's fix)

| | |
| --- | --- |
| **Date** | Wed 7 Oct 2026, night |
| **Why** | After the round-7 fixes (commit `0673126`), 8 independent tests still failed and the builder thought the tests were wrong. `docs/process.md` says the builder can't dismiss a failing independent test on its own, so a fresh **verifier** decided. |
| **What the verifier got** | The process, the spec notes (rounds 1–7), the code, the data and the tests. The builder's argument was in a separate file it was told to open only **after** writing its own ruling. |
| **Ruling** | 6 tests ("{x} clinic"): **code bug**, so the builder fixed the code. 2 tests (same-name lists): **test bug**, so a fresh tester fixed the tests. |
| **Result** | All 3,124 tests pass (276 builder, 2,848 independent). See [`triage.md`](triage.md), round 7 section. |

Both agents' reports follow verbatim.

---

## 1. Verifier's ruling

### 1. Ruling

- **Group 1, "{x} clinic" (6 tests): code bug.** The spec says in plain words that "…clinic" is not read as part of a place name, so "Downtown clinic" should get the "I don't recognise the place" note. The code should only ignore words like "clinic", "health", "center" or "medical" when they are part of *that* place's own name. "Sunset Clinic" still works because the real name is Sunset Community Clinic. "Downtown clinic" does not, because the real name is Downtown Health Center. The spec should add one sentence saying this. Farhaan can choose the opposite rule, but that is his decision to make, not the builder's.
- **Group 2, same-name notes (2 tests): test bug.** The notes the code writes are correct. The test cuts the list at every comma, including the comma inside the brackets. The test should only cut at a comma that comes before "Dr.". The code doesn't change.

### 2. Step 1: my own view

**Group 1: "{x} clinic"**
- **What the spec says.** Round 7, section 1, lists "…clinic" (next to "…office", "…location" and "…area") as phrases that are "simply not a place name, so it's 'not recognised'". The same section says names are still matched forgivingly, including "generic name words", with the example "Mission Bay Health Center". That example is a clinic's own full name.
- **Both lines can be true at once.** Words like "health", "center" or "clinic" are forgiven when they belong to the place being matched. Under that reading the spec doesn't contradict itself, so I follow it as written.
- **What the code does.** It keeps one fixed list of these words, taken from all eight of our names, and drops them wherever they appear. My checks show what that leads to:
  - "Downtown clinic" and "Downtown center" are accepted, but "Downtown office" is refused. A caller would see no difference between them. The only reason is that two of our clinics happen to have "Clinic" in their names. The project's quality checklist warns about exactly this: a rule that fits this one catalog and won't survive a different one.
  - "Richmond Medical Group" matches Richmond Care Center, and "Midtown Health Center" matches Midtown Medical Group. Neither name is in our records.
  - "Chinatown clinic" becomes "somewhere near Chinatown". We have no clinic in Chinatown. Turning "the Chinatown clinic" into "near Chinatown" is reading the caller's sentence, which is what round 7 set out to stop.
- **What the stricter rule costs.** The AI gets the not-recognised note, which tells it to "pass just a place name", and it tries again with "Downtown". That retry is how the spec intends every other refused phrase to be handled.
- **The tests themselves are fair.** The testers left out Sunset and Mission District, the two places that really have "Clinic" in their names. So they read the spec the same way I do. Another independent test file (test_places.py) also notes that "the downtown clinic" is a phrase under round 7.

**Group 2: same-name notes**
- **The notes are correct.** I ran both cases:
  - "…Dr. Daniel Chen (Dermatology, Downtown Health Center / Richmond Care Center) and Dr. Daniel Chen (Dermatology, Sunset Community Clinic) aren't taking new patients." That names two different doctors, each with their places, and the reason is true.
  - "Doctors with that surname: Dr. David Chen (Cardiology), Dr. Daniel Chen (Dermatology, Downtown Health Center / Richmond Care Center), Dr. Daniel Chen (Dermatology, Sunset Community Clinic) and 5 more." That is 3 named plus 5 more, which matches the 8 Chens.
- **The format is the spec's own.** Round 7, section 5, gives the example "Dr. Daniel Chen (Dermatology, Downtown Health Center / Richmond Care Center)". The brackets make it easy to read aloud.
- **Why the tests fail.** Their list-splitter cuts at every ", ", so it reads one doctor as two broken pieces ("4 names read", "5 + 5 = 8"). The tests' own label checker already understands this format. Only the splitter is wrong.

### 3. Step 2: the builder's argument

**Group 1: it doesn't change my ruling.**
- **"The spec listed '…clinic' by mistake."** That may be true, but it is a claim about what the spec meant to say. The spec records Farhaan's decisions, and the process doesn't let the builder overrule written text on its own. If Farhaan agrees it was a mistake, he changes the spec, and then the 6 test cases change. Until then, the code doesn't match what the spec says.
- **"'Richmond clinic' is like 'Richmond Care Center'."** It isn't. "Richmond Care Center" is that clinic's real name. "Richmond clinic" borrows a word from two *other* clinics' names.
- **What the argument leaves out.** It doesn't address "Chinatown clinic" becoming "near Chinatown", or "Downtown center" being accepted while "Downtown office" is refused.

**Group 2: it agrees with me.** The builder's explanation is the same as mine, and the test should change.

### 4. Anything else noticed

- **The builder's own test asserts the opposite.** One of the builder's own tests, `tests/test_builder_catalog_and_search.py` around line 260, checks that "Richmond clinic" means Richmond Care Center. If the code is fixed, that test has to change too, and the triage record should say so.
- **The same splitter weakness is in other tests that pass.** The real catalog has three pairs of doctors with the same full name (Maria Garcia, Linda Ramirez, Michael Sato). If one of their labels with places ever lands among the first three names in a list, the comma-splitting test will break in the same way. When the testers fix the two failing tests, they should fix the shared splitter, not just these two cases.

---

## 2. The tester's fix (a fresh independent tester)

I fixed the two failing tests by giving the independent tests one shared helper for splitting doctor lists, and the full independent suite now passes.

**What was wrong:** a doctor's label can have a comma inside its brackets, like "Dr. Daniel Chen (Dermatology, Downtown Health Center / Richmond Care Center)". The tests cut lists at every comma, so one doctor was counted as two broken pieces. The code was right, as the verifier ruled.

**What I changed:**
- **`round6_reference.py`**: added one shared splitter, `split_doctor_list`. It only cuts at a ", " that is outside brackets and comes right before "Dr.". It also cuts at the final " and " before a "Dr." label, but that can be turned off. The part of a list before "and N more" is split on commas only, so a wrongly written list there still gets caught.
- **`round6_reference.py`, `capped_names_problems`**: now uses the splitter. Its old check that a list reads "A, B and C" would also break on a comma inside brackets. It now rebuilds "A, B and C" from the pieces and compares that to the text. That check is a bit stricter than before: it also rejects "A and B and C".
- **`test_round7_notes.py`, `split_more`**: now uses the splitter. This fixes the two failing tests, `test_same_name_same_specialty_in_the_cant_do_this_reasons` and `test_same_name_same_specialty_in_the_surname_note`.
- **`test_round5_notes.py`, `list_problems`**: same weak splitting in two places, now uses the splitter.
- **`test_options.py`, `test_alternatives_list_does_not_repeat_a_name_unexplained`**: it split the "Doctors who can" list at every comma, the weakness the verifier warned about for the three real same-name pairs. It now removes the trailing "and N more" and uses the splitter.
- **`test_round6_values.py`, `test_summary_never_lists_the_chosen_doctor_even_if_filled_in_directly`**: splits the card summary's "not:" list with the splitter, then turns any label back into a plain name before checking. The check is at least as strict as before.

I left one other comma split alone, in `test_round2_other.py` line 301. It cuts a single answer's name, not a list of doctors. Every test checks the same things as before; none was loosened.

**Test numbers** (independent tests only):
- Before: 2 failed, 2846 passed (the two named tests).
- After: 2848 passed, 0 failed. Nothing else failed.

I didn't edit `backend/clinic/` or `backend/tests/`. The before run used a temporary copy of the old tests, which I deleted afterwards.

Files changed (in `backend/tests_independent/`): `round6_reference.py`, `test_round7_notes.py`, `test_round5_notes.py`, `test_options.py`, `test_round6_values.py`.
