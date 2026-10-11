# The test plan, as written in the Phase 2 plan (locked 5 Oct; later decisions in docs/decisions.md override parts)

**Layer 2: AI-played callers.**
- About 10 scenarios (cut to 6 on 11 Oct, decision 87). Each is a short goal and persona for a second AI playing the caller, plus an **expected outcome** checked in code against the final booking card (booked the right thing, or correctly refused).
- Each scenario runs **3 times**, and we report the pass rate. (Decision 84: the naive versions run once per scenario because of the budget.)

**Three versions compared** on the same scenarios:
1. **Naive:** the whole catalog pasted into one stage, plus an unchecked "book" tool.
2. **Naive + rules:** the same, but the book tool runs our rule checks and rejects invalid bookings.
3. **Ours.**

Version 2 vs 3 shows what the context management itself adds, beyond "the code checks rules." That answers the "rigged test" objection.

**Measure for each version:** pass rate, input tokens per call, number of AI passes, and the slowest reply.

**Scale:** generate a big fake catalog (about 500 locations and 2,000 doctors) and run *ours* on it. For the naive versions, show the size: more than GPT-4o's 128k limit. Our input size should barely change.

**Running without voice:** the tests drive the same stages and tools with typed text (decision 22: a small loop of our own). **Rule:** all stage and tool logic lives in plain Python, separate from Pipecat, so both voice and text use the same code.

A note from an earlier review (R11, 11 Oct), for the text-mode loop: after choose_option, add the code's read-back (`say_now`) as the agent's turn and skip the second AI pass, as the voice agent does.
