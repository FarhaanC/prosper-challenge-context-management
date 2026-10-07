# Build log

What was built, in order, and what each check found. The decisions are in [`decisions.md`](decisions.md); the process every step follows is in [`process.md`](process.md).

---

## Step 1: the catalog and rules module (`backend/clinic/`), version 0.1.0

**Planned for Tue 6 Oct; built Mon 5 Oct (late); reviewed Tue 6 – Wed 7 Oct.**

### What it is

The module is plain Python with no voice code, so the voice agent and the typed test runs call exactly the same code. It holds four things:

- the clinic catalog;
- the six booking rules;
- a small "booking card" for each call;
- a search that offers the AI only options that already pass every rule.

| File | What it does, in plain words |
| --- | --- |
| `catalog.py` | Loads the given catalog unchanged, plus our fake map data, and checks both. It lists every problem at once if anything is wrong. It answers small questions: the 21 specialties, the visit types in one, every doctor matching a heard name (with how close the match is), and which of our places a place name means. |
| `fuzzy.py` | Forgiving name matching for misheard names (spelling and "sounds alike"), using Python's standard library only. Also the two fixed word lists the code reads: "no preference" words and words no name has. |
| `patients.py` | 6 fake returning patients, and the step-by-step identity check: name and date of birth, the same reply for every miss, spelling as the third try, then an offer to register as new or speak to staff. |
| `slots.py` | Fake open times that are the same every run: 2 weeks ahead, 30-minute blocks, lunch blocked, San Francisco time. A booking can't take a time twice. |
| `rules.py` | "Can this caller book this visit type?" with plain reasons, and the final full check before saving. Each rule is written once. |
| `options.py` | Up to 3 valid options (doctor + location + time). Each wish the caller has is applied only if something survives it. Anything that can't be met becomes a short note, and every note is checked against all valid options, so it's true. |
| `card.py` | The booking card. Changing one choice clears what depended on it. Doctors can be turned down. There's a summary pasted into each stage's instructions, and a read-back built from the card, never from the AI's memory. |
| `facts.py` | `answer_question`: small facts about a location, doctor or visit type. |

**The rule for what comes in from the AI** is written at the top of `clinic/__init__.py`, and it was settled by the reviews below:
- Names (doctors, places, languages) are matched forgivingly against our own records.
- Two fixed word lists are read: "no preference" words, which count as empty, and words no name has, like "not", which are refused.
- Everything else is a plain instruction. Anything else is refused with a note saying how to send it. Nothing is guessed.

### The build (commit `2725eca`)

The build came with 30 of the builder's own tests. They covered:
- the Garcia skin check;
- the knee MRI;
- OB/GYN for new patients;
- duplicate names;
- "every option ever offered passes the full rule check", across all 82 visit types.

### The independent checks

Each round used **fresh** AI agents that never saw the build conversation:
- an independent tester, writing tests from the plan and the raw data only;
- an independent reviewer, looking for bugs and "AI slop".

From round 4, one agent did both jobs, because the remaining work was targeted. Each round's report is saved word for word in [`reviews/2026-10-06-rules-module/`](reviews/2026-10-06-rules-module/), and [`triage.md`](reviews/2026-10-06-rules-module/triage.md) records a decision on every finding.

| Round | Version checked | Tests at the end of the check | What it found (headline) | What changed |
| --- | --- | --- | --- | --- |
| 1 | `2725eca` (build) | 296 independent: 271 pass, 25 fail | Old wishes blocked new ones and gave **false notes**. Patient identity too loose ("Mr. Wilson" found James Wilson). Places misread. Slow at 2,000 doctors. | 17 fixes. Farhaan decided: newest wish wins; name + date of birth; "the Mission" → ask. Builder tests 30 → 100. |
| 2 | `d4983c2` | 632 independent: 601 pass, 31 fail | Edge cases in wish order, places, identity privacy, notes as free text. | Farhaan decided: notes are kind + sentence; spelling as the third identity try. Builder tests → 133. |
| 3 | `e94e6d6` | 1,032 independent: 1,014 pass, 18 fail | "Someone else, please" half built; doctor words guessed wrong ("podiatrist" → Pediatrics); everyday time phrases refused. | Fixed. Builder tests → 161. |
| 4 | `f4595f7` | 1,412 in all: 1,396 pass, 16 fail | "Someone else" **still** produced false sentences: the code was reading the caller's words. Notes named doctors who couldn't help. Data-check holes. | **Farhaan decided: the AI gives a clear instruction** (`turn_down_doctors`); the code stops reading phrases. Builder tests → 198. |
| 5 | `395cb9f` | 1,724 in all: 1,700 pass, 24 fail | A **crash** caused by the round-4 fix; "not Dr. Chen" passed as a name still became a wish *for* Dr. Chen; times still read as phrases. | **Farhaan decided: days and times are plain fields** (back to decision 23). Sentences passed as names are refused. Builder tests → 224. |
| 6 | `18af256` | 2,186 in all: 2,182 pass, 4 fail | The claim "the code reads no sentences" was untrue for place phrases ("near…", "the X one"); two-word languages guessed. | **Farhaan decided: "near" is a yes/no.** Builder tests → 256. |
| 7 | `37c5b8a` | 3,104 in all: 3,082 pass, 22 fail | Leftover place words still read phrases ("Midtown office"); same-name doctors not told apart in two lists. | Fixed. Then 8 tests the builder thought wrong went to a **fresh verifier**: it ruled 6 were real code bugs (the builder had been wrong) and 2 were test bugs (fixed by a fresh tester). Builder tests → 276. |

**Final state (code as of commit `e265175`; tag `v0.1.0` on the record commit after it):** 3,124 tests, all passing:
- 276 builder tests;
- 2,848 independent tests.

pyflakes (a Python code checker) finds nothing in either the code or the tests.

**Speed** on a generated catalog of 500 locations and 2,000 doctors, roughly the plan's scale test:
- a search takes about 0.2–0.6 s;
- loading the catalog takes 0.03 s;
- on the real catalog a search takes under 10 ms.

### What the rounds taught us (for the write-up)

1. **Independent checking works, and the builder's own tests miss things.** Round 1's tester and reviewer independently found the same false-note bug, which 30 builder tests had passed. In round 7, the verifier overruled the builder.
2. **Drift is real.** Decision 23 said days and times would be plain fields. Under pressure to accept everyday phrases (round 3), the code started reading sentences, and every new phrase brought a new bug (rounds 2–5). Going back to the principle (rounds 4–7) removed that whole family of bugs instead of patching them one by one.
3. **"Expected failures" have to be proved, not claimed.** After each spec change, a throwaway adapter played the AI's part and the testers' unchanged tests were rerun. That proved the remaining failures came only from agreed changes. It caught two builder slips:
   - a lost `to_dict()` in round 2;
   - a "bare street" rule in round 6 that would have read "the main one" as Main Street.

   The round-7 checker caught a third: a stale failure count in the round-6 triage (204, really 192).
4. **Every note must be true, so every note is checked against the whole catalog.** That's how wrong names in notes were found (rounds 4–5): thousands of combinations, not a few examples.

### Not done in this step (belongs to the next)

- The tool functions the voice agent calls (`start_booking`, `list_visit_types`, `choose_visit_type`, `find_options`, `choose_option`, `confirm_booking`, `change_choice`, `turn_down_doctors`, `answer_question`), and saving bookings to a file (add it to `.gitignore`). The module already has all the logic they need.
- The tool descriptions must tell the AI exactly what to send. For example: one weekday per day entry; "morning" or "afternoon"; a place name plus near yes/no; a doctor's name, never "someone else" (use `turn_down_doctors`).
