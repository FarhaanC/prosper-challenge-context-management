# Triage: independent check of the editor

Build checked: `9209ca0`. One fresh agent, first as tester (91 tests: 62 on the server, 29 in a
real browser) then as reviewer (21 findings). Farhaan's decisions on 11 Oct: **fix all 21**;
yes to the two behaviour changes (E2: the agent file's checks refuse arrow names the AI service
can't use; E3: deleting a stage keeps the arrows into it, so Save lists them); the AI model
becomes a dropdown (gpt-4o or gpt-4o-mini).

| # | Finding (short) | Sev. | Decision | What was done |
| --- | --- | --- | --- | --- |
| E1 | A stage without `task_messages` blanked the page | med | Fix | The panel treats a missing list as no instructions; the type says it's optional. |
| E2 | Arrow names the AI can't use were saved (space, empty, duplicate, a tool's name) | med | Fix (Farhaan: yes) | The load-time checks (so the editor **and** the voice agent) refuse them, in plain words. Dragged arrows get a safe, unique name (`go_to_<stage>`, `_2`…). |
| E3 | Deleting a stage silently deleted the arrows into it | med | Fix (Farhaan: yes) | Arrows stay; Save lists them ("goes to 'x', which isn't a stage"), and the panel shows the target as "(missing)". Comment corrected. |
| E4 | Arrows hidden behind boxes in the default layout | med | Fix | Stages zig-zag (every other one lower), the global box sits under the first stage. All 7 dashed arrows visible (screenshot checked). One label still tucks partly under a box: cosmetic. |
| E5 | Problems used the file's words (node, edge, initial_node) and didn't say what to do | med | Fix | Every load-time problem reworded in stage/arrow/tool words. Missing stages that tools need are one sentence each: "There's no stage called 'end', but the code of confirm_booking, hand_off, start_booking moves the call there: keep a stage with that name." The panel also says, on such a stage, "The code of … moves the call to this stage by its name, so keep the name." One message keeps the file's key because an older independent test names it ("global_tools must be a list of tool names (the always-available tools)"). |
| E6 | Refused tool calls showed only "not done" | med | Fix | Each tool line shows a short reason or result (error, say, reasons, problems, which_one, noted, or the reply), with the full reply one click away. |
| E7 | The problem list vanished at the first edit | low | Fix | It stays until the next Save, marked "(this list is from the last Save)" once edited. |
| E8 | A tool made always available couldn't be unticked in its stage | low | Fix | The stage's tick stays usable while the stage lists the tool too, so it can be taken out there (the reviewer's second option; it's also what the tester's test expects). |
| E9 | "+ Stage" put the box off screen | low | Fix | The view re-fits when a stage is added or removed, and when the call panel opens or closes (the tester's note). |
| E10 | Highlighted box and side panel could disagree | low | Fix | One record: the stage in the side panel is the highlighted box; React Flow's own selection is ignored. |
| E11 | A refused rename left the taken name in the field, under the "Not saved" heading | low | Fix | The field goes back to the real name; the reason shows under its own heading, "Can't rename the stage". |
| E12 | Inspector requests piled up on a slow server | low | Fix | Ask, wait for the answer, wait a second, ask again. |
| E13 | The inspector jumped to the bottom on every event | low | Fix | Only when the list was already at the bottom. |
| E14 | Problems were rebuilt by splitting an error's text | low | Fix | `AgentFileProblems` (a ValueError carrying `.problems`) is raised by both the shape checks and the builder; the editor returns that list. The "unhashable" crash path is gone (tool lists are checked before use). A body that isn't an object gets the same `{ok, problems}` answer. |
| E15 | Save could fail on Windows if a call read the file at that instant; two saves shared a temp file | low (unverified on Windows) | Fix | One save at a time (a lock), a unique temporary file, up to 5 tries 0.1 s apart if Windows refuses the swap, and the Save button stays off while saving. The file's own line endings are kept, so an unchanged save changes nothing on Windows either. |
| E16 | Free-text AI model and voice id | low | Fix (Farhaan: dropdown) | Model: gpt-4o or gpt-4o-mini (a model already in the file stays shown). Voice id: a note that a wrong id leaves calls silent. |
| E17 | The card listed options after booking | low | Fix | The inspector labels them "Last offered" and greys them once the call is booked or handed off. The server still returns the latest offer (the tester's test expects that). |
| E18 | `/tools` sent fields the page didn't use | low | Fix | The panel now shows each tool's fields ("Takes: full_name (needed), …"). Kept in the route, as the tester's test checks them. |
| E19 | Builder tests compared text not bytes, used a relative path, and cited a missing build-log entry | low | Fix | Byte comparison with both line-ending kinds, a path from the test file, docstring corrected; build-log entry added with this step. |
| E20 | Leftovers (an effect that never ran, a doubled guard, a second catalog) | low | Fix | Effect removed; only the box blocks dragging from "Always available"; bot.py passes its catalog in (`editor_routes(..., catalog=...)`, optional so the tester's calls still work). |
| E21 | Replies cut off by the caller aren't in the token counts | low (unverified) | Fix (as a note) | The inspector says so beside the totals. Counting them would need a usage figure the AI service doesn't send for a cancelled reply. To keep in mind for Saturday's cost numbers: the typed test loop has no interruptions, so it isn't affected. |

## Tests after the fixes

- Builder: all pass.
- Independent, server side (`tests_independent/editor/api`): 61 of 62. The one failure,
  `test_saving_unchanged_agent_with_windows_line_endings`, checks first that the repo's agent
  file has Windows line endings: on Farhaan's Windows checkout it does; the working copy edited
  from the Linux side had plain ones. The behaviour it tests (an unchanged save keeps Windows line
  endings) is now built (E15) and covered by the builder's byte test with both kinds.
- Independent, browser (`tests_independent/editor/browser`, run separately with Playwright): **29 of 29**.
- Independent, older (voice stages and rules module): all pass except
  `test_choose_option_handler_stays`, which is decision 66 itself (see the silence/read-back triage).
