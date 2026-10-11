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

---

## Step 2: the stages and tools in the voice agent, version 0.2.0

**Planned for Wed 7 Oct; built and checked Thu 8 Oct** (a day late: the rules module's review rounds used Wed 7).

**Done when:** a real voice call books correctly and catches the Garcia mistake. ✅ Farhaan's calls on Thu 8 Oct, the last at 23:07–23:11 Dubai time:
- **The skin check with "Dr. Garcia":** the agent said *"Unfortunately, Dr. Garcia doesn't offer Skin Cancer Screenings"*, offered three dermatologists, moved to tomorrow when asked, read back and booked.
- **James Wilson's knee MRI near Downtown:** found from his spoken date of birth; offered only the two doctors who can do it, nearest first; read back and booked.

### What it is

The voice agent now runs the plan's three stages and an end stage. The AI holds a small booking card, the code holds the catalog, and every move between stages is decided by code.

| Part | What it does, in plain words |
| --- | --- |
| `backend/call/tools.py` | The 9 tools the AI calls, in plain Python with no Pipecat. Each takes the values the AI sent, refuses anything that isn't a plain value (saying how to send it), calls the clinic module, and says whether to stay or move stage. The tool registry holds what the AI is shown for each tool, and the stages each can move to. |
| `backend/call/session.py` | One call's state: the booking card, the options on offer, the stage, what just happened, and the goodbye. It fills the `{placeholders}` in each stage's instructions at the moment of the move. It writes a call log (one line per stage move and tool call), and saves bookings to `backend/bookings.jsonl`, reloaded at start-up so a booked time is never offered again. |
| `backend/clinic_agent.json` | The agent as data: the persona; the identify, visit type, booking and end stages; each stage's tools; the always-available tools (answer_question, change_choice, turn_down_doctors, hand_off); history wiped on every move; one tool call at a time; a greeting spoken by the code. |
| `backend/agent_builder/` | Turns the agent file into Pipecat Flows nodes. It checks the file at load and lists every problem at once: unknown keys, wrong types, unknown tools, placeholder typos, stages a tool can move to that don't exist. Each tool is wrapped so that a "move" from the tool's code becomes a Pipecat stage move with freshly filled instructions. |
| `backend/bot.py` | Runs `clinic_agent.json`. It gives each call its own session, sends one tool call at a time to the AI service, and sets speech-to-text to English. |

### The build and the checks

| Version | What | Tests at the end |
| --- | --- | --- |
| `349b652` | **Build.** The tools, session, agent file and wiring, with 43 builder tests. | 3,167 pass |
| `fd6da1a` | **Round 1** (decision 44): a fresh tester (296 tests, written without reading the code) and a fresh reviewer (15 findings, 2 high), working separately. | 272 of 296 new tests pass (24 fail, 10 causes); all 2,848 older ones pass |
| `25c3f91` | **Fixes.** Farhaan decided 50–54. Every finding has a decision in `triage.md`. The remaining failures were proved to come only from agreed changes, using a throwaway adapter. | Builder 78; 6 tester failures, all from agreed changes |
| `90d63c1` | **Round 2.** One fresh agent: first as tester (brought the tests up to the new spec without reading the code, plus 336 new ones), then as reviewer (13 findings, none high). | 3,480 independent, all pass |
| `44e6317` | **Fixes.** All 13; decisions 56–57. | 3,855 pass |
| `41ee0e7` | **After the first voice call** (decisions 58–60): a code-spoken greeting, names spelled back, nothing promised before the options. | 3,858 pass |
| `50d96ca` | **After the second voice call** (decisions 61–63): speech-to-text set to English, exact days sent as dates, stage 1 passes doctor names on unchecked. | **3,861 pass** (381 builder, 3,480 independent) |

### What the checks found, in short

**Round 1:**
- **The AI was never told the year,** so a date like "the 15th" could come back as "15 October is outside 6–20 October".
- **The goodbye could end in silence:** Pipecat offers the always-available tools even in the last stage, and a tool call there is cut off by the hang-up.
- **"Friday afternoon at Midtown" lost its second half,** because one call could only carry one change and the stage move wipes the conversation.
- **A finished call could be reopened.**
- **Other gaps:** language values slipped through, the bookings file used the computer's clock, and agent-file typos loaded silently.

**Round 2:** every round-1 fix held. The new features brought new ways for something the caller said to be lost:
- an early "not Dr. Kim" wiped the doctor the caller *did* want;
- a change of visit wiped early turn-downs;
- "as soon as possible" on its own overturned a newer place choice.

There was also one real hole: choosing a visit type a second time could save a visit the caller never heard read back.

### What the voice calls taught us (things no test could show)

| Call | What happened | Fix |
| --- | --- | --- |
| 1 | **6 s of silence** before the greeting, 3.7 s of it the AI writing a greeting. | The code speaks a fixed greeting the instant the call connects (58). It now arrives in about 1.3 s. |
| 1 | **"Farhaan" saved as "Farhan".** Speech has no spelling. | New patients' names are spelled back (59). |
| 1 | **"I'll register you for that skin check with Dr. Garcia"** (a false promise), and an extra "any preferences?" question let Dr. Chen replace Dr. Garcia before the warning could come. | Nothing is promised before the options; no preference questions in stage 2 (60). |
| 2 | **A name transcribed in Russian.** | Speech-to-text set to English (61). |
| 2 | **"Tomorrow" sent as "Friday"** (meaning any Friday), so next week was offered. | Particular days are sent as dates (62). |
| 2 | **Stage 1 asked "which Dr. Garcia?" itself,** so the clear warning never came. | Stage 1 passes doctor names on unchecked; the code checks them against the visit (63). |
| 3 | **Everything above worked.** | — |

### Known, not fixed (for Sat 10, testing day)

- ~~**The first name was still not spelled back once**~~ *(fixed in step 3: the name is now built from the confirmed letters, decisions 77–78)* (only the last name was), so "Farhan" was saved again. The instruction says both. The AI-played callers will show how often this happens before we decide on a stronger fix.
- **After a change of day, the Garcia note is said again.** It's still true, just repetitive.
- **If the AI calls a tool during the goodbye, the call ends without the goodbye** (decision 50, accepted). It didn't happen in any call.
- **Stage 2 can still take an extra AI pass** when the caller says only "an MRI": the visit types have to be looked up. The agent now speaks first ("I'll check…"), so the caller isn't left in silence.
- **The Pipecat Flows package says it's deprecated** in favour of `pipecat.flows`. Ours works; switching is one import line, left for later.

### Lessons

1. **Real calls find a different class of problem.** Thousands of tests checked that the code does what it's told. Three calls showed the AI saying things it shouldn't ("I'll register you with Dr. Garcia"), a 6-second silence, and speech-to-text guessing the wrong language. Neither kind of check replaces the other.
2. **Each fix can open a new hole.** Round 2 found that round 1's features (several changes in one call, turning doctors down anywhere) had each brought a new way to lose the caller's words. A second, shorter round was worth it.
3. **The code catching a mistake isn't enough; the caller has to hear it.** The Garcia check worked in every call. In two of three it was never said, because the conversation took a different path first.
4. **Windows set-up:** the Python here was missing `tzdata`, without which the agent can't tell San Francisco time. And saving the console to a file needs UTF-8, or Pipecat's start-up emoji crashes it. Both are now in the README.

---

## Step 3: silence, the code-spoken read-back, and the editor (Phase 1), version 0.3.0

**Planned for Fri 9 Oct; built Sun 11 Oct** (the schedule had slipped two days; checks kept proportionate, decision P5).

### Part A: decisions 64, 66 and 67

| What | Where | In plain words |
| --- | --- | --- |
| 64: silence and the 10-minute cap | `backend/call/silence.py` (the rules), `backend/agent_builder/call_watch.py` (the Pipecat side), `bot.py` | 20 s of silence after the agent speaks: "Are you still there?". 15 s more: a short goodbye, and the code hangs up. Words from the caller bring back the full 20 s; a noise doesn't. Every call ends at 10 minutes, unless it's already booked or handed off. Each of these is a line in the call log. |
| 66: the code says the read-back | `call/tools.py` (`Outcome.say_now`), `agent_builder/builder.py` | After choose_option, the code says "To confirm: … Would you like me to book it?" and the AI waits for the caller. No AI pass is spent repeating it, and it's word for word every time. (Pipecat Flows only lets a tool skip the AI's next pass by moving stage, so it "moves" to the same stage, keeping the conversation.) |
| 67: "Let me check" | `clinic_agent.json` | The booking stage asks for a short line before searching again. |

**How it was checked**

| Version | What | Tests |
| --- | --- | --- |
| `14dd04e` | **Build**, with 12 builder tests | builder 393; independent 3,479 of 3,480 (the one is decision 66 itself) |
| `95d4da3` | **One fresh reviewer** (Farhaan's choice for these small changes), who checked every claim against Pipecat's real code and ran small simulations. 11 findings, 2 high. | — |
| `1d40cff` | **Fixes** (all agreed; `triage.md`): an interrupted code-spoken line jammed the call (69); a noise switched the silence check off (70); the 10-minute timer outlived the call and wrote false lines; a "yes" to "Are you still there?" could book (71). The tests now drive Pipecat's real timer and a real pipeline, and were shown to fail on the old code. | builder 403; independent as above, the one failure proved (adapter) to be decision 66 |

**Still to do:** Farhaan's voice call to confirm (script in the chat of 11 Oct): talk over the greeting; ask for another day ("Let me check"); pick an option (the code's read-back); stay silent (check-in), answer "Yes" (asked again, not booked); then a silent call (check-in, goodbye, hang-up).

### Part B: the editor

| Part | Where | In plain words |
| --- | --- | --- |
| Server routes | `backend/editor_api.py` | Load the agent; check and save it (the same checks the voice agent runs, so nothing is saved that a call would refuse; written all at once; one save at a time); the tool registry; the newest call log with the booking card in names. Added to the voice agent's own web server (72). |
| Token counts | `backend/agent_builder/token_log.py` | One call-log line per AI reply with the AI service's own input and output token counts (decisions 45, 76). |
| The editor | `frontend/` (React, TypeScript, React Flow) | Stages as boxes; solid arrows are the AI's own moves; dashed arrows are where a tool's code can move the call, read from the tool registry, including a box for the always-available tools. A side panel edits a stage or the agent. Save lists every problem in plain words. Test call opens the call page beside the editor. The inspector reads the newest call log about once a second: stage, booking card, every tool call with a short result, every line the code said, and tokens per AI reply. |

Run it: build once (`cd frontend`, `npm install`, `npm run build`), start the agent, open http://localhost:7860/editor.

**How it was checked**

| Version | What | Tests |
| --- | --- | --- |
| `4fae8c4`, `9209ca0` | **Build**, 11 builder tests; checked in a headless browser (edit, save, refused save, test-call panel, inspector) | builder 414 |
| `a65d14b` | **One round** (Farhaan's choice): one fresh agent, first as tester (91 tests: 62 on the server, 29 in a real browser), then as reviewer (21 findings, 6 medium, none high) | 68 of 91 |
| `c7141ab` | **Fixes: all 21** (Farhaan), decisions 73–75 | builder all pass; the tester's browser tests 29/29; server 62/62 on a Windows checkout |

**What the check found, in short:** a crash on a stage without instructions; arrow names the AI service would refuse; deleting a stage silently dropped arrows; arrows hidden behind boxes; problems written in the file's words (node, edge); refused tool calls showing no reason; and smaller things in selection, renaming, polling and saving on Windows. Two of the tester's tests and two of the reviewer's suggestions disagreed (options after a booking; where a refused rename is shown); each time the reviewer's other suggested fix satisfied both.

**Known, not fixed:** one dashed arrow's label tucks partly under a box in the default layout (boxes can be dragged); no real call has token lines yet (the token step was checked against Pipecat's code and in isolation; the next call will show them).

### Lessons

1. **A fresh reviewer with the library's source beats a confident builder.** The greeting jam (69) had been in the code since decision 58 and three real calls never hit it: nobody happened to talk over the greeting. It took reading Pipecat Flows' action code and a 40-line simulation to find it.
2. **When a tester and a reviewer disagree, look for the fix that satisfies both** before calling a verifier: twice, the reviewer had offered a second option that also matched the tester's expectation.
3. **Working on a Windows checkout from Linux changes line endings.** Files edited from the Linux side lost their Windows line endings in the working copy (git normalises them, so the repo was fine); they were checked out again afterwards.

### Part C: after Sun 11's voice call (decisions 77–80)

**The call** confirmed: talking over the greeting no longer jams the call (69); "Let me check" (67); the code's read-back started 0.7 s after "the first one" (66); the silence check-in and hang-up (64), and in a separate call, "Yes, I'm here" after the check-in made the agent ask its last question again (71). The read-back-then-"Yes" case wasn't reached (the caller answered within 20 s). Tokens per AI reply were logged for the first time: about 1,500–2,400 in, most of it cached by OpenAI.

**It also showed four problems:** speech-to-text misheard the spelled letters (2 minutes, 14 AI replies); the agent read back the right letters but saved "Farhan" anyway; it picked a visit type for a caller who said "any of them"; and it said "Let me proceed with booking" before anything was checked.

| Version | What | Tests |
| --- | --- | --- |
| `39845de` | **Build:** the name built from confirmed letters (77), spelling one name at a time with a check word, no booking promise (80), never choosing the visit for the caller | builder 431; 312 older independent tests fail (their new callers don't spell) |
| — | **One fresh reviewer:** 12 findings (1 high: letters joined by hyphens, as speech-to-text writes them, were saved as written). Before deciding, Farhaan asked for research into how other voice-AI agents capture names, and for the brief to be checked on visit types. | — |
| (this commit) | **Fixes and decisions 78–79:** the stricter letter reader; the three-step spelling with "spelling not confirmed"; our own descriptions of look-alike visit types | builder 454; independent: all 2,848 rules tests pass; voice and editor tests 691 of 694 with the adapter, each of the 3 explained in `docs/reviews/2026-10-11-names-and-visit-types/triage.md` |

**Still to confirm on a call:** a new patient's name saved as spelled, the word-per-letter step, and a "don't mind" visit choice.

**Sun 11, 22:42 call:** the AI sent the confirmed letters as a list and was refused twice; fixed in `2fb50d1` (details in the names-and-visit-types triage).

### Part D: the 22:50 call, and the fixes before tagging 0.3.0 (decisions 81–83)

**The call confirmed everything still open:**
- the name: speech-to-text heard "Perhan Cheetah", the caller spelled it, and "Farhaan Chida" was saved from the confirmed letters (77, 78);
- the visit type: the agent described the two skin visits from our notes and, when the caller said "you advise me, I don't mind", chose the usual one and said it could be changed (79);
- the editor: a line Farhaan added in the editor ("Thanks for waiting") was said on the call, so edit, save, call, see the change works; the inspector was polling throughout (then the line was removed in the editor, before this commit);
- "Let me check" (67), the code's read-back (66), the booking, and the silence check-in (64).

**It showed one real bug and two slips:**
- **25 s of silence after "Yes, that is it."** The console log shows the answer started, then 20 ms later a turn "started" from speech-to-text (a late rough draft: no final text followed), which cancelled it. The turn ended empty after Pipecat's 5 s limit, nothing asked the AI again, and the check-in came 20 s later. Fixed both ways (81): drafts no longer start a turn, and an empty turn that leaves the caller unanswered asks the AI again. This is probably also the "it didn't speak properly" from an earlier call.
- "Thank you, Perhan" before the name was spelled (82).
- "around 11:00 a.m." became "Let me check ... around eleven", then 9:00 and 8:30 were offered without saying searches go by morning or afternoon (83).

| Version | What | Tests |
| --- | --- | --- |
| (this commit) | Decisions 81–83 | builder 469 (12 new: Pipecat's real turn controller shows a draft started a turn with the default rules and doesn't with ours; the safety net with Pipecat's real silence timer and conversation record; the two instruction fixes). Independent: the rules-module tests all pass; with the P3 adapter the voice tests give 630 of 632, the same 2 failures before and after this change (`test_choose_option_handler_stays`, decision 66; a one-word name the adapter itself turns into a spelled name); editor API 59 of 62 (3 inspector tests read the newest real call log on this computer, which is now the 22:50 call, and expect an older one; the same 3 fail without this change; not edited, P2: a note for the next fresh tester). |

**Checks kept proportionate (P5):** no separate review round for 81–83 (Farhaan: "just fix the errors and let's get the version update out"); the next voice call confirms them, and the testing step gets its own independent check.

**Lesson:** the 25 s silence came from a default inside Pipecat, not our code, and only a real call with a real speech service could show it. Reading the console log line by line (not just our call log) found it.
