# How this project is built: the quality process

This take-home was built with heavy AI assistance, which Prosper allows. The risk with AI-written code is that it *looks* finished while hiding mistakes, and that the same AI that wrote it then "checks" it and agrees with itself. This document is the process used to prevent that. Every build step goes through it, and the evidence is kept in this repo.

**The one rule behind everything:** code is never judged only by the thing that wrote it.

---

## The roles

| Role | Who | Sees | Never sees |
| --- | --- | --- | --- |
| **Builder** | The AI session writing the code, steered by Farhaan | Everything | — |
| **Independent tester** | A fresh AI agent, new for each review | The plan, the decisions, the raw data, and the code's function names (to know how to call them) | The build conversation and the builder's tests. It must work out expected answers from the plan and the raw data, not from the code |
| **Independent reviewer** | A fresh AI agent, new for each review | The plan, the decisions, the code and the builder's tests | The build conversation and the builder's own account (build log) |
| **Verifier** | A fresh AI agent, used when the builder disagrees with a finding | The finding, the code, the plan | The builder's argument for dismissing it, until it has formed its own view |
| **Farhaan** | The candidate | Everything | — |

Farhaan decides anything that changes behaviour or the plan, and must be able to explain every part before it's called done.

---

## The checklist for every build step

Each step is one item from the build schedule (for example "catalog and rules module").

1. **Before building:** confirm the step's goal and its "done when" from the schedule. If the work needs a change to the plan, record it as a decision first.
2. **Build.** The builder writes the code and its own quick tests (in `backend/tests/`). All tests pass.
3. **Save a version:** commit "build" with a clear message. The reviews refer to this exact version.
4. **Independent tests:** a fresh tester writes tests from the plan alone (in `backend/tests_independent/`) and reports. The report is saved in `docs/reviews/<date>-<step>/`.
5. **Independent review:** a fresh reviewer checks correctness and AI slop using the checklist below. Its report is saved in the same folder. Steps 4 and 5 run at the same time and don't see each other's work.
6. **Triage:** every finding and failing test gets a decision, recorded in `triage.md` in the review folder:
   - **Fix:** the builder agrees it's a problem.
   - **Won't fix:** with a reason.
   - **Disputed:** the builder thinks it's wrong.
   - **Farhaan decides:** it changes behaviour or the plan.

   **Agreeing with a finding needs no further check. Dismissing one does:** a disputed finding goes to a fresh verifier or to Farhaan. The builder can't wave away criticism of its own code.
7. **Fix**, then rerun **both** test folders. The builder must not edit an independent test to make it pass. If a test is wrong, that's a disputed finding (step 6), and the change is recorded.
8. **Save a version:** commit "review fixes", referring to the triage file.
9. **Understanding check:** Farhaan gets a plain-language walkthrough of what was built and what changed. Likely interviewer questions, with answers, go in `docs/defence-notes.md`. Anything he can't explain gets simplified or explained before moving on.
10. **Update the record:** decision log, build log, changelog, and the status in the project overview. Tag the version.

A step is done only when all ten boxes are ticked.

---

## The "AI slop" checklist (what reviewers look for)

- Comments or docstrings that don't match what the code does.
- Dead code, unused imports, parameters or fields, leftovers.
- The same rule or calculation written in more than one place (they drift apart).
- Over-engineering (layers with one user, settings nobody sets), or the opposite: copy-paste.
- Silent failure: errors swallowed, fallbacks that hide bad data, guesses presented as facts.
- Unexplained magic numbers and thresholds.
- Hacks that fit this catalog or these test cases but won't survive a bigger or different one.
- Inconsistent names, types, return shapes or style across files.
- Fragile text matching (names, places, dates) without tests of things that should *not* match.
- Tests that can't fail, only test the happy path, copy the code's own output as the "expected" answer, or check the code against itself.
- Behaviour the plan never asked for, or plan items quietly missing.
- Slowness at the scale the plan claims.
- Anything the author can't explain in one sentence.

---

## Versions and records

- **Git:** a commit at each checkpoint (build, review, fixes) with a message saying what and why. A tag at the end of each build step (`v0.1.0` for the rules module, `v0.2.0` for the voice stages, and so on).
- **Changelog:** `CHANGELOG.md` lists what changed in each version, in plain words.
- **Where the record lives:**

| File | What it holds |
| --- | --- |
| `docs/process.md` | This document |
| `docs/decisions.md` | Every decision and its reason |
| `docs/build-log.md` | What was built at each step and what was learned |
| `docs/reviews/<date>-<step>/` | The independent test and review reports, the triage, and evidence |
| `docs/defence-notes.md` | Questions Prosper may ask, with honest answers |
| `CHANGELOG.md` | What changed in each version |
| `solution.md` | The final write-up, which links to all of the above |

- **Pushing:** work is saved locally and backed up privately during the week, then pushed to the public fork on submission day. The dates on every saved version show when each step really happened.
- **Never committed:** API keys (`backend/.env`), personal notes.
