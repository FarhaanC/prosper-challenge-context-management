# The editor, explained

A walk through the Phase 1 editor (`frontend/` and `backend/editor_api.py`), in plain words, so every part can be explained in the review call. The React ideas are explained the first time they come up.

## The big picture

```
browser: the editor (React)                      the voice agent (one Python program, bot.py)
  ├─ loads the agent, tools, placeholders  ──►  /api/editor/agent, /tools, /placeholders
  ├─ Save  ───────────────────────────────────►  /api/editor/agent (POST): check, then write clinic_agent.json
  ├─ Test call: a frame showing  ─────────────►  /client  (Pipecat's own call page)
  └─ inspector, about once a second  ─────────►  /api/editor/calls/latest  (reads backend/call_logs/)
                                                 every call: reads clinic_agent.json fresh, writes a call log
```

The editor never talks to the AI. It edits a file, and it reads the file the calls write. That's why "save, call, see the change" works: the agent reads the agent file at the start of every call.

## Three React ideas, first

- **A component** is a function that returns what to draw (HTML-like code called JSX). `StagePanel`, `Inspector` and `App` are components. A component can contain other components, like boxes inside boxes.
- **State** (`useState`) is a value React remembers between redraws, such as the agent being edited. Changing it with its setter (`setAgent(...)`) makes React redraw everything that uses it. The rule: **never change state in place; make a new copy.** That's why every edit in `edits.ts` returns a new agent instead of modifying the old one.
- **An effect** (`useEffect`) is code that runs after drawing, when certain values change (the list at the end, e.g. `[agent, positions, selected]`). Effects are for things outside drawing: loading from the server, timers, telling React Flow to re-fit. Returning a function from an effect is the clean-up (stop the timer when the inspector is paused or closed).

**Props** are what a parent hands a child component: `<StagePanel stage={stage} onChange={...} />`. Data flows down as props; changes flow up as calls to functions passed down (`onChange`, `onRename`).

## File by file

### `src/main.tsx`: the starting point
Puts `App` on the page and loads two style sheets (React Flow's and ours). `StrictMode` is a React development check; it changes nothing for users.

### `src/api.ts`: talking to the server
- **Types** describe the shapes of data (TypeScript checks them while building): `Agent`, `Stage`, `Arrow`, `Tool`, the call log's events, the booking card. They match the agent file's format in `backend/agent_builder/schema.py`. The server refuses keys it doesn't know, so the editor never adds its own (box positions are kept in the browser instead).
- **Functions** that fetch from the server: `loadAgent`, `loadTools`, `loadPlaceholders`, `loadLatestCall`, `saveAgent`. Saving returns either `{ok: true}` or `{ok: false, problems: [...]}`.

### `src/edits.ts`: every change the editor can make
Plain functions, no React. Each takes the agent and returns a changed copy:
- `updateStage`: change some fields of one stage. Renaming also updates the arrows pointing at it and the start stage.
- `addStage`: a new stage called `new_stage_1` (or the next free number).
- `deleteStage`: removes the stage only. Arrows into it stay, so Save lists them as problems (decision 74).
- `addArrow`: from dragging one box onto another. The name is made safe for the AI service (`go_to_<stage>`, letters, digits, `_` and `-` only) and unique in the stage (decision 73).
- `toggle`: add or remove a tool name in a list.

### `src/graph.tsx`: turning the agent into boxes and arrows
Nothing here changes the agent; it only describes what to draw.
- `buildNodes`: one box per stage, plus the "Always available" box. Positions come from what the person dragged (remembered in the browser) or a default zig-zag, so an arrow that skips a stage passes beside it, not behind it. The box open in the side panel is the highlighted one.
- `buildEdges`:
  - **solid arrows**: the stage's own `edges` (moves the AI chooses);
  - **dashed arrows**: for every tool in a stage (and the always-available ones), the stages its code can move the call to, from the tool registry's `moves_to`. Tools leading the same way share one arrow, labelled one tool per line.
- `loadPositions` / `savePositions`: box positions in the browser's storage (wrapped in try/catch, because storage can be blocked; then boxes just use their default places).

### `src/Boxes.tsx`: what a box looks like
Two small components: a stage box (name, "start" and "ends call" badges, its tools) and the "Always available" box. The dots (`Handle`) are where arrows attach: in on the left, out on the right. Arrows can't be dragged out of the "Always available" box.

### `src/Panels.tsx`: the side panel
- `StagePanel`, when a stage is selected:
  - **Name**, typed into a draft and applied on Enter or when leaving the field, so the box isn't renamed on every key press. If the name is taken, the field goes back to the real name and the reason shows at the top.
  - A note on stages whose name the tools' code needs (e.g. "booking"): renaming them would break those tools.
  - **Calls start here** and **Ends the call**.
  - **Instructions**: one text box per message, with the list of `{placeholders}` the code fills in.
  - **Tools in this stage**: one tick per tool, with where its code can move the call, its description and its fields. Always-available tools show ticked and fixed.
  - **Arrows out**: name, when to use it, where it goes, remove.
  - **Delete this stage.**
- `AgentPanel`, when nothing is selected: name, AI model (gpt-4o or gpt-4o-mini, decision 75), voice id, persona, always-available tools.

### `src/Inspector.tsx`: the call inspector
- **Polling:** ask the server for the newest call log, wait for the answer, wait a second, ask again. Waiting for each answer means a slow server can't pile up requests. Untick "Live" to stop.
- **Header:** the log file, the current stage (the last stage line), and the AI replies with total tokens in and out. Replies the caller cuts off aren't counted: the AI service sends no figures for a cancelled reply (decision 76).
- **Booking card:** caller, what they want, what's chosen, status, and the options on offer ("Last offered" once the call is booked).
- **Events**, one line each: a stage move (with the instructions the AI was given, one click away), a tool call (what was sent, ok or not done, a short reason or result, and the full reply one click away), what the code said (the read-back, "Are you still there?"), and each AI reply's tokens.
- New lines scroll into view, unless you've scrolled up to read something.

### `src/App.tsx`: the main screen
- **State it holds:** the agent being edited; the agent as last saved (as text, to tell whether there are unsaved changes); the tools and placeholders; which stage is selected; what the last Save said; whether a save is running; whether the call panel is open; box positions; the boxes as React Flow knows them.
- **Loading:** one effect, once, fetches the agent, tools and placeholders together.
- **The canvas:** `ReactFlow` draws the boxes and arrows. We keep the boxes in state and rebuild them from the agent whenever it changes, keeping what React Flow measured about each box (it needs box sizes to draw arrows). Dragging is applied with React Flow's own `applyNodeChanges`; its own idea of "selected" is ignored, because the side panel decides which box is highlighted.
- **Edits:** every change goes through `edit(newAgent)`, which stores the new copy.
- **Save:** sends the agent; on success remembers it as saved ("Saved. The next call uses it."); on problems shows the list until the next Save. The Save button is off while saving or when nothing has changed.
- **Test call:** a panel with Pipecat's call page in a frame (microphone allowed), plus "open in a new tab". If there are unsaved changes, it warns that the call uses the last saved version.
- The view re-fits when a stage is added or removed, or the call panel opens or closes.

### `src/styles.css`
Plain CSS: a column (top bar, problems, canvas with panels, inspector), quiet colours so the structure stands out.

### `backend/editor_api.py`: the server side
- **Load:** returns `clinic_agent.json`.
- **Save:** runs `AgentBuilder.from_dict`, the very checks the voice agent runs at the start of a call; if there are problems (`AgentFileProblems.problems`), returns them with status 422 and writes nothing. Otherwise writes the file **all at once**: to a temporary file, then a swap, so a call starting at that instant reads the old file or the new one, never half. One save at a time; on Windows, if a call is reading the file at that instant, it waits a moment and tries again. The file's own line endings are kept, so an unchanged save changes nothing.
- **Tools:** the registry: name, description, where its code can move the call, its fields.
- **Latest call:** the newest file in `backend/call_logs/` (names start with the date and time), every line as an event (a half-written last line is skipped until the next poll), and the latest booking card with ids turned into names.

### `backend/agent_builder/token_log.py`: tokens per reply
A small step in the voice pipeline, right after the AI service. Pipecat sends a usage note after every AI reply; this step writes one call-log line with the input and output tokens, and passes everything on.

## How to run it

```
cd frontend
npm install        (once)
npm run build      (after any change to frontend/src)
```

Then start the agent as usual and open http://localhost:7860/editor. For working on the editor with live reload: `npm run dev`, then http://localhost:5173/editor/ (the agent must be running too).

## Likely questions

**Why React Flow?** The canvas (drag boxes, draw arrows, zoom) comes ready-made; the plan's budget was about 4 hours.

**Why does the editor not hold its own copy of the rules for a valid agent?** One set of checks, in the backend, used by both the editor and the voice agent. The editor can't save something a call would refuse, and the rules can't drift apart.

**Why are some arrows dashed?** They aren't choices the AI makes: a tool's code decides, from the booking card, whether to stay or move (decision 49). The editor reads where each tool *can* move from the tool registry, so the picture always matches the code.

**Why poll once a second, not push?** Simple and robust for a demo (the plan's choice). The call log is a small file; reading it every second costs nothing. Pushing (a socket) would be the next step for many calls at once.

**What doesn't it do?** No undo or version history, no editing of the catalog, no logins (by plan). Git is the version history.
