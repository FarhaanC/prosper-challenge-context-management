"""The typed test runs: AI-played callers against three versions of the agent.

Decision 22: a small loop of our own, not a text-only Pipecat pipeline. It uses the
same agent file (clinic_agent.json), the same stage instructions and the same tool
code (call/) as the voice agent, and copies what Pipecat Flows does in a call:

- the persona is the AI's system instruction; each stage adds its own instructions;
- the code says the greeting, and the AI waits for the caller;
- one tool call at a time; after a tool that stays in the stage, a second AI pass;
- a stage move wipes the conversation (history "reset") and the new stage's AI pass runs;
- after choose_option the code says the read-back (say_now) as the agent's turn,
  with no second AI pass, and waits for the caller (decision 66; review R11).

    budget.py        prices, and the spending record with the $7 stop (decision 84)
    ai.py            one OpenAI request, timed, with rate-limit waits not counted
    agents.py        the versions: ours (stages) and naive (with or without rule checks)
    caller.py        the AI that plays the caller (decision 85: gpt-4o-mini)
    scenarios.py     the six scenarios and their expected outcomes (decision 87)
    scoring.py       pass or fail, checked by code against what was saved
    conversation.py  one call: caller and agent taking turns
    run.py           the command: plan, smoke, round1, round2, round3
    results.py       the results tables and readable transcripts

Run from the backend folder: python -m evals.run plan
"""
