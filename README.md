# Prosper Challenge — Context Management

Voice AI for healthcare scheduling. An agent is a **graph of nodes** (Pipecat Flows), defined declaratively as JSON and compiled into a runnable voice pipeline.

- **Phase 1** — a UI to edit the node graph and place a test call.
- **Phase 2** — a context-management approach so a scheduling agent can reliably and cost-effectively navigate a large catalog of locations, doctors, and appointment types.

```
browser mic  ->  ElevenLabs STT  ->  OpenAI LLM  ->  ElevenLabs TTS  ->  browser
```

Pipecat's dev runner ships a **prebuilt browser client**, so the test-call UI comes for free — no frontend code to write yet.

## Quickstart

Requires **Python 3.11+**. Run from the repo root:

```bash
make install
make run
```

Open the URL it prints (default `http://localhost:7860/client`), click **Connect**, allow mic access, and talk to the agent. `Ctrl+C` to stop. (`make help` lists all targets.)\
\
Remember to update the `.env` file accordingly.

## Layout

| Path | Responsibility |
| --- | --- |
| `backend/bot.py` | The voice pipeline (WebRTC + ElevenLabs STT/TTS + OpenAI LLM). Loads an agent JSON via `AgentBuilder` and runs it. No graph logic lives here. |
| `backend/agent_builder/` | All agent-building code. `schema.py` = the declarative `AgentConfig` / `Node` / `Edge` contract; `builder.py` = `AgentBuilder`, which loads + validates the JSON and compiles it into a Pipecat Flows graph. |
| `backend/clinic_agent.json` | The clinic scheduler **as data**: 3 stages (identify → visit type → who/where/when + confirm) plus an end stage, each stage's tools, the always-available tools, and instructions with `{placeholders}` filled from the booking card at each stage move. This is what `bot.py` runs. |
| `backend/call/` | The tools the AI calls and each call's working state, in plain Python with no Pipecat: `tools.py` (tools, their descriptions for the AI, the tool registry), `session.py` (booking card, options on offer, placeholders, call log, saved bookings). |
| `backend/clinic/` | The catalog, the 6 booking rules, fake patients and open times, the booking card, and the search that only offers valid options. Plain Python, no voice code. See its `__init__.py`. |
| `backend/example_flow.json` | The starter example agent, kept as it was. |
| `backend/data/catalog.json` | A deliberately large, deliberately messy clinic catalog (locations, providers, appointment types, booking rules). See [`backend/data/README.md`](backend/data/README.md). |
| `backend/bookings.jsonl`, `backend/call_logs/` | Created when the agent runs (not committed): one line per saved booking, reloaded at start-up; one log file per call, a line per stage move and tool call. |
| `backend/tests/`, `backend/tests_independent/` | The builder's tests, and tests written by independent agents that never saw the build. Run both from `backend/` with `python -m pytest`. |
| `INTERFACE.md` | The tool interface sheet given to the independent tester (names, fields, exactly what the AI is shown). |
| `docs/` | How the work was done: `process.md`, `decisions.md`, `build-log.md`, `reviews/`, `defence-notes.md`. |

To run a different agent, point `AGENT_FLOW` in `bot.py` at another JSON file.