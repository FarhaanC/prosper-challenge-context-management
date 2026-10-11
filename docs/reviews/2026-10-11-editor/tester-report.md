# Tester report: Phase 1 agent editor (commit 9209ca0)

Independent tester. I did not open `backend/tests/` while writing these tests. Expected answers come from the Phase 1 plan, the decisions (45, 49), the raw agent files (`clinic_agent.json`, `example_flow.json`), the raw `data/catalog.json`, the tool table at the top of `call/tools.py`, and the six real call logs. They don't come from what the routes return.

**Where the tests are:** `editor-check/repo-copy/backend/tests_independent/editor/`
- `api/test_editor_api.py`: 62 tests of the server routes and the token step (FastAPI TestClient, temporary copy of the agent file, temporary log folder).
- `browser/test_editor_page.py`, with `browser/conftest.py` and `browser/serve.py`: 29 Playwright (Chromium) tests against the built page (`frontend/dist`). Each test starts its own throwaway server on port 7871 (port 7860 was already in use), using a fresh copy of the agent file and of the real call logs.
- `browser/screenshots/`: the screenshots I looked at (01 to 13).

**How to run**

```
cd repo-copy/backend
PYTHONPATH=<pytest folder> <venv python> -m pytest tests_independent/editor/api -q
cd tests_independent/editor/browser
VENV_PYTHON=<venv python> PYTHONPATH=<pytest folder> python3 -m pytest --confcutdir=. -q
```

The venv didn't have pytest, so I installed it into a side folder (`scratchpad/pydeps`) rather than changing the venv.

**Before testing:** I rebuilt the page from `frontend/src` (`npm ci && npm run build`, which also runs the TypeScript check). It produced exactly the same files as the shipped `frontend/dist` (same file names, which are content hashes), so the build I tested matches the source.

## Totals

| Suite | Passed | Failed |
| --- | --- | --- |
| Server routes and token step (API) | 50 | 12 |
| Browser | 18 | 11 |
| **All** | **68** | **23** |

## What works (passed)

**Loading and saving**
- Loading gives back the agent file exactly, with keys in the same order.
- Editing one stage's instructions and saving writes exactly that change. Nothing else in the file changes, and the next load returns the same thing.
- Saving an unchanged agent leaves the file byte-for-byte the same, as long as the file has the plain line endings git stores.
- Non-English characters (é, curly quotes) save and read back correctly.
- A saved file is accepted by the voice agent's own loader (`AgentBuilder.from_json`, which bot.py runs at the start of every call).
- No temporary file is left behind after a save.
- **A call starting during a save:** one thread kept loading the agent file the way bot.py does while 150 saves ran. Every read got a whole, valid agent (Linux).

**Broken agents.** 24 kinds are each refused with status 422. Each gets a list of one-line problems that names the culprit, and the file is left byte-for-byte untouched with no leftover temp file:
- an arrow to a missing stage
- the start stage deleted
- the start stage pointing at a name that doesn't exist
- an unknown tool in a stage
- an unknown always-available tool
- a stage deleted or renamed that a tool's code moves to
- two stages with one name
- unknown keys on the agent, a stage or an arrow
- an arrow with no "when to use it"
- an unknown placeholder
- a placeholder in the persona
- doubled braces
- a bad history value
- the one-at-a-time setting not set to yes or no
- a tool listed both in a stage and as always available
- a tool listed twice
- no stages at all
- a stage with no name
- instructions that aren't text
- `respond_immediately` not set to yes or no
- a stage with no tools while one-at-a-time is on

When an agent has several problems, all of them are listed at once.

**Tool registry, placeholders and inspector routes**
- The tool route matches the registry: names, descriptions, fields, required fields, and where each tool can move. The moves also match the documented table.
- The placeholders route lists all 7 placeholders.
- Inspector route:
  - With no log folder, or an empty one, it says there's no call.
  - With all six real logs, the newest (`20261010-184339-8e2ba6.jsonl`) wins, with all 13 events in order and the booking card removed from each event. A newer file takes over.
  - A half-written last line is skipped, and the card comes from the last whole line.
  - The card comes from the latest line, not the first.
  - A line added later shows up on the next request.
  - The card from the real log has the right names from the raw catalog: Zoya Chida (new), New Patient Consultation, Dr. Michael Sato, Richmond Care Center, 2026-10-12 13:00, booked, 3 options on offer.
  - Before the caller is known, the card is empty.

**Token lines**
- `TokenLog` writes one `ai_turn` line per usage note, with input, output and cached tokens (cached counts as 0 when missing), and passes every frame on.
- It ignores other measurements (time to first byte, processing time, speech-voice usage).
- A token line written through a call's session comes back through the inspector route with its numbers.

**Browser**
- **Canvas:**
  - Every stage is drawn as a box with its tools, plus the "start" and "ends call" badges and the "Always available" box.
  - Exactly the 7 dashed arrows the registry implies are drawn, with tool names on them: identify→visit_type, identify→end, visit_type→booking, booking→end, and always→visit_type, always→booking, always→end. There are no solid arrows (the real agent has none).
  - On `example_flow.json`, the 3 solid arrows are drawn with their names.
- **Editing and saving:**
  - Save stays off until something changes.
  - Editing a stage's instructions and saving writes the file, and every other key is unchanged, including keys the panel doesn't show (`pre_actions`, `respond_immediately`, `history`, `parallel_tool_calls`).
  - Editing the persona saves.
  - Editing an arrow's "when to use it" keeps its `properties` and `required` exactly.
  - Renaming a stage moves the arrows into it and the start setting with it.
- **Broken edits:**
  - Renaming `booking` lists four plain-ish problems and leaves the file untouched.
  - Deleting the start stage is refused and leaves the file untouched.
  - Dragging from one box to another makes an arrow, and Save writes it with only the allowed keys.
- **Test call:** the panel opens the call page in a frame (with microphone allowed). The "open in a new tab" link opens `/client/` in a new tab. With unsaved changes, the panel warns that the call uses the last saved version.
- **Inspector:**
  - It shows the newest real call: stage "end", the card, all 7 tool calls and all 6 stage moves.
  - A token line appended to the newest log appears within 2.5 seconds, with the totals updated ("AI replies: 1 · tokens in 2,345").
  - A newer log file takes over within 2.5 seconds.
  - Unticking "Live" stops the requests, and ticking it starts them again.
  - With no logs it says "no calls yet" without errors.

## What failed

### Server routes (12 failures)

1. **Problems use the file's internal words, not the editor's** (5 tests). The plan says errors come back "in plain words", but the messages say "node", "edge", "initial_node" and "global_tools". Examples:
   - "Edge 'go_on' in node 'identify' targets unknown node 'nowhere'."
   - "initial_node 'identify' is not a defined node."
   - "Tool 'start_booking' can move to stage 'end', which isn't a node."
   - "Two nodes are called 'booking'."
   - "Node 'booking': unknown key 'tool'."
   The editor itself calls these stages, arrows and tools.
2. **A tools list containing a list** (`"tools": [["choose_option"]]`) is refused, which is correct. But the message is Python's own: "The agent file is malformed: unhashable type: 'list'".
3. **A body that isn't an object** (e.g. a JSON list) gets FastAPI's own `{"detail": [...]}` answer, not `{"ok": false, "problems": [...]}`. The page treats every 422 as the second shape. The page never sends such a body, so a person can't hit this.
4. **Arrow names the AI service can't use are saved.** These four tests go beyond the plan's list. The save (and the voice agent's loader) accept:
   - an arrow name with a space (`go_to_new stage 1`)
   - an empty arrow name
   - two arrows with the same name in one stage
   - an arrow named like a registry tool (`hand_off`)
   OpenAI's documented rule is that function names use only letters, digits, `_` and `-` (up to 64 characters). So these would likely fail at call time. That part is unverified: there were no API keys to run a real call.
5. **Windows line endings are lost on this Linux machine** (1 test, environment note). Every file I was given has Windows line endings, including the call logs, which aren't in git, so they were written on the owner's machine. On Linux, saving an unchanged copy of that file rewrites every line ending. On Windows, Python writes Windows line endings, so the file would most likely stay the same. Unverified on Windows. It isn't a defect where the owner works.

### Browser (11 failures)

6. **Selecting a stage that has no `task_messages` key blanks the whole page.** The error is "Cannot read properties of undefined (reading 'length')", and unsaved edits are lost (screenshot 07). The agent format makes `task_messages` optional, and the loader accepts the file.
7. **Deleting a stage silently deletes the arrows into it.** Deleting `offer_times` in `example_flow.json` removed collect_details' arrow `record_details`, with its collected fields. No message was shown, and Save went through (screenshot 12). The plan says Save catches arrows to missing stages.
8. **An arrow dragged to a stage named with a space is saved as `go_to_wrap up`** (see 4; screenshot 10).
9. **The problem list disappears at the first change.** After a refused save, the "Not saved. Fix these first" list vanishes as soon as the person makes the first fix, while the other problems are still there.
10. **Renaming a stage to a name that's already taken is stopped, but the Name field keeps showing the taken name** ("end") while the stage is still "booking".
11. **"+ Stage" puts the new box off screen.** It lands at x≈1256 on a 1200-wide canvas, so the person sees no new box; only the side panel changes (screenshot 06).
12. **The highlighted box doesn't match the side panel** (2 tests):
    - After a rename, no box is highlighted.
    - After "+ Stage", the previously clicked box stays highlighted while the panel shows the new stage.
13. **The inspector doesn't show why a tool was refused.** A refused `choose_visit_type` (`{"ok": false, "reasons": ["This visit needs a referral."]}`) shows only "→ not done". The same happens for `confirm_booking`'s `problems` and `turn_down_doctors`' `which_one`.
14. **The inspector stacks up requests on a slow server.** With answers taking 3 seconds, 6 requests were waiting at once (6 is the browser's own limit per server).
15. **Making a stage's tool always available traps the person.** Save then refuses ("Tool 'choose_option' is in node 'booking' and in global_tools; list it once."), but in the booking stage that tool's tick is greyed out, so it can't be removed there (screenshot 13).

## Seen in the screenshots, not tested by an assertion

- **Some arrows are hidden behind boxes.** All stages start in one row, so an arrow between boxes that aren't next to each other runs behind the boxes in between:
  - The dashed identify→end arrow (start_booking handing to staff) runs behind visit_type and booking, and its label hides under the `choose_visit_type` label (the small "· · ·" box in screenshot 01).
  - A newly dragged identify→booking arrow is invisible behind visit_type (screenshot 05).
  - The always→end `hand_off` arrow ends behind the booking box.
- **The legend covers the bottom of the "Always available" box.** With the problems banner open or a longer tool list, its last tools are hidden (screenshots 03, 13).
- **Opening the test call panel doesn't re-fit the canvas.** The canvas shrinks and the "end" box is cut off (screenshot 08).
- **After a booking, the card still lists the three options that were on offer** (screenshot 09).
- **No real call log has token lines yet.** All six were written before `TokenLog` existed, so the inspector shows "AI replies: 0". The token step has only been checked in isolation and against Pipecat's source, not in a live call.
