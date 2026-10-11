# Reviewer report: Phase 1 agent editor (commit 9209ca0)

I reviewed `backend/editor_api.py`, `backend/agent_builder/token_log.py`, the editor changes in `backend/bot.py`, `frontend/src/*` and `backend/tests/test_builder_editor_api.py`, against `phase1-plan.md` and the "AI slop" checklist in `docs/process.md`. Line numbers refer to each file on its own. Where a finding was confirmed by one of my tests, the test is named.

## Findings

### E1 (medium): Selecting a stage without `task_messages` blanks the whole editor
- **Where:** `frontend/src/Panels.tsx:32` (`stage.task_messages.length`); `frontend/src/api.ts` (the `Stage` type declares `task_messages` as always present).
- **What's wrong:** The agent format makes `task_messages` optional (`schema.py` `Node.from_dict` uses `d.get("task_messages", [])`), and both Save and the loader accept a stage without it. The panel reads `.length` on it anyway. The page has no error boundary, so React removes everything.
- **What the person sees:** They open an agent file written by hand or by the Phase 2 Copilot and click such a stage. The whole page turns blank, and every unsaved change is lost. Confirmed: `test_a_stage_without_instructions_key_can_be_selected` (screenshot 07).
- **Fix:** `const messages = stage.task_messages?.length ? ...`. Make `task_messages` optional in the type, so TypeScript catches the next such read.

### E2 (medium): Save accepts arrow names the AI service can't run (unverified against OpenAI)
- **Where:** `frontend/src/edits.ts:44` (a dragged arrow is named `go_to_${to}`); `Panels.tsx:114` (the "Tool name" field is free text); `schema.py:105-107` and `builder.py` (an arrow name only has to be text).
- **What's wrong:** None of these are refused:
  - a name with a space ("go_to_wrap up", produced automatically when a stage name has a space)
  - an empty name
  - two arrows with one name in a stage (dragging twice to the same box does this)
  - an arrow named like a tool (`hand_off`)
  OpenAI's documented rule is letters, digits, `_` and `-`, up to 64 characters. Two functions with one name register only one handler in Pipecat (`register_function` keys handlers by name), so a duplicate silently runs whichever registered last.
- **What the person sees:** "Saved. The next call uses it." Then, in the test call, the agent goes silent when it reaches that stage (the AI request is refused), or `hand_off` moves the call to a stage instead of handing it to staff.
- **Confirmed:** Save accepts all four (`test_arrow_name_with_a_space_is_refused`, `test_empty_arrow_name_is_refused`, `test_two_arrows_with_one_name_in_a_stage_are_refused`, `test_arrow_named_like_a_tool_is_refused`, and the browser test `test_arrow_from_a_stage_named_with_spaces`). The failure in a real call is unverified: there were no API keys.
- **Fix:**
  - In `AgentBuilder._validate`, check each arrow name against `^[A-Za-z0-9_-]{1,64}$`, unique within its stage, and not a registry tool name. The editor and the loader then refuse it together.
  - Build dragged arrow names from a cleaned-up stage name, and add `_2` when the name is taken.

### E3 (medium): Deleting a stage silently deletes the arrows into it, with their fields
- **Where:** `frontend/src/edits.ts:31-38`. The comment above it (lines 29-30) says "nothing is changed silently".
- **What's wrong:** `deleteStage` filters out every solid arrow that pointed at the deleted stage: name, wording and collected fields (`properties`/`required`). The plan says Save catches "arrows to missing stages" and shows the problem. There is no undo (by plan), so the wording and fields are gone. The comment claims the opposite of what happens to arrows.
- **What the person sees:** They delete `offer_times` in `example_flow.json` and press Save. It saves, and `collect_details` no longer has its `record_details` move, so calls get stuck in that stage. Confirmed: `test_deleting_a_stage_arrows_point_to_is_reported_not_silent` (screenshot 12).
- **Fix:** Leave the arrows in place (the panel already shows "(missing)" for a target that's gone) and let Save report them. Or ask "This also removes 2 arrows into it: OK?". Correct the comment either way.

### E4 (medium): The canvas hides arrows in its default layout
- **Where:** `frontend/src/graph.tsx:24-27`. Every stage without a remembered position goes in one row (`{x: index * 300, y: 0}`).
- **What's wrong:** An arrow between boxes that aren't next to each other runs straight behind the boxes in between:
  - The dashed identify→end arrow (start_booking hands the caller to staff) is hidden behind visit_type and booking, and its label is covered by the `choose_visit_type` label (the small "· · ·" box in screenshot 01).
  - A newly dragged identify→booking arrow is completely invisible (screenshot 05).
  - The always→end `hand_off` arrow ends behind booking.
  The plan's first goal is clarity, and these are exactly the jumps the dashed arrows exist to show.
- **What the person sees:** The canvas suggests stage 1 can only lead to visit_type. They drag an arrow and nothing seems to happen, except "Unsaved changes".
- **Fix:** A simple automatic layout, e.g. alternate the y position, or place stages in a column. Or draw arrows that skip a box with a curved path, like the `smoothstep` edge type with an offset. Re-fit the view when a stage is added (see E9).

### E5 (medium): Problems shown after Save aren't in the editor's words, and don't say what to do
- **Where:** `backend/editor_api.py:39-48` passes the loader's messages through unchanged: `builder.py:79, 81, 91, 96, 111` and `schema.py` ("Node '…': unknown key", "edge #0").
- **What's wrong:** The plan asks for errors "in plain words". The editor calls things stages, arrows, "start" and "always available". The messages say node, edge, `initial_node` and `global_tools`. More importantly, renaming or deleting `visit_type`, `booking` or `end` gives four lines of "Tool 'X' can move to stage 'booking', which isn't a node." Nothing tells the person these three stage names are fixed by the tools' code. The panel gives no hint that these names can't be changed, either.
- **What the person sees:** Screenshot 03. They renamed a stage and get four lines about "nodes", with no hint that the fix is to rename it back. Confirmed: `test_problems_use_the_editors_words` (5 cases).
- **Fix:** Word the loader's messages in stage, arrow and tool words, which suits the Phase 2 Copilot too. Group the moves_to problems: "Stage 'booking' is needed by change_choice, choose_visit_type, confirm_booking and turn_down_doctors (their code moves the call there); keep that name." In the stage panel, mark stages that some tool's `moves_to` names as "name used by code".

### E6 (medium): The inspector doesn't show the result of refused tool calls
- **Where:** `frontend/src/Inspector.tsx:130` (`const detail = e.error ?? result.error ?? result.say ?? ""`).
- **What's wrong:** Refusals from `choose_visit_type` (`reasons`, `alternatives`), `confirm_booking` (`problems`) and `turn_down_doctors` (`which_one`) show only "→ not done". Successful calls show only "ok". So the useful part is never visible: the read-back, the answer to a question, the visit types listed. The plan asks for "each tool call with its short result".
- **What the person sees:** During a test call the caller asks for a visit needing a referral. The inspector says "choose_visit_type … → not done" and nothing about why. Confirmed: `test_inspector_shows_why_a_tool_was_refused`.
- **Fix:** Show a one-line summary of the result. Take the first of `error`, `say`, `reasons`, `problems`, `which_one` or `noted`, otherwise the result without `ok`, shortened to about 120 characters. Put the full result in a `<details>`, as the stage instructions already are.

### E7 (low): The list of problems disappears at the first change
- **Where:** `frontend/src/App.tsx:85-88`. Every edit sets the status back to idle.
- **What's wrong:** After a refused save, the first keystroke or tick hides the whole list, although the other problems are still there.
- **What the person sees:** Three problems listed. They fix the first and can no longer see the other two without pressing Save again. Confirmed: `test_problem_list_stays_while_fixing`.
- **Fix:** Keep the problems shown, maybe greyed with "(from the last Save)", until the next Save.

### E8 (low): Making a stage's tool "always available" can't be undone from the stage
- **Where:** `frontend/src/Panels.tsx:87-95` (`disabled={global}`); `AgentPanel` lets any tool be ticked as always available.
- **What's wrong:** Ticking `choose_option` as always available makes Save refuse ("…is in node 'booking' and in global_tools; list it once"). But in the booking stage that tool's tick is now greyed out, so it can't be removed there.
- **What the person sees:** A message saying to list the tool once, and a stage where it can't be unticked. They have to untick it as always available, untick it in the stage, then tick it again. Confirmed: `test_making_a_stage_tool_always_available_can_be_undone_from_the_stage` (screenshot 13).
- **Fix:** When a tool is made always available, remove it from every stage's list in the same edit (in `AgentPanel`'s `onChange`). Or leave the stage tick enabled while the tool is listed in both places.

### E9 (low): "+ Stage" adds a box off screen
- **Where:** `frontend/src/App.tsx:131`, `graph.tsx:24-27`. `fitView` runs only once, when the page opens.
- **What's wrong:** The fifth box lands at x=1200, beyond the visible canvas.
- **What the person sees:** They press "+ Stage" and the canvas doesn't change; only the side panel does. Confirmed: `test_new_stage_appears_selected_and_can_be_saved` (screenshot 06).
- **Fix:** Place new boxes near the centre of the current view (`screenToFlowPosition`), or call `fitView` after adding.

### E10 (low): The highlighted box and the side panel can disagree
- **Where:** `frontend/src/App.tsx:61-70` and `131`. The side panel follows `selected`, while the box highlight follows React Flow's own `node.selected`. They are two separate records of the same thing.
- **What the person sees:**
  - After renaming a stage, no box is highlighted, because the renamed box is a new node and loses its selected flag.
  - After "+ Stage", the old box stays highlighted while the panel edits the new stage.
  Confirmed: the two `test_highlighted_box_matches_the_side_panel_*` tests.
- **Fix:** Derive each node's `selected` from `selected` in `buildNodes`, and drop React Flow's own selection changes. Or set `selected` from React Flow's `onSelectionChange` only.

### E11 (low): A rename that's refused leaves the wrong name in the field
- **Where:** `frontend/src/App.tsx:112-116`, `Panels.tsx:24-28`.
- **What's wrong:** Renaming "booking" to "end" is stopped with "There's already a stage called 'end'", but the Name field keeps showing "end". That message also appears under the heading "Not saved. Fix these first:", although nothing was being saved.
- **Fix:** Have `onRename` report whether it worked, and reset the draft name when it didn't. Show the message next to the field rather than in the Save banner. Confirmed: `test_renaming_into_an_existing_name_is_stopped`.

### E12 (low): The inspector's once-a-second requests pile up when answers are slow
- **Where:** `frontend/src/Inspector.tsx:16-36` (`setInterval(poll, 1000)` with an async `poll`).
- **What's wrong:** A new request starts every second whether or not the last one has answered. Answers can also arrive out of order, so an older answer can overwrite a newer one for a second. The `stopped` flag only guards against pause and unmount.
- **What the person sees:** On a slow or busy machine the inspector falls behind, or flickers back to an older state. With 3-second answers, 6 requests were waiting at once (`test_inspector_does_not_pile_up_requests_on_a_slow_server`). On localhost with small logs this is rarely visible.
- **Fix:** Use a loop that waits for each answer, then sleeps one second (`setTimeout` after `await`), with `stopped` checked before each request.

### E13 (low): The inspector jumps to the bottom on every new event
- **Where:** `frontend/src/Inspector.tsx:38-42`.
- **What's wrong:** While a call runs, anyone scrolled up to read earlier events or open instructions is pulled back down every time a line arrives.
- **Fix:** Only scroll to the bottom if the list was already at the bottom.

### E14 (low): Turning server problem text back into a list is fragile
- **Where:** `backend/editor_api.py:44-47`.
- **What's wrong:** The problem list is rebuilt by splitting the exception's text on new lines, dropping the first line and removing "- " prefixes. That depends on the exact wording `schema.py` and `builder.py` each build separately (the same "The agent file has problems:\n- …" format is written in two places).
  - A stage name containing a line break splits one problem into two items.
  - A change to the heading silently drops the first problem.
  - `KeyError` and `TypeError` become "The agent file is malformed: unhashable type: 'list'" (tested), which isn't plain words.
- **Fix:** Have the loader raise one exception class that carries `problems: list[str]`, used by both `schema.py` and `builder.py`, and return `e.problems`.

### E15 (low, unverified): Save on Windows can fail if a call starts at that instant; two saves at once share one temporary file
- **Where:** `backend/editor_api.py:64-66`.
- **What's wrong:**
  - On Linux and macOS `os.replace` is all-or-nothing, and my test of 150 saves during constant loads found no half-read file. But every file handed over, including the uncommitted call logs, has Windows line endings, which suggests the owner runs Windows. There, `os.replace` fails ("access denied") if the agent file is open by another reader at that moment: bot.py's `read_text` at the start of a call. The save would then show "Saving failed: 500 Internal Server Error" and leave `clinic_agent.saving` beside the agent file.
  - Separately, two saves at the same moment both write `clinic_agent.saving`, and one can move the other's half-written file into place. That's possible because the Save button re-enables itself during a save once any edit is made (App.tsx:87).
- **What the person sees:** A rare, unexplained save failure, or very rarely a broken agent file.
- **Fix:**
  - Use a unique temporary name (`tempfile.NamedTemporaryFile(dir=agent_file.parent, delete=False)`).
  - Retry `os.replace` a few times on `PermissionError`.
  - Hold a `threading.Lock` around the save.
  - Keep the Save button disabled while a save is in progress.

### E16 (low): "AI model" and "Voice id" fields allow values that break every call
- **Where:** `frontend/src/Panels.tsx` `AgentPanel` (the model field). The plan lists only name, persona, always-available tools and voice (nice-to-have).
- **What's wrong:** The model field goes beyond the plan, and neither field is checked. A typo such as "gpt4o" saves fine.
- **What the person sees:** The next test call fails at the first AI reply, or has no voice.
- **Fix:** Drop the model field (the plan didn't ask for it), or offer a fixed list. Show the voice id as read-only or with a note.

### E17 (low): The booking card keeps listing options after the call is booked
- **Where:** `backend/editor_api.py:98`.
- **What's wrong:** `options_on_offer` is shown whatever the card's status.
- **What the person sees:** After a booking, "On offer" still lists three doctors, which reads as if the booking isn't done (screenshot 09).
- **Fix:** Return an empty list (or label it "last offered") when the status isn't `in_progress`.

### E18 (low): The `/tools` route sends fields the page never uses
- **Where:** `backend/editor_api.py:71-72` (`fields`, `required`); `frontend/src/api.ts:43`.
- **What's wrong:** Nothing in `frontend/src` reads `fields` or `required`. This is dead data, and a second description of the registry to keep in step.
- **Fix:** Remove both, or show them (e.g. under each tool in the panel).

### E19 (low): The builder's tests miss what their names promise, and a docstring points at a record that doesn't exist
- **Where:** `backend/tests/test_builder_editor_api.py`.
- **What's wrong:**
  - Lines 36-40 compare `read_text()` before and after saving. Text mode turns Windows line endings into plain ones, so the test can't notice a save that changes every line ending: "same layout, so git shows only real edits" isn't actually checked. A byte comparison would.
  - Line 23 copies `"clinic_agent.json"` by relative path, so it only works when run from `backend/`.
  - Lines 2-3 say "the browser side was checked by hand and in a headless browser; see docs/build-log.md", but `docs/build-log.md` has no editor entry (nor does the CHANGELOG). No browser test is committed.
  - The broken-agent cases (lines 52-58) cover 5 kinds and no plain-words check. The token test calls `process_frame` directly with `push_frame` replaced, which checks the step but not where it sits in the pipeline.
- **Fix:** Compare bytes. Use a path relative to the test file. Add the build-log entry (or commit the headless check as a test).

### E20 (low): Leftovers
- **Where:** `frontend/src/Panels.tsx:23`; `App.tsx:166`; `backend/editor_api.py:28-36`.
- **What's wrong:**
  - `useEffect(() => setDraftName(stage.name), [stage.name])` never does anything, because `StagePanel` is keyed by `stage.name` (App.tsx:181) and starts fresh on every rename.
  - `c.source !== ALWAYS` in `onConnect` repeats a guard the box already enforces (`isConnectable={false}`). That's harmless, but it's two places for one rule.
  - `editor_api._names()` loads a second copy of the catalog in the same program that already holds `CLINIC.catalog`. That's harmless at this size.
- **Fix:** Remove the effect. Keep one of the two guards. Optionally pass the catalog into `editor_routes`.

### E21 (low, unverified): Token counts miss AI replies that are cut off
- **Where:** `backend/agent_builder/token_log.py:21-30`, `bot.py:115`.
- **What's wrong:** Placement is right (see "checked and correct"). But OpenAI sends the usage figures in the last piece of a streamed reply (`services/openai/base_llm.py:440-467`, `stream_options.include_usage`). When the caller talks over the AI and Pipecat cancels the reply, that last piece never arrives. The input tokens were still paid for but aren't logged.
- **What the person sees:** "AI replies" and "tokens in" undercount on calls with interruptions. This matters if these numbers feed the Phase 2 cost comparison.
- **Fix:** Note it next to the totals ("replies cut off by the caller aren't counted"). Or count interrupted requests separately, e.g. log an `ai_turn_cut_off` line when an interruption arrives while the AI is generating.

## Answers to the specific questions

1. **Save and the voice agent's loader.** Save runs the same `AgentBuilder.from_dict` the loader runs (bot.py runs `AgentBuilder.from_json` at each call), on the same parsed JSON. I found nothing the editor refuses that the loader accepts, or the reverse. But both accept agents the AI service can't run: E2, plus E16 for the model name. A call starting during a save is safe on Linux and macOS: tested with 150 saves during constant loads. It's unverified on Windows (E15).
2. **The agent file's shape.** Every edit copies the stage or agent with object spread, and only the edited field changes. Keys the panel doesn't show are kept, with their order: `pre_actions`, `respond_immediately`, `role_message`, `post_actions`, `history`, `parallel_tool_calls`, and arrows' `properties`/`required` (tested on both agent files). Nothing extra is added, and box positions live in the browser. Exceptions:
   - Deleting a stage drops arrows into it (E3).
   - Ticking "Ends the call" off writes `"end": false` where the key was absent, and ticking a tool on a stage without `tools` adds the key. Both are harmless.
   - A stage's `role_message` overrides the persona, yet the panel says "Persona (applies in every stage)" and doesn't show the override. No current agent uses one.
3. **React.**
   - Rename: the panel is reset (keyed by name), and the start setting and arrows follow. The highlight is lost (E10).
   - Delete: the panel is cleared. Arrows into the stage are dropped (E3).
   - Box positions and measured sizes are kept across edits, by merging with the previous nodes.
   - Polling stops on pause and unmount, but piles up when slow (E12).
   - The only crash found is E1.
   - Keys:
     - Events are keyed by position, which is fine for an append-only list.
     - Problems are keyed by their text, which is a duplicate key if the loader repeats a line ("isn't in the tool registry" for a tool listed twice). That's minor.
4. **The inspector.** It shows the current stage, the booking card with names (checked against the raw catalog for the real newest log), each tool call, and input/output/cached tokens per AI reply. It updates within about a second (tested). What's weak:
   - Tool results are reduced to ok / not done (E6).
   - The card keeps old options after booking (E17).
   - No real log has token lines yet, so the end-to-end "done when" (call, see tokens live) hasn't been shown with a real call. Unverified.
5. **TokenLog.** In Pipecat 1.4 the OpenAI service sends one usage note per completed AI request, from `start_llm_usage_metrics` → `push_frame(MetricsFrame)`, downstream. That includes the second request after a tool runs. TokenLog sits right after the LLM, so it sees every one.
   - The speech-to-text measurements pass through it but aren't LLM usage, so they're ignored. The voice's measurements are produced after it.
   - Nothing pushes these notes twice, so there's no double counting.
   - It can miss replies cut off by the caller (E21).
6. **Plan coverage.** Every plan item is present: canvas, side panel, agent settings, Save with checks, test call (frame plus new tab), and the inspector at about once a second.
   - Partly met: "errors in plain words" (E5), "each tool call with its short result" (E6) and "clarity" of the dashed arrows (E4).
   - Built but not asked for: the AI model field (E16), the "Live" switch, output and cached tokens, silence and time-limit lines, remembered box positions. All harmless except E16.

## Checked and found correct

- The save refuses every kind of broken agent the loader refuses (24 kinds tested), lists all problems at once, and leaves the file byte-for-byte untouched with no temporary file left.
- An unchanged save keeps the file byte-for-byte (plain line endings on Linux; Windows line endings on Windows, by Python's text mode).
- A cross-site page can't overwrite the agent. A `text/plain` post is refused by FastAPI, and a JSON post needs a check (CORS) the server doesn't allow.
- The `/tools` route matches the registry. The dashed arrows on the canvas are exactly the 7 the registry implies for `clinic_agent.json`, and the solid arrows match `example_flow.json`.
- The inspector:
  - picks the newest log by file name (names start with date and time)
  - skips a half-written last line
  - takes the card from the last whole line
  - strips the card from events
  - handles a missing or empty log folder
- The test call frame allows the microphone. The "open in a new tab" link works, and the unsaved-changes warning shows.
- bot.py adds the editor routes before the runner sets up its own. No runner route clashes with `/editor` or `/api/editor`. The default log folder is the same one the calls write to. The agent file is still read at the start of every call, so "save, then call, and the change is live" holds.
- The shipped `frontend/dist` is exactly what `npm run build` produces from `frontend/src`, and the TypeScript check passes.
