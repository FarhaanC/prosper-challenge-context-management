# Independent review: decisions 64, 66 and 67 (commit 14dd04e)

## Summary

Most of the wiring is right. I checked it against the real Pipecat 1.4.0 and Pipecat Flows 1.4.0 code, and ran small simulations against the installed libraries. The silence timer starts after the greeting. It pauses while the agent speaks and while a tool runs. It picks up the 15-second wait after "Are you still there?". `UserIdleTimeoutUpdateFrame` does reach the user aggregator. For 66, returning a node from `choose_option` really does stop the AI pass, and the spoken read-back is added to the conversation.

There are three real problems, plus one likely one:

- **Noise turns the silence check off (R1).** A noise with no words (a rustle, a cough, a pocket) stops the silence count, and it only starts again the next time the agent speaks. On a silent or pocket-dialled line that never happens, so the call runs to the 10-minute cap. Decision 64 was meant to stop exactly that.
- **Talking over a code-spoken line jams Pipecat Flows (R2).** I reproduced this. If the caller talks over a line the code speaks (the greeting or the read-back), Flows waits forever for that line to "finish". For the greeting, the first stage's instructions and tools are then never sent. This comes from decision 58, not this commit, but 66 uses the same mechanism.
- **The 10-minute timer is never stopped when the agent ends the call itself (R3).** That covers every normal booking or hand-off. Ten minutes after the call started, it writes a false "time limit" line into the finished call's log.
- **"Are you still there?" followed by "Yes" can be read as a yes to the booking (R4).** The check-in sentence joins the conversation, so a caller who was thinking about the read-back may hear the check-in, say "Yes", and have that taken as agreement. This one is likely but unverified: the mechanism is confirmed, the AI's choice is not.

The rest are smaller clean-ups and tests that check text rather than behaviour.

## Findings

### R1. Noise with no words switches the silence check off until the agent next speaks (high)

**Where:** `backend/bot.py` lines 162 and 211–215; `backend/call/silence.py` lines 6–10 and 59–64. Library: `pipecat/turns/user_idle_controller.py` lines 88–111 and `llm_response_universal.py` lines 838–841.

**What's wrong:** Pipecat's idle timer starts in one place only: when the agent stops speaking (`BotStoppedSpeakingFrame`). When the caller starts a turn, the timer is cancelled (line 107–109). When the caller's turn ends (line 110–111), the timer is **not** restarted.

A turn can be started by the voice detector alone. If the speech-to-text returns no words (background noise, a rustle in a pocket, a cough), the user aggregator has nothing to send (`push_aggregation` returns early on an empty aggregation). So the AI never runs, the agent never speaks, and the timer never starts again.

The same happens after the check-in. `on_caller_spoke` also clears `checked_in`, so the 15-second hang-up is cancelled too.

I confirmed this with the real `UserIdleController`. The sequence "agent stops speaking, noise starts, noise stops, then silence" never fires the idle event. The sequence "agent stops speaking, then silence" fires on time.

**What a caller would experience:** A pocket dial. The greeting plays, the phone rustles once, and the line then stays open in silence until the 10-minute cap. The speech services are paid the whole time. The same happens if someone hears "Are you still there?", their phone scrapes a table, and they walk away: the call stays open for up to 10 minutes instead of ending 15 seconds later. Decision 64 names pocket dials as the reason for this feature.

**Suggested fix:** Restart the count when a caller turn ends and nothing will be said back. One option is a handler for the user aggregator's `on_user_turn_stopped` event. When `message.content` is empty, start a small fallback timer in bot.py (cancelled by the next `on_user_turn_started` or the agent speaking) that calls the same `on_silence` logic. Another option is to keep the whole silence timer in bot.py, built on the start/stop events, instead of relying on Pipecat's controller. Either way, add a test with "noise, no words, then silence".

### R2. If the caller talks over a line the code speaks, Pipecat Flows waits forever; for the greeting, the first stage never gets its instructions or tools (high, mostly from decision 58; also affects 66)

**Where:** `backend/clinic_agent.json` lines 21–27 (greeting `tts_say` and `respond_immediately: false`); `backend/agent_builder/builder.py` line 145 (`_say_and_wait` uses a `tts_say` pre-action). Library: `pipecat_flows/actions.py` lines 265–300 and 316–329, and `pipecat_flows/manager.py` lines 655–656 and 700–707. Also `pipecat/services/tts_service.py` around line 929 and `pipecat/transports/base_output.py` lines 538–553 (interruptions throw away queued frames).

**What's wrong:** A `tts_say` action queues the sentence, then a marker frame (`ActionFinishedFrame`). Flows then waits, with no time limit, for that marker to reach the end of the pipeline. Only after that does it send the stage's instructions and tools (the pre-actions run before `_update_llm_context`).

The marker is an ordinary frame, so it can be thrown away if the caller interrupts. It waits behind the sentence's audio, both in the TTS service's queue and in the output's audio queue, and an interruption clears both queues. When the marker is lost, the count of running actions stays at 1 and the wait never ends. Every later `tts_say` also waits forever, because the count never returns to 0.

I reproduced this with the real `PipelineWorker`, the real output transport, the real `ActionManager` and `FlowManager`, and a fake TTS:

- Not interrupted: the action finishes. The context holds the stage's instructions, and its tools are set.
- Interrupted part-way: the action is still waiting after 5 s. The context is empty, the tools are `NOT_GIVEN`, and `current_node` is `None`. A second `tts_say` afterwards is also stuck.

**What a caller would experience:**

- **Greeting (decision 58):** A caller who starts talking during "Hello, you've reached the clinics' scheduling line..." ("Hi, yes, I need to book...") reaches an AI that has the persona but no stage instructions and no tools. It can't call `start_booking`, so it will improvise or stall. The whole call is broken. This is the most common kind of interruption.
- **Read-back (66):** A caller who says "yes, yes" over "To confirm: ...". The stuck re-entry would only re-send what the booking stage already has, so nothing goes wrong for the caller today. But the action count stays stuck for the rest of the call. Any later read-back's re-entry also hangs (it never finishes), and a post-action added later to a stage that waits for the caller would silently never run.

**Suggested fix:** Don't use Flows' `tts_say` for lines the caller may talk over. Register a small custom action instead (for example `say`, through `flow_manager.register_action`) that just queues `TTSSpeakFrame(text)`. Flows doesn't wait after custom actions (`actions.py` lines 286–297), so nothing can hang. Use it for both the greeting and `_say_and_wait`.

For the greeting only, another option is to queue the `TTSSpeakFrame` from bot.py after `initialize`, or to mute the caller until the first line has been said. Add a simulation test like the one described above.

### R3. The 10-minute timer is never stopped when the agent ends the call, and it writes a false "time limit" line into the finished call's log (medium)

**Where:** `backend/bot.py` lines 217–237. Library: `pipecat/transports/smallwebrtc/transport.py` lines 478–488 and 539–545.

**What's wrong:** `time_limit_task` is cancelled only in `on_client_disconnected`. SmallWebRTC fires that event only when the **caller** hangs up. When the bot ends the call (`EndFrame` from the end stage, the silence goodbye or the time limit), it sets `_closing`, and `on_client_disconnected` is deliberately skipped. `run_bot` has no `finally`, so the task keeps sleeping after the call ends.

When it wakes, `watch.on_time_limit()` returns a step whenever the call ended through the end stage, because `CallWatch` doesn't know about that ending. `act()` then:

- writes `{"event": "time_limit", "said": "...time limit...", "hang_up": true}` into that call's log, and
- queues frames into a worker that has already finished.

**What happens:** Take a normal call that books in 3 minutes and ends with the agent's goodbye. Seven minutes later, its call log gets a line saying the time-limit goodbye was said and the call was hung up. Decision 45's call log is what calls are checked against and what the editor's inspector will read, so that line is false evidence.

Every such call also keeps its worker, flow manager and session in memory for up to 10 minutes. After a silence hang-up the task still sleeps, but writes nothing.

**Suggested fix:** Cancel the task when the pipeline ends, however it ends: wrap `await runner.run()` in `try/finally` (or use the worker's finished event). You could also mark `watch.ended` when the end stage is entered. Add a test that ends a call through the end stage and checks nothing is logged afterwards.

### R4. "Are you still there?" goes into the conversation, so the caller's "Yes" can read as a yes to the booking (medium; mechanism verified, the AI's choice unverified)

**Where:** `backend/bot.py` lines 195–203 (`TTSSpeakFrame(step.say)`, whose `append_to_context` defaults to True: `pipecat/frames/frames.py` line 803); the booking instructions at `backend/clinic_agent.json` line 57.

**What's wrong:** After the code-spoken read-back ("... Would you like me to book it?"), a caller who takes more than 20 s (checking a calendar, talking to someone) hears "Are you still there?". They answer "Yes." The AI then sees, in order: the read-back with its question, "Are you still there?", and "Yes". The instructions say "Only after they say yes, call confirm_booking", which makes a bare "Yes" an easy reason to book. The same thing can happen in stage 1 ("Have you been a patient with us before?", then the check-in, then "Yes").

**What a caller would experience:** They meant "I'm still here", and a booking is saved without them agreeing to it. This is the "sounded right, but was wrong" mistake the project leads with (decision 12).

**Suggested fix:** Add one sentence to the persona: "If you've just asked 'Are you still there?', a yes only means the caller is still on the line: ask your last question again before acting on it." Or make the check-in line itself repeat the question. A text-loop scenario for this case would show whether the model gets it right.

### R5. The tool result claims the read-back was already said, before it is said, and uses "said" with two different meanings (low)

**Where:** `backend/call/tools.py` lines 314–317; `backend/call/tools.py` line 623 and `backend/bot.py` line 199 (the log's `said`); the persona's `'say'` field, `backend/clinic_agent.json` line 5.

**What's wrong:**

1. The result tells the AI "The read_back has just been said to the caller". It's written before the speech starts. If the caller speaks in the gap between the tool finishing and the read-back starting, the queued sentence is thrown away (it's an ordinary frame) and the caller never hears it. The AI still believes they did. Small gap, but the claim is a guess presented as a fact.
2. `said` holds an instruction to the AI in the tool result, but the actual spoken sentence in the call log. Meanwhile the persona tells the AI to speak any `'say'` field as it is. `say` (speak this) and `said` (don't repeat this) are one letter apart and mean the opposite.

**Suggested fix:** Rename the result field to something like `note`. Word it so it doesn't depend on timing, for example: "The code is reading this back to the caller and asking whether to book it; don't repeat it." The spoken text is in the conversation anyway, as the agent's own turn.

### R6. The time-limit goodbye doesn't know whether the call is already ending (low)

**Where:** `backend/bot.py` lines 217–221.

**What's wrong:** The cap is only blocked by an earlier silence or time-limit hang-up. Right at 10 minutes it can therefore fire:

- while the end stage's goodbye is playing (two goodbyes), or
- just after `confirm_booking` saved a booking ("we've reached the time limit... Please call back if you still need help" after a successful booking).

This is rare, and nothing is lost: the booking is still saved. The R3 fix (tell `CallWatch` when the end stage starts) also fixes this.

### R7. `_say_and_wait` copies how a stage's tools and role are built (low, slop: same rule in two places)

**Where:** `backend/agent_builder/builder.py` lines 112–116 and 140–143.

**What's wrong:** The role message (`node.role_message or self.config.persona`) and the function list (edges + tools) are built in two places. If one changes later (a stage-specific tool filter, say), the read-back re-entry would quietly give the AI a different set of tools from the stage it is in.

**Suggested fix:** Use one helper, for example `_functions_and_role(node)`, called from both.

### R8. A tool that sets both `next_stage` and `say_now` silently loses the sentence (low, slop: silent failure)

**Where:** `backend/agent_builder/builder.py` lines 172–175.

**What's wrong:** `next_stage` wins and `say_now` is dropped without a word. No tool does this today. A future one would have its sentence never said, and the call log (`tools.py` line 623) would still record `said`, which is false.

**Suggested fix:** Raise an error in `run_tool` (or the builder) if both are set, or say in `Outcome` that they can't be combined and test it.

### R9. The new tests check text, not behaviour, and some copy the code's own output (low to medium, slop: tests that can't fail usefully)

**Where:** `backend/tests/test_builder_silence_and_read_back.py`.

- **Lines 91–98:** `test_bot_wires_the_idle_timer_and_the_time_limit` searches bot.py for strings. It passes with R1 and R3 present, and would fail on a harmless rename. It tests that text exists, not that silence is handled.
- **Lines 114–115 and 160–164:** these copy the code's exact sentences ("To confirm: {read_back} Would you like me to book it?", and two sentences from the agent file) as the expected answer. Any rewording breaks them, and they can never catch a wrong meaning.
- **Lines 145–156:** `test_only_choose_option_has_the_code_speak` checks 3 of the 9 tools. The name claims all of them. Loop over `TOOLS` instead, so a new tool that sets `say_now` by mistake is caught.
- **Missing:** nothing exercises the Pipecat side of 64 or 66. Small simulations like the ones in this review would cover the timer with noise, the timer after the check-in, an interrupted read-back, and the cap after a normal end.

### R10. `silence.py`'s description promises more than the wiring does (low, slop: comment doesn't match behaviour)

**Where:** `backend/call/silence.py` lines 6–10.

**What's wrong:** "Anything the caller says starts the count again from CHECK_IN_AFTER". In fact the count starts again only after the agent's next reply finishes, and a turn with no words stops the count entirely (R1). "Counted from when the agent stops speaking" is accurate. After the R1 fix, re-word the line to match.

### R11. The typed test loop must copy the new `say_now` behaviour (low; unverified: no typed loop in the files I was given)

**Where:** decision 22; `backend/call/tools.py` line 65.

**What's wrong:** Decision 22's typed loop copies Flows' "second AI pass after every tool call". After 66, the voice agent does **not** run a second pass after `choose_option`. It adds the read-back as the agent's turn and waits. If the typed loop still runs a second pass, the AI will reply to its own read-back in text mode, and the ~90 typed conversations will measure something the voice agent no longer does. That is the "small differences from Pipecat" risk named in decision 22.

**Suggested fix:** When the typed loop is built (or if it already exists), handle `say_now`: append it as the assistant's turn and skip the second pass. Add the same note to the next tester's spec-change note.

**Process note:** the independent test `test_choose_option_handler_stays` now fails by design. Under P2/P3 that needs a triage entry and a spec-change note to the next fresh tester. The INTERFACE.md change covers what the note should say.

## Checked and found correct

- **The greeting starts the silence count.** The greeting ends with the agent stopping speaking, so the 20 s timer starts before the caller has said anything. Confirmed with the real `UserIdleController`.
- **Speaking and tools pause the count.** The timer is cancelled while the agent speaks, and stays off while a tool runs. `FunctionCallsStartedFrame`, `FunctionCallResultFrame` and `FunctionCallCancelFrame` are broadcast both ways by the LLM service (`llm_service.py` lines 1273 and 1405), so they reach the user aggregator. The tool counter also covers 67's "Let me check." finishing while the tool is still running.
- **The timeout change reaches the aggregator.** `UserIdleTimeoutUpdateFrame`, queued with `worker.queue_frame`, passes through the input transport and STT to the user aggregator. I confirmed this in a running pipeline: the timer used the new value. The change applies to the next time the timer starts, which is exactly how `act()` uses it: queued before "Are you still there?", so the hang-up wait is 15 s counted from the end of that sentence.
- **`CallWatch` fires each step at most once.** No second check-in or goodbye once it has hung up. No time-limit goodbye after a silence hang-up. Caller speech after a check-in returns to 20 s.
- **Hang-ups keep their goodbye.** `EndFrame` can't be thrown away by an interruption, and it is processed after the queued goodbye, so the silence and time-limit goodbyes are spoken before the call ends (unless the caller talks over them; then the call still ends).
- **Event handler signatures match the library:** `on_user_turn_idle(aggregator)` and `on_user_turn_started(aggregator, strategy)`.
- **66 really skips the AI pass.** Returning `(result, node)` makes Flows report the result with `run_llm=False` (`manager.py` lines 503–516). With `respond_immediately: False` no `LLMRunFrame` is queued, and the empty `LLMMessagesAppendFrame` has `run_llm=None`, so it starts nothing. No AI pass runs until the caller speaks.
- **66 puts the read-back into the conversation.** The `tts_say` text is appended by default (`actions.py` line 324; `TTSSpeakFrame.append_to_context=True`), so the AI's next pass sees what was said.
- **Re-entering the booking stage is harmless (when not interrupted).** The same system instruction is sent again (no effect). The same tools are sent again (tool-change messages are off by default, and the tool list hasn't changed). Global tools are added again by Flows as usual. The booking stage has no post-actions, so nothing deferred is lost. `_pending_transition` is cleared as normal.
- **The stage and call log stay right.** `session.stage` stays `booking` (the re-entry doesn't call `enter_stage`). The call log gets one tool line with `said` and `next_stage: null`, and no false stage-move line.
- **A refused `choose_option` behaves as before:** it returns only the result, so the AI runs and can explain.
- **67 is clear and consistent.** It matches stage 2's "say one short sentence before calling a tool" and the persona's "one or two short sentences". It doesn't conflict with the read-back rule (no line needed before `choose_option`).
- **INTERFACE.md matches the code** for `choose_option`, `Outcome.say_now` and the new log events.
- **The numbers are named and explained.** `CHECK_IN_AFTER`, `HANG_UP_AFTER` and `MAX_CALL_SECONDS` have their reasons in the module docstring.

*How this was checked:* I installed `pipecat-ai==1.4.0` and `pipecat-ai-flows==1.4.0` in a scratch environment. The four library files the change relies on are byte-identical to the uploaded copies. The simulations used the real Pipecat classes, with fake audio standing in for ElevenLabs: the idle controller driven frame by frame; a running pipeline for the timeout change; `ActionManager` and `FlowManager` with the real output transport for the interrupted-speech case. No uploaded files were changed.
