# Prosper Challenge — Context Management

Voice AI for healthcare scheduling. An agent is a **graph of nodes** (Pipecat Flows), defined declaratively as JSON and compiled into a runnable voice pipeline.

- **Phase 1** — a UI to edit the node graph and place a test call.
- **Phase 2** — a context-management approach so a scheduling agent can reliably and cost-effectively navigate a large catalog of locations, doctors, and appointment types.

```
browser mic  ->  ElevenLabs STT  ->  OpenAI LLM  ->  ElevenLabs TTS  ->  browser
```

Pipecat's dev runner ships a **prebuilt browser client**, which the editor uses for test calls.

## The editor (Phase 1)

Build it once (needs Node.js 18+), from the repo root:

```bash
cd frontend
npm install
npm run build
```

Then start the agent as below and open **http://localhost:7860/editor**. The agent serves the editor itself, next to the call page, so there's only one thing to run. Edit a stage's instructions, **Save** (the agent file is checked first, and nothing is saved if it has problems), press **Test call**, and watch the call in the inspector at the bottom: the stage, the booking card, every tool call, and the tokens each AI reply used. The agent reads the agent file at the start of every call, so a saved change is live on the next call.

To work on the editor itself, `npm run dev` serves it on http://localhost:5173/editor/ with live reload; it talks to the running agent on port 7860.

## Quickstart

Requires **Python 3.11+**. Run from the repo root:

```bash
make install
make run
```

Open the URL it prints (default `http://localhost:7860/client`), click **Connect**, allow mic access, and talk to the agent. `Ctrl+C` to stop. (`make help` lists all targets.)\
\
Remember to update the `.env` file accordingly.

**On Windows, without `make`** (from the repo root, PowerShell):

```powershell
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt -r backend\requirements-dev.txt
backend\.venv\Scripts\python.exe backend\bot.py
```

- Install the requirements first: they include `tzdata`, without which Windows Python can't tell San Francisco time and the agent stops at the first call.
- To keep a copy of the console output (useful for checking a call afterwards), set `$env:PYTHONUTF8 = "1"` first, then add `2>&1 | Tee-Object -FilePath backend\call_logs\console.txt`. Without that setting, writing Pipecat's start-up emoji to a file crashes the agent.
- Tests: `cd backend`, then `.venv\Scripts\python.exe -m pytest -q`.

## Layout

| Path | Responsibility |
| --- | --- |
| `backend/bot.py` | The voice pipeline (WebRTC + ElevenLabs STT/TTS + OpenAI LLM). Loads an agent JSON via `AgentBuilder` and runs it. No graph logic lives here. |
| `backend/agent_builder/` | All agent-building code, and everything else that touches Pipecat. `schema.py` = the declarative `AgentConfig` / `Node` / `Edge` contract; `builder.py` = `AgentBuilder`, which loads + validates the JSON and compiles it into a Pipecat Flows graph; `call_watch.py` = the silence check-in, hang-up and 10-minute cap; `token_log.py` = tokens per AI reply into the call log. |
| `backend/editor_api.py` | The editor's server routes (load / check and save the agent, the tool registry, the newest call log), added to the agent's own web server. |
| `frontend/` | The editor (React + TypeScript + React Flow): canvas, side panel, save, test call, call inspector. Built into `frontend/dist` (not committed). |
| `backend/clinic_agent.json` | The clinic scheduler **as data**: 3 stages (identify → visit type → who/where/when + confirm) plus an end stage, each stage's tools, the always-available tools, and instructions with `{placeholders}` filled from the booking card at each stage move. This is what `bot.py` runs. |
| `backend/call/` | The tools the AI calls and each call's working state, in plain Python with no Pipecat: `tools.py` (tools, their descriptions for the AI, the tool registry), `session.py` (booking card, options on offer, placeholders, call log, saved bookings), `silence.py` (the rules for silence and the 10-minute cap). |
| `backend/clinic/` | The catalog, the 6 booking rules, fake patients and open times, the booking card, and the search that only offers valid options. Plain Python, no voice code. See its `__init__.py`. |
| `backend/example_flow.json` | The starter example agent, kept as it was. |
| `backend/data/catalog.json` | A deliberately large, deliberately messy clinic catalog (locations, providers, appointment types, booking rules). See [`backend/data/README.md`](backend/data/README.md). |
| `backend/bookings.jsonl`, `backend/call_logs/` | Created when the agent runs (not committed): one line per saved booking, reloaded at start-up; one log file per call, a line per stage move and tool call. |
| `backend/tests/`, `backend/tests_independent/` | The builder's tests, and tests written by independent agents that never saw the build. Run both from `backend/` with `python -m pytest`. |
| `INTERFACE.md` | The tool interface sheet given to the independent tester (names, fields, exactly what the AI is shown). |
| `docs/` | How the work was done: `process.md`, `decisions.md`, `build-log.md`, `reviews/`, `defence-notes.md`. |

To run a different agent, point `AGENT_FLOW` in `bot.py` at another JSON file.