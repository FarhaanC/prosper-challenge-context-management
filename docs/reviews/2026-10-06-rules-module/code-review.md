# Independent code review: catalog and rules module (`backend/clinic/`)

| | |
| --- | --- |
| **Date** | Mon 5 Oct 2026, late evening (work planned for Tue 6) |
| **Version reviewed** | Commit `2725eca` ("Add catalog and rules module with builder tests") |
| **Who** | A fresh AI agent that never saw the build conversation, briefed as a senior reviewer looking for bugs and "AI slop". It read the plan, the catalog findings, the build decisions, the code, the data and the builder's own tests. It was told not to read the builder's build log so it would judge the code fresh. |
| **Evidence** | Its probe scripts are in [`probes/`](probes/). They were written against its own copy of the code, so the path at the top of each needs adjusting to rerun them. |
| **What happened next** | See [`triage.md`](triage.md). |

The agent's report follows. It could not write files itself, so the builder session saved it. The only edit: its opening note about scratch folder paths was removed.

---

## 1. Verdict

This is solid at its core but has a few holes, and those holes show up as soon as a caller changes their mind. The structure is good: it's plain Python with no Pipecat in it, the current time is passed in rather than read from the clock, the fake schedule gives the same answer every run, and `check_booking` acts as the final gate. The code also reads cleanly, with no unused imports. All 30 tests pass.

The trouble is in the code that turns a caller's wishes into options (`options.py`). It applies each leftover wish as a strict filter, in a fixed order, and then writes notes as if every doctor had been considered. The result is notes that are simply false, like "Midtown has no doctor for this" when one does, or "nothing open Wednesday for two weeks" when there is. That is the very failure the project is built to prevent ("it sounded right but was wrong"), and it sits right on the demo path (`change_choice`). The forgiving name and place matching also hands back guesses as if they were exact matches.

A demanding reviewer would like the structure and then find these problems within minutes, mainly by asking "what happens when the caller changes the location?" The fixes are small and local.

## 2. Findings (most serious first)

**1. MUST FIX: an old doctor wish blocks a location change, and the agent then gives a false reason.** VERIFIED
`options.py:137-207`, together with `card.py:363-369`. Changing the location saves the old doctor as `preferred_provider_id`. `find_options` filters by doctor *first*, so the location filter only ever looks at that one doctor.
Reproduction: a new patient books a skin check with Dr. Daniel Chen at Richmond, then says "the Midtown one". The result is the note *"Midtown Medical Group has no doctor available for Skin Cancer Screening; these are the closest alternatives"*, and all 3 options are Dr. Chen again, one of them back at Richmond. In fact Dr. Kenji Kim does skin checks at Midtown and takes new patients. The same ordering bug shows up in two more places:
- Doctor wish plus "Spanish": the note says *"None of the available doctors for this speaks Spanish"*, but Kim and Smith both speak it.
- Doctor wish plus "the Mission one": it asks "which Mission?" while offering only Richmond and Downtown, and gives no note that the doctor works at neither.
The plan says the doctor is cleared "if they don't work there". Here the new wish should win.
Fix: work out which wish is the *newest* one (the thing the caller just changed) and treat it as a hard filter. Treat older wishes as soft (use them to rank, never to exclude). Write each note from the full list of valid pairs, not from a list that has already been narrowed.

**2. MUST FIX: a time change pins the doctor and location, which produces a false "nothing open" note.** VERIFIED
`card.py:371-382`, `options.py:209-221`. After a time change, both the old doctor and the old location are kept as strict filters. The fake schedule puts each doctor at one site per weekday, so many of these combinations can never happen.
Reproduction: Dr. Chen at Richmond, then "Wednesday". The result is *"Nothing is open for 'Wednesday' in the next two weeks"*, followed by three Tuesday times. In reality Dr. Chen is at Downtown on Wednesdays, and other dermatologists are free that day.
Fix: the same fix as #1 (the new day wish is hard, the old doctor and location are soft). At the very least, say the true thing: "Dr. Chen isn't at Richmond on Wednesdays".

**3. MUST FIX: patient lookup breaks decision 29 and is loose with identity.** VERIFIED
`patients.py:56`. The two-word check counts words *before* titles are removed, so `"Mr Wilson"` and `"Dr Wilson"` both return James Wilson, together with his Radiology referral. A surname alone was supposed to be refused. The forgiving match also hands out other people's records: "Robert Tyler" gets Robert Taylor's record (with a GI referral), and "Sarah Johnston" gets Sarah Johnson's. A date of birth that is one day off returns `not_found`, so a real returning patient is quietly treated as new and refused referral visits.
Fix: count the name's words after removing titles. For a healthcare company, also require the date of birth whenever the name match isn't exact, and add a `dob_mismatch` status instead of falling through to "new patient".

**4. MUST FIX: place matching misfires on everyday San Francisco phrasing.** VERIFIED
`catalog.py:230-275`.
- `"the Marina District"` is taken as *Mission District*. The options are then ranked from the Mission and read out as "about 1.3 miles from Mission District".
- `"Richmond District"`, `"Sunset District"` and `"Castro District"` all come back unrecognised.
- `"near Mission Street"` is taken as Mission District. This is the exact trap noted in the findings doc (North Beach Specialty Center is on Mission St).
- `also_called: ["The Mission"]` is never used, because "the" is stripped before the comparison.
The cause is a single whole-phrase spelling score with a 0.75 cut-off. "Marina district" and "mission district" share most of their letters.
Fix: strip "district" along with the other filler words. Compare word by word and require the *distinctive* word to match. Add the test cases above.

**5. SHOULD FIX: fuzzy doctor matches are presented as exact matches.** VERIFIED
`catalog.py:215-227`, `fuzzy.py:342-351`. Some examples:
- "Dr. Cohen" returns all 7 Chens
- "Dr. Nixon" returns all 8 Nguyens
- "Dr. Jensen" returns Dr. David Johnson
- "Dr. Kahn" returns both Kims
- "Dr. Martin" returns 3 Martinezes
Nothing in the result says it was a sound-alike, so the agent will say "Dr. Cohen, Internal Medicine…" instead of "I don't have a Dr. Cohen. Did you mean Dr. Chen?". Meanwhile "Dr. Garcia's" (a common speech-to-text output) matches nobody, and "Dr. Hannah Win" doesn't find Nguyen.
Fix: return how good each match was (exact or sounds-like) and make the notes say so. Remove a trailing "'s" from names.

**6. SHOULD FIX: day and time words it doesn't recognise are ignored without a word, or produce false notes.** VERIFIED
`options.py:62-86`.
- `time_of_day="early morning"` or `"lunchtime"` is ignored, and afternoon times are offered with no note.
- `days=["next Thursday"]`, `["this Friday"]` or `["Oct 13"]` give *"Nothing is open for 'next Thursday' in the next two weeks"*. That isn't true: the input simply wasn't understood.
- `"evening"` (15:00 or later) was never in decision 23.
Fix: check the values on the way in. Reject anything outside the agreed formats with "unrecognised day", so the AI can try again. Drop "evening" or add it to the spec.

**7. SHOULD FIX: the same rule is written in several places.** VERIFIED (traced)
The booking rules are written four times:
- `pair_ok` (rules.py:224)
- `check_booking` (rules.py:297-308)
- the reason logic in `can_book_visit_type` (rules.py:253-267)
- `_why_doctors_cant` (options.py:99-116)
Distance is written twice, and the two versions already disagree. `facts.py:455` uses plain degree differences, which ignores that longitude degrees are shorter than latitude degrees this far north. For "Castro", `answer_question` says the closest location is Midtown, while `find_options` ranks Mission District first.
Fix: write one function that returns, per rule, why a booking fails, and use it everywhere. Use `distance_miles` in facts.

**8. SHOULD FIX: bad data is quietly papered over.** VERIFIED
- A location missing from `location_extras.json` silently gets coordinates (0, 0), so it sinks to the bottom of every "near" search. I removed Midtown's entry, and Midtown disappeared from "near Hayes Valley" even though it is *in* Hayes Valley.
- `parse_hours` (slots.py:113) quietly falls back to Mon-Fri 8-17 for anything it can't read ("Monday-Friday", "8am-5pm", a Saturday part).
- Ids in the catalog that point at nothing are never checked when it loads.
- `find_options` and `can_book_visit_type` crash with `KeyError` when given an unknown id, while `check_booking` returns a polite message. The two behave differently.
Fix: check the data when it loads and stop with a clear error. Make every function the tools call handle unknown ids the same way.

**9. SHOULD FIX: it gets slow at the size the plan claims.** VERIFIED (measured)
On a generated catalog of 500 locations and 2,000 doctors, `find_options` takes **0.3 s** with no wishes and **1.5 s** for "Saturday", which falls back and recomputes everything. That eats into the 2.5 s reply budget, and Farhaan's laptop will likely be slower. The reason is that every call rebuilds 15 days of hashed time blocks for *every* valid doctor and location pair (440 of them for a skin check), only to pick 3. `is_open` also rebuilds 15 days just to check one time. Name search takes 0.2 s.
Fix: walk the days in order and stop once there are enough options, or cache the free blocks per doctor, location and day.

**10. SHOULD FIX: there is no time zone.** JUDGEMENT
Every date and time has no time zone attached (slots.py, options.py). If the tool layer calls `datetime.now()` on a laptop in Dubai, "now" is 11 hours ahead of San Francisco. "Today", "tomorrow" and the 2-hour notice rule are then all wrong. Fix: make "now" San Francisco time (`ZoneInfo("America/Los_Angeles")`).

**11. SHOULD FIX: `answer_question` hides duplicate doctors.** VERIFIED
`facts.py:474` keeps only 3 of the 8 Chens, which goes against the plan ("Always return *all* matches for duplicate names"). Fix: return them all with short fields, or list the specialties to choose from.

**12. SHOULD FIX: return shapes are inconsistent, and notes are free text.** JUDGEMENT
Here is what each function hands back:
- `find_options` returns an object with `to_dict()`.
- `can_book_visit_type` returns `Bookability` holding Provider objects, with no dict version.
- `check_booking` returns a bare list of strings.
- `answer_question` returns a dict.
- `lookup` returns its own result type.
Notes mix lines to say aloud with instructions to the AI ("Ask the caller which one"), which contradicts the module docstring. Tests and the tool layer can only tell notes apart by searching the text. Fix: give every note a short code plus a text, for example `{"kind": "ambiguous_place", "say": ...}`, and use one dict shape for everything a tool returns.

**13. SHOULD FIX: option ids are just "1", "2", "3" on every search.** JUDGEMENT
`options.py:257`. After a second `find_options`, "option 2" points at a different appointment, so a stale pick books the wrong slot without any error. Fix: build the id from the doctor, location and start time.

**14. SHOULD FIX: plan items missing or half-built.** VERIFIED (traced)
- `soonest` is stored and shown but never used in the search. With a place given, options are ranked by distance, so "soonest near Downtown" is ignored.
- The rejection "alternatives" from the plan (for example, "a new-patient visit with a family doctor") exist nowhere.
- Bookings live only in memory (`Schedule.booked`). The plan says they are saved to a file, so "no double booking" only holds within one running process. Also, checking and then booking are two separate steps.
- `match_specialty`, `Catalog.policies` and `Provider.display` are never used.

**15. NIT: comments that don't match the code.** VERIFIED
- The table in the `change_choice` docstring (card.py:330-334) says a doctor change keeps the location and a location change keeps the doctor. The code clears both, as decision 26 says.
- The `time_of_day` comment lists morning and afternoon only, but the code also accepts evening.
- The fuzzy module docstring leaves out the "at least 3 letters" condition for sound-alike matches.
- "most important first" (rules.py:220) isn't really true.

**16. NIT: small leftovers.** VERIFIED
- The thresholds (0.5 / 0.6 / 0.7 / 0.75 / 0.8 / 0.85 / 0.9, 0.2 miles, 15:00) have no stated reason.
- "two weeks" is hard-coded in the notes, while `DAYS_AHEAD` is 14 and the code actually looks 15 days ahead.
- The odd one-item tuple test `lid not in (prefs.preferred_location_id,)`.
- `_doctor_list` takes a `catalog` argument it never uses.
- `summary()` prints two "doctor:" lines ("Garcia; Dr. Daniel Chen") when both doctor fields are set, and `find_options` silently ignores the heard name.
- A time change can't clear `time_of_day`.
- `read_back` crashes with `KeyError: ''` on an incomplete card.
- Status and stage names are plain strings.
- Bare `list` and `dict` type hints, while fuzzy.py uses `list[str]`.

## 3. Test quality

**T1. SHOULD FIX: none of the bugs above are caught.** VERIFIED
There's no test for a location change while a doctor was chosen, a time change to a day the doctor isn't at that site, a doctor wish plus a language, or wishes it doesn't recognise. The tests check the order of filters that happens to work, not what the plan asks for.

**T2. SHOULD FIX: `slots.py` has no tests of its own.** VERIFIED
Lunch, closing time, the 2-hour notice, the 14-day limit, rounding a 45-minute visit up to two blocks, and a booking freeing up two blocks are never tested directly. I checked lunch and closing by hand and they're correct, but nothing protects them from future changes. "Now" is always Tuesday at 9 AM. There are no Friday-afternoon or 4:30 PM edge cases.

**T3. SHOULD FIX: only "yes, it matched" cases for fuzzy matching.** VERIFIED
There's no list of names that must *not* match (Cohen, Nixon, Jensen, "Mr Wilson") and no test of the place phrasings in #4. There are no tests of the "several" patient result or of date-of-birth handling.

**T4. SHOULD FIX: the "nothing offered breaks a rule" test checks the code against itself.** JUDGEMENT
`test_every_option_ever_offered_passes_every_rule` is the best test here. But it judges options using `check_booking`, which was written by the same author from the same understanding of the rules, and it only ever uses empty preferences. Write a separate checker in the test, straight from the raw JSON, and run it with doctor, place and day wishes too.

**T5. NIT: weak assertions.** VERIFIED
- Notes are checked by searching their text (`"could mean" in n`, `any("referral" in n)`).
- `test_same_answer_every_run` calls the function twice in one process, so it can't catch run-to-run variation. I checked across 3 hash seeds and the output really is the same every run.
- `conftest.py` has a `sys.path` workaround instead of proper pytest configuration.

## 4. What's solid (keep it)

- Plain Python with no Pipecat in it, and "now" passed in everywhere, so it can be tested and shared by voice and text.
- The repeatable schedule uses sha256, not Python's run-to-run `hash()`. I confirmed the output is identical across runs.
- Lunch, closing time, notice and duration rules: correct for 10, 30, 45 and 60-minute visits.
- `check_booking` as the final gate, with a clear message for each rule. Rule 6 is covered by design.
- Only rule-passing doctor and location pairs reach the AI. The knee MRI correctly has exactly 2 options, and OB/GYN and the dead-end visit types are handled.
- Duplicate names are returned together, and "Mission" and "North" are flagged as ambiguous.
- Catalog records are frozen (can't be changed by accident), lookup tables are built once, and there are no unused imports.

## 5. Questions Prosper will likely ask

1. *"Caller picks Dr. Chen, then says 'the Midtown one'. What happens?"* No good answer yet: it gives a false note (#1).
2. *"Why does a time change keep the doctor and location?"* It's in the plan, but the false "nothing open" note undermines it (#2).
3. *"How do you know you've got the right patient?"* Weak: a surname plus a title, or a near-miss name, is enough (#3).
4. *"What if the speech-to-text hears 'Dr. Cohen'?"* Weak: it says "Dr. Chen" as if that's what was asked (#5).
5. *"Why 0.75 / 0.8 / 0.85?"* No stated reason (#16). Explain what each one is for, or replace them with tested examples.
6. *"Where is each rule written?"* In four places (#7). Expect to be asked about drift.
7. *"Does this really scale to 2,000 doctors?"* Partly: the AI's input stays small, but each search takes 0.3-1.5 s (#9).
8. *"What time zone is 'now'?"* None yet (#10).
9. *"How does the tool layer tell an ambiguous place from no times available?"* Only by searching the note text (#12).
10. *"Why does each doctor work at one site per weekday?"* Good answer: so they can't be double-booked across sites (decision 25). Say it's fake data.
11. *"Why does `can_book_visit_type` ignore free times?"* Fine: it matches the plan's definition. `find_options` then reports when there are no free times.
12. *"Why `evening`? Why not use `soonest`?"* No good answer (#6, #14).
