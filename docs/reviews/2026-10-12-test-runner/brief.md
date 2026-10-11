# The brief given to the reviewer (12 Oct)

One fresh agent, as tester and reviewer (process rule P5). It was given a copy of the repo without `backend/.env`, the call logs, the bookings file, the earlier independent tests or the build log. It was told not to call OpenAI (no key, no network). The brief, word for word except for the paths (shortened here):

---

You are an independent tester and reviewer for a take-home project. You did not write any of this code and you have not seen the conversation that produced it. Your job is to find real problems, not to agree. The code's author will read your report; a finding they dismiss goes to someone else, so be concrete and show evidence.

**The project, in brief.** A voice AI agent books healthcare appointments. "Our" agent runs as stages (identify → visit type → booking → end), defined in `backend/clinic_agent.json`, with tools in plain Python (`backend/call/`, rules and catalog in `backend/clinic/`). The voice agent runs on Pipecat Flows via `backend/agent_builder/builder.py`. A new folder, `backend/evals/`, is a TEST RUNNER: a typed (text-only) loop where an AI plays the caller, compared across versions of the agent, with a $7 OpenAI spending stop. Its headline numbers (pass rate, bad bookings, tokens, AI passes, slowest reply) will be shown to the employer, so it must be fair and correct.

**What you have.**
- `backend/evals/` (the runner under review) and `backend/tests/test_builder_evals.py` (its author's tests, which use a pretend scripted AI).
- `backend/call/`, `backend/clinic/`, `backend/agent_builder/`, `backend/clinic_agent.json`, `backend/data/`.
- `docs/decisions.md` (16, 20, 22, 50, 66, 71, 84-88, P1-P5), `docs/process.md`, the test plan, and `INTERFACE.md`.
- Pipecat Flows' real source (`manager.py`, `actions.py`, version 1.4.0).

**Part 1, first, before opening `backend/evals/`.** Work out the expected outcome for each of the six callers from the raw catalog, the fake patients, the map data and the policies only. Write them down, then compare with `scenarios.py`.

**Part 2: review the runner.**
- A: does the typed loop copy the voice agent?
- B: is the comparison fair?
- C: is the scoring right?
- D: is the $7 stop safe?
- E: the scale test.
- F: the author's tests.
- G: the AI-slop checklist.
- H: Windows.

**Your report.** In plain English, with numbered findings, each with a severity, the evidence and a suggested fix. Then what was checked and found fine. Tests you wrote go in a separate folder, and the author's files are not to be edited.
