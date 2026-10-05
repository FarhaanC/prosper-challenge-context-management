# Round 2 independent code review: catalog and rules module

| | |
| --- | --- |
| **Date** | Tue 6 Oct 2026, early morning |
| **Version reviewed** | Commit `d4983c2` ("Fix all 17 findings from the rules-module review") |
| **Who** | A fresh AI agent (not the round-1 reviewer) that never saw the build or fix conversations. It was asked to check each triage item, hunt for new bugs and slop brought in by the fixes, and judge the builder's tests. It read the process, both round-1 reports, the triage (to verify, not trust), the plan, the code, both test folders and the full change since `2725eca`. It was told not to read the builder's build log. |
| **Evidence** | Its probe scripts are in [`round-2-probes/`](round-2-probes/) (`latest.py`, `card2.py` and `places.py` reproduce findings 1-4). They were written against its scratch copy, so the paths at the top need adjusting to rerun them. |
| **What happened next** | See [`triage.md`](triage.md), round 2 section. |

The agent's report follows. The builder session saved it (agents can't write files here); the only edit is that a scratch folder path was shortened.

---

## 1. Verdict

The structure is much better, and most round-1 problems really are fixed. In 1,743 random searches mixing doctor, place, day, time and language wishes, the code never offered an invalid option and never silently dropped a wish. Every round-1 demo scenario now gives the right options and a true note. The builder's claim about the independent tests also holds. I filled in each patient's date of birth automatically in a scratch run, and 295 of 296 passed. The last one is the intended change: two patients with the same name now get "ask for the date of birth" instead of a list of both names.

But the fixes brought in two real bugs on the change-your-mind path, which is the demo path. First, the code that records "what the caller changed last" uses the word "location", while the code that reads it expects "place". So "the newest wish wins" quietly fails for location changes. Second, changing only the time of day wipes the day the caller already asked for. Place matching also has new false matches on short words: "the main one" becomes North Gate. A demanding reviewer would like the design, then find bug 1 within minutes by asking the same question as last round in a slightly different form. Not ready to tag v0.1.0 yet. The fixes are small.

## 2. Triage check

| # | Result | Evidence |
|---|---|---|
| 1 | **Partly** | Fixed when the old doctor was a *chosen* option. Broken when the doctor was only *named* by the caller (new finding 1). The language note can still be false (finding 7). |
| 2 | **Fixed, but brought in a privacy leak** | Titles, "Tyler" vs Taylor, "Kim" vs Khan and a wrong date of birth all behave. New problem: finding 4. |
| 3 | **Partly** | All the round-1 phrasings now work. New false matches: finding 3. |
| 4 | Fixed | Every approximate match is labelled, and the surname fallback says so. |
| 5 | **Partly** | `change_choice("time", "afternoon")` stores "afternoon" as a *day*, so the search returns `bad_input` and no options. A time-only change wipes the days (finding 2). |
| 6 | Mostly | rules.py:101 writes the doctor half of rule 5 a second time. options.py:235-243 turns rule numbers back into its own sentences. |
| 7 | **Partly** | Catalog checks are still missing: duplicate ids silently overwrite each other, a missing key crashes with a plain `KeyError`, and a doctor with more than 5 sites never works at some of them (finding 11). |
| 8 | **Partly** | Typical searches are fast now. A day nobody can meet still takes 1.2–1.4 s at scale (round 1 measured 1.5 s). The triage's "25–120 ms" is also wrong for Annual Physical: 203 ms (finding 5). |
| 9 | Fixed | I couldn't check `requirements.txt` for `tzdata`: it isn't in this copy. |
| 10 | Fixed | |
| 11 | **Partly** | Notes now have a `kind`, but the str-based Note crashes on copy and pickle, and loses its `kind` in JSON (finding 6). Return shapes are still mixed: dicts, objects with `to_dict()`, and a bare list of strings. |
| 12 | Fixed | |
| 13 | Fixed | Saving bookings to a file is deferred, as stated. |
| 14 | Fixed | |
| 15 | **Partly** | New comments that don't match the code: the `latest` values, the `SPECIALTY_STEM_MIN` comment, patients.py's "never quietly treated as new", and "on the way to" in `NEAR_PHRASE`. |
| 16 | **Partly** | One test is vacuous, others are shaped to the code, slot rules aren't tested directly, and there are no near-miss "should NOT match" tests (section 4). |
| 17 | **Fixed, but brought in a bug** | "physician" now maps to Physical Therapy (finding 9). |

## 3. New findings (most serious first)

**1. MUST FIX: a location change doesn't win over a doctor the caller only named.** VERIFIED. options.py:355 sorts wishes by `w.kind != prefs.latest`, and the place wish's kind is `"place"`. But card.py:143 writes `latest = "location"` (also its comment at card.py:61). So a location change is never treated as the latest change. Round 1's scenario only passes now because a *chosen* doctor is a carried-over wish, which always sorts last.
- Reproduction: `Preferences(doctor_name_heard="Dr. Daniel Chen")`, then `card.change_choice("location", "the Midtown one")`, then `find_options`.
- Result: Chen at Downtown and Richmond, with the note "Midtown Medical Group isn't available with Dr. Daniel Chen".
- With `latest="place"` you get Dr. Kim at Midtown, which is what the caller asked for.
- This is the realistic demo order: "skin check with Dr. Chen", then "the Midtown one" before picking an option.
- Fix: use one word for both. Make named constants shared by card.py and options.py, and add a test that goes through `change_choice`.

**2. MUST FIX: a time change silently drops the day wish.** VERIFIED. card.py:138-139.
- `change_choice("time", days=["Thursday"])` then `change_choice("time", time_of_day="afternoon")` leaves `days=[]`. Thursday is lost without a word.
- `change_choice("time", "afternoon")` (or "Thursday afternoon") stores it as a day, so the search returns `bad_input` and no options.
- Fix: only replace `days` when a day was given. Send a plain "morning" or "afternoon" to `time_of_day`.

**3. MUST FIX: short words wrongly match place names, and the result is a silent restriction.** VERIFIED. The cause is `_words_fit` (catalog.py:166), which accepts words that are 80% alike in spelling, even very short ones.

| Caller says | Code decides | Effect |
|---|---|---|
| "the main one", "the main clinic" | North Gate | Only North Gate is offered, no note ("main" vs "marina" is 0.8 alike) |
| "anywhere in the bay area" | Mission Bay | Only Mission Bay is offered, no note |
| "none" | Noe Valley | Options ranked by distance from Noe Valley |
| "no" | Nob Hill | Options ranked by distance from Nob Hill |

Nearby gaps:
- "any", "no preference" and "anywhere" give "I don't recognise the place", because the "any day" clear words aren't used for places or doctors.
- "on the way to downtown" isn't recognised, so that `NEAR_PHRASE` entry is dead.
- "near Market Street" still restricts to both Market Street locations, against decision 24 ("near" ranks, it doesn't restrict).
- "mid town" only ranks by distance, while "Midtown" restricts.

Fix: require an exact match for words of 4 letters or fewer, apply the clear words to places, and add these phrases as "must NOT match" tests.

**4. SHOULD FIX: patient lookup reveals who is a patient, and overclaims in its docstring.** VERIFIED. patients.py:99-110.
- `lookup("James Wilson")` returns `need_date_of_birth`, but `lookup("John Doe")` returns `not_found`. Anyone can test a name. The `dob_mismatch` wording ("doesn't match our records for this name") confirms it too.
- Fix: for a caller who says they're returning, always ask for the date of birth first, and give one generic "can't find you" answer.
- The docstring promise "never quietly treated as a new patient" doesn't hold. "Emily Braun" and "James Wilson Jr", each with the correct date of birth, come back `not_found` and become new patients.

**5. SHOULD FIX: still slow at the plan's scale when a wish can't be met.** VERIFIED. Measured on a generated catalog of 500 locations and 2,000 doctors:
- Annual Physical with "Saturday": 1.35 s.
- A date after the 14-day window: 1.24 s.
- No wishes at all: 203 ms.

A wish nobody can meet forces every doctor and location pair (1,520 of them) through all 15 days, so the lazy search saves nothing. Fix: skip days the day filter rules out before working out their times, and reject dates outside the window up front.

**6. SHOULD FIX: `Note(str)` is too clever.** VERIFIED. options.py:61.
- `copy.copy`, `copy.deepcopy`, `pickle` and `dataclasses.asdict(result)` all crash with `TypeError: __new__() missing 'say'`.
- `json.dumps(result.notes)` silently drops `kind`.
- `n.strip()` and `n + "x"` lose `kind`.
- Fix: a frozen dataclass with `kind` and `say`.

**7. SHOULD FIX: the language note isn't always true.** VERIFIED. options.py:349.
- For a new patient, Skin Cancer Screening plus Hindi says "None of the doctors who offer Skin Cancer Screening speaks Hindi". Dr. Wei Sato does, but isn't taking new patients. Same for 2 other visit types.
- The same check also counts a language speaker who has no free times as "doesn't speak it".
- Fix: "None of the doctors available to you…", or give the reason.

**8. SHOULD FIX: "a different doctor" offers the same doctor again.** VERIFIED. `change_choice("doctor", "")` leaves no doctor wish, so the first option is Dr. Daniel Chen at the same 11:00 slot the caller just turned down. Fix: remember the rejected doctor and leave them out.

**9. SHOULD FIX: specialty word matching.** VERIFIED. catalog.py:243-261.
- "physician" becomes Physical Therapy, a dead-end specialty with no doctors.
- The `SPECIALTY_STEM_MIN` comment (line 32) is self-contradictory. "dentist" gives the 4-letter stem "dent", which is allowed and matches Dental.
- "gynecologist" gives nothing, but "gyno" gives OB/GYN.

**10. NIT: past or far-off dates.** VERIFIED. `days=["2026-10-01"]` or `["2026-12-25"]` give "Nothing is open on Thursday 1 October … in the next 14 days". That should be `bad_input`. The wording "Nothing is open on today" is also awkward.

**11. NIT: catalog checks and the fake schedule.** VERIFIED.
- A duplicate doctor id loads silently (51 doctors become 50).
- A missing `languages` key raises a plain `KeyError`.
- A doctor at 8 sites never works at 3 of them. slots.py admits a 5-site limit, but nothing checks it, and a generated 2,000-doctor catalog may break it.

**12. NIT: leftovers and needless cleverness.** JUDGEMENT.
- Unused: `Catalog.location_point`, `Schedule.booked` and `booking_id`.
- rules.py:101 writes rule 5 a second time.
- `_doctor_impossible` fixes its grammar with string `.replace("don't","doesn't")`, and branches on its own message text (`reason.startswith("don't offer")`).
- Match ranks are encoded as `quality*10 + 1`. A tuple would explain itself.
- The `p=p` default arguments in the lambdas are actually needed, because `p` is reused later at options.py:376. That is fragile, and the lambdas without them use a different style.
- `_Times` memoises a shared iterator. It is correct today only because no two lookups for the same pair run at once.

## 4. Test quality

**T1. SHOULD FIX: a vacuous test.** VERIFIED. `test_nothing_open_note_only_when_true_across_the_catalog` asserts only inside `if any(... "Nothing is open")`. For each weekday the note is either a conflict note or nothing, so the assertion never runs.

**T2. SHOULD FIX: the "newest wish wins" tests are shaped to the code.** VERIFIED.
- The location test only uses a *chosen* doctor.
- The language test sets `latest="language"`, a value `change_choice` can never write.
- No test goes from `change_choice` to `find_options` with a doctor the caller only named. That is why finding 1 slipped through.

**T3. SHOULD FIX: no near-miss "should NOT match" tests.** VERIFIED. The only place negatives are "Narnia", blank and "the clinic". There's nothing for "main", "bay", "none" or "physician".

**T4. NIT: gaps that remain.**
- The builder suite has no direct slot tests (lunch, closing time, notice, 45-minute visits). Only the independent suite covers them.
- The "same answer every run" test still runs twice in one process (round-1 T5).
- No test for the time change wiping the days.
- No test of speed at scale.
- The note kinds `doctor_not_found`, `place_unknown` and `no_times` are never asserted.

## 5. What's solid

- **The wish engine at its core:** every round-1 scenario is now correct, including the 35 false "nothing open" notes, and the random sweep found no invalid or silently dropped results.
- **Rules:** really centralised in `visit_type_problems` and `pair_problems`, and `check_booking` uses both.
- **Doctor names:** match quality is labelled honestly (I tried 90 misheard names).
- **Patients:** identity by name plus date of birth.
- **Catalog checks:** coordinates, opening hours and unknown ids are checked when it loads.
- **Booking guards:** `SlotTaken`, and option numbers with the `offered()` guard.
- **Time:** `clinic_now`.
- **Speed:** name search 5 ms, typical searches 10–60 ms at scale.
- **Code hygiene:** pyflakes finds nothing in `clinic/`.

## 6. Likely Prosper questions

1. *"Caller names Dr. Chen up front, then says 'the Midtown one'. What happens?"* No good answer yet (finding 1).
2. *"Caller said Thursday, then 'afternoon please'. Is Thursday kept?"* No (finding 2).
3. *"How do you know every note is true?"* Mostly good, with one language edge (finding 7).
4. *"Does your lookup reveal who is a patient?"* Yes, it does today (finding 4).
5. *"Why 0.8, and does 'the main clinic' match anything?"* The thresholds are explained in comments, but short words match wrongly (finding 3).
6. *"Does it scale to 2,000 doctors?"* Mostly; an impossible day takes about 1.3 s (finding 5).
7. *"Why is a note a string subclass?"* Weak answer: it crashes on copy and pickle (finding 6).
8. *"Where is each rule written?"* Good, apart from one small duplicate.
9. *"What are the `p=p` defaults and the `_Times` class for?"* They can be explained, but simpler code would avoid the question.
10. *"Why does option numbering live in both the card and `find_options`?"* Acceptable, but stable ids, or having the search read the card, would be simpler.
