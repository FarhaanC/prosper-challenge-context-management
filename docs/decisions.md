# Decision log

Every decision that shaped the work, with the reason. Numbers never change once given; a decision that was later changed says so and points to the one that replaced it.

- **1–21:** made while planning (1–5 Oct), before any code.
- **22–30:** made while building the rules module (5–6 Oct).
- **31 onward:** made during the independent review rounds of the rules module (6–7 Oct). These were Farhaan's calls where behaviour changed, or a fresh verifier's ruling where the builder disagreed with a test.

The reviews behind 31 onward are in [`reviews/2026-10-06-rules-module/`](reviews/2026-10-06-rules-module/). The quality process is in [`process.md`](process.md).

---

## Planning (1–5 Oct)

| # | Decision | Why |
| --- | --- | --- |
| 1 | ~~Plan Phase 1 first~~ **Replaced by 5.** | Phase 2 turned out to shape Phase 1 more than expected. |
| 2 | Keep the Phase 1 editor minimal (React Flow). | The brief says polish matters less than judgement. The editor is where time gets wasted. |
| 3 | Booking rules are enforced by normal code, not left for the AI to remember. | The AI asks; the code says yes or no. The baseline call booked an MRI with no referral check, and its saved record didn't match what it said. |
| 4 | Measure, don't just claim: a test set plus a cost comparison. | Turns "I think this is better" into numbers. |
| 5 | Order: run the project, then the rough Phase 2 shape, then lock the format, then build. | The format is what both phases depend on. |
| 6 | The editor is built in React with Claude leading the code; Farhaan owns understanding it. | React is a weaker area, and the brief encourages AI tools. He must be able to explain every part. |
| 7 | ~~The test call runs inside our own editor~~ **Refined by 17.** | The demo needs a live view of what the agent is doing. |
| 8 | Phase 2 approach: graph stages plus small lookup tools, with rules checked in code. | Predictable where errors are costly, flexible where callers are messy. Links both phases into one story. |
| 9 | Each AI pass costs about 1 s; a tool call costs 2 passes; no reply should need more than 2. | Measured on the baseline call, plus a reading of Pipecat's code. |
| 10 | The cut-off-when-hesitating issue is noted, not prioritised. | Voice tuning, not context management. |
| 11 | When the caller changes a choice, re-check everything that depended on it. | Farhaan's catch on the baseline call: switching from a skin check to a knee MRI silently dropped Dr. Garcia. Built as `change_choice`. |
| 12 | Lead the story with "it sounded right, but was wrong". | The baseline agent was smooth but made four booking errors. |
| 13 | Accept all seven fixes from the independent review of the plan. | Each was verified against Pipecat's code or the catalog. |
| 14 | 3 stages (identify → visit type → who/where/when + confirm), plus an end stage. | Fewer moves means less silence. Merging who/where/when matches how callers talk. |
| 15 | Two-level visit-type lookup (specialty first) instead of keyword search. | Keyword search failed everyday requests ("stomach pain", "heart doctor"). What the AI sees stays the same size at any catalog size. |
| 16 | Compare 3 versions: naive, naive + rules, ours. | Version 2 vs 3 isolates what context management adds beyond rule checks, which answers a "rigged test" objection. |
| 17 | The test call uses Pipecat's ready-made call page; a "call inspector" panel in our editor shows the live booking card, tool calls and tokens. | Gets the demo effect without rebuilding the call page in React. |
| 18 | Fake coordinates and neighbourhoods for the 8 locations, in our own file. | The given data can't answer "near Downtown" (addresses contradict names). |
| 19 | Moves use plain "reset" and rebuild the next stage's instructions with the booking card and pre-fetched options; parallel tool calls off. | Keeps the AI's input small and stops a lost stage move. Avoids the slow, deprecated summary option. |
| 20 | Tests: code tests of search and rules, plus about 10 AI-played callers × 3 runs, scored by checking the booking card in code. | Fixed scripts drift when the agent asks questions in a different order. |
| 21 | Submission deadline Mon 12 Oct. | 7 days from 5 Oct, part-time. |

## Building the rules module (5–6 Oct)

| # | Decision | Why |
| --- | --- | --- |
| 22 | **Text mode is our own small loop**, not a text-only Pipecat pipeline. It reuses the same stage definitions and `clinic` code, and copies the 3 Pipecat Flows behaviours that matter: history wiped on a stage move, a second AI pass after every tool call, one tool call at a time. | Pipecat is built around live audio; pushing about 90 typed conversations through it means extra plumbing, slower runs and harder token counting. **Risk:** small differences from Pipecat. **Safeguard:** one shared stage definition; the demo scenarios are also run by voice. |
| 23 | **Day and time wishes are structured fields** (days like "Thursday" or "2026-10-13", plus morning/afternoon), not free text. The AI fills them in. | The AI is good at turning "next Thursday morning" into fields; code that parses spoken dates is brittle. *During review rounds 2–4 the code drifted from this and started reading phrases; rounds 4–7 brought it back and extended the rule (see 37–40).* |
| 24 | ~~"Near X" ranks by distance; "the X one" means only X~~ **Replaced by 39** (near is a yes/no). Still true: a name that fits several locations ("Mission", "North") makes the agent ask. | Guessing between Mission Bay and Mission District is exactly the mistake to avoid. |
| 25 | **Rule 6 is enforced by design.** Every option is doctor + location + time together; the final check refuses a booking with no location; in the fake schedule a doctor is at one location per working day. | The caller can't end up with a doctor but no settled location, and a doctor can't be double-booked across sites. |
| 26 | **When a choice changes, the old doctor and place become wishes, not choices.** The next search honours them if they still fit, and says so plainly if they don't. | Nothing is kept or dropped silently (decision 11). |
| 27 | **"New patient" means new to the clinic group**, not new to that doctor. | The catalog has one flag per doctor and per visit type, and no history of who saw whom. The simplest reading that fits the data; stated as an assumption. |
| 28 | **A referral is stored as a specialty** and covers every referral-needing visit type in it. | The catalog has no referral detail. Simple and explainable. |
| 29 | Booking-card preferences gained `preferred_provider_id` / `preferred_location_id` (for 26) and the structured `days` / `time_of_day` (for 23). | Exact ids avoid re-asking "which Dr. Ramirez?" after the caller only changed the time. |
| 30 | **No new packages** (apart from `tzdata` for time zones on Windows, added in round 1). Matching uses Python's standard library. | Nothing extra to install or break. |

## Review rounds (6–7 Oct)

| # | Decision | Who | Why |
| --- | --- | --- | --- |
| 31 | **The newest wish wins.** Wishes are applied strongest first: the latest change, then other things the caller said (doctor, place, time, language), then choices carried over. A wish is applied only if something survives it. Every note is checked against all valid options, so it's true. | Farhaan, round 1 | Both round-1 reviewers found the old order gave false "nothing available" notes. |
| 32 | **Returning patients give full name and date of birth.** Nothing is looked up without both, and every miss gets the same reply. | Farhaan, round 1 | "Mr. Wilson" found James Wilson, and "Robert Tyler" got Robert Taylor's record. The same reply for every miss means the agent never reveals whether a name exists. |
| 33 | **"The Mission" is ambiguous: the agent asks** (Mission Bay or Mission District). | Farhaan, round 1 | Guessing is the baseline's mistake. |
| 34 | **Fix the smaller spec items too:** specialty words ("dermatologist"), street names, a neighbourhood used as a name. | Farhaan, round 1 | Cheap, and callers say these. |
| 35 | **Notes are plain records:** a kind (e.g. `place_ambiguous`) plus the sentence. | Farhaan, round 2 | The tool layer can react to the kind (ask "which one?") without reading the sentence. |
| 36 | **Identity, step by step:** try again; then the caller spells their last name (third try); then offer to register them as a new patient or put them through to staff. Same name *and* birthday → staff. After 3 unusable answers in a row, the same offer. | Farhaan, rounds 2–3 | People share names and speech-to-text mishears; nobody should be asked forever. |
| 37 | **Turning doctors down is its own clear instruction** (`turn_down_doctors`: given ids, the doctors on offer, or the current doctor). The code no longer reads "someone else" or "not Dr. Chen". | Farhaan, round 4 | Rounds 2–4 kept finding bugs in code that read the caller's sentence. That broke decision 23's principle: the AI understands speech; the code follows instructions. |
| 38 | **Days and times are plain fields only** (back to decision 23): each day is a weekday, "today", "tomorrow" or a date; the time of day is "morning" or "afternoon". Anything else is refused with a note saying how to send it. | Farhaan, round 5 | The code had started reading phrases like "Thursday or Friday, morning please", so "Thursday works" was refused. |
| 39 | **"Near" is a yes/no the AI passes**, next to a place name. | Farhaan, round 6 | The last phrase reading left was spotting "near"-type words. |
| 40 | **The rule for what comes in from the AI**, stated in `clinic/__init__.py`. Names (doctors, places, languages) are matched forgivingly against our own records, because the AI doesn't know them. Two fixed word lists are read: "no preference" words (treated as empty) and words no name has, like "not" (refused). Everything else is a plain instruction, and anything else is refused, never guessed. | Builder, from 37–39; worded after round 7 | One sentence that can be defended, and checked by reading the code. |
| 41 | **A word like "clinic" or "center" in a place name counts only if it's part of that place's own name.** "Sunset Clinic" works; "Chinatown clinic" is not quietly read as "near Chinatown". | Fresh verifier, round 7 (the builder disagreed and lost) | A rule built from all eight names only fit this catalog, and it read phrases. |
| 42 | **Two-word language values are refused unless they're one language name** (or a listed other name like "Mandarin Chinese"). A language we have no record of gets a note listing the languages we do have. | Builder, rounds 5–6 | "Spanish French" or "Chinese" must never be guessed, and every note must be true. |

## How the work is checked (process decisions, 5–6 Oct)

| # | Decision | Why |
| --- | --- | --- |
| P1 | **Tests are never written only by the agent that wrote the code.** A fresh independent tester and a fresh reviewer check each step; the builder's own tests are a separate folder. | Farhaan: tests from the same chat that wrote the code are "a bit foolish". |
| P2 | **The builder never edits an independent test.** Spec changes go to the next fresh tester as a written note. A test the builder thinks is wrong goes to a fresh verifier (or Farhaan), who sees the builder's argument only after forming a view. | The builder can't grade its own work. |
| P3 | **Every review round checks that remaining failures come only from agreed changes.** A throwaway adapter plays the AI's part (e.g. turns old phrases into the new plain fields) and the testers' unchanged tests are rerun. What still fails is listed one by one. | It proves "these failures are expected" instead of claiming it. |
| P4 | **Versioning:** a git commit at every checkpoint (build, each review, each fix), docs kept in the repo, a tag per finished step. Saved locally, copied to a private backup repository (to be set up), and pushed to the public fork only on submission day. | The process has to be explainable to the employer from the history alone. |
