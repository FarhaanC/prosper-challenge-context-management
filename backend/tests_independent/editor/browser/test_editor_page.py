"""Independent browser tests of the editor page (Phase 1 plan, items 1, 2, 4, 5, 6).

Expected answers come from the plan, the raw agent file, the tool registry's documented
moves (call/tools.py header table) and the real call logs.
"""

import json
import time

from conftest import shot, start_server

STAGES = ["identify", "visit_type", "booking", "end"]

# Dashed arrows the registry implies for the real agent file (self-moves aren't drawn).
#   identify: start_booking -> visit_type, end
#   visit_type: choose_visit_type -> booking (list_visit_types stays)
#   booking: confirm_booking -> end (and booking itself); choose_option stays
#   always available: change_choice, turn_down_doctors -> visit_type, booking; hand_off -> end
EXPECTED_DASHED = {
    ("identify", "visit_type"), ("identify", "end"), ("visit_type", "booking"), ("booking", "end"),
    ("always", "visit_type"), ("always", "booking"), ("always", "end"),
}


def open_editor(page, served):
    page.goto(served.url + "/editor/")
    page.wait_for_selector(".react-flow__node")
    page.wait_for_timeout(500)


def box(page, name):
    return page.locator(f'.react-flow__node[data-id="{name}"]')


def edges(page):
    """(from, to, dashed?, label) for every arrow drawn, read from the drawing itself."""
    out = []
    for e in page.query_selector_all(".react-flow__edge"):
        label = e.get_attribute("aria-label") or ""  # "Edge from X to Y"
        _, rest = label.split("Edge from ", 1)
        src, dst = rest.split(" to ", 1)
        path = e.query_selector(".react-flow__edge-path")
        dash = page.evaluate("p => getComputedStyle(p).strokeDasharray", path)
        text = e.query_selector(".react-flow__edge-text")
        out.append((src, dst, dash not in ("none", ""), text.text_content() if text else ""))
    return out


def side(page):
    return page.locator("aside.side")


def save_button(page):
    return page.get_by_role("button", name="Save")


def drag_arrow(page, source, target):
    s = box(page, source).locator(".react-flow__handle.source").bounding_box()
    t = box(page, target).locator(".react-flow__handle.target").bounding_box()
    page.mouse.move(s["x"] + s["width"] / 2, s["y"] + s["height"] / 2)
    page.mouse.down()
    page.mouse.move((s["x"] + t["x"]) / 2, (s["y"] + t["y"]) / 2 + 40, steps=8)
    page.mouse.move(t["x"] + t["width"] / 2, t["y"] + t["height"] / 2, steps=8)
    page.mouse.up()
    page.wait_for_timeout(300)


# ------------------------------------------------------------------ canvas
def test_canvas_shows_every_stage_with_its_tools(page, served):
    open_editor(page, served)
    agent = json.loads(served.agent_bytes())
    for stage in agent["nodes"]:
        b = box(page, stage["name"])
        assert b.count() == 1, stage["name"]
        text = b.inner_text()
        assert stage["name"] in text
        for tool in stage.get("tools", []):
            assert tool in text
    assert "start" in box(page, "identify").inner_text()
    assert "ends call" in box(page, "end").inner_text()
    always = page.locator(".react-flow__node", has_text="Always available").inner_text()
    for tool in agent["global_tools"]:
        assert tool in always
    shot(page, "01_canvas")
    assert page.errors == []


def test_canvas_draws_the_dashed_arrows_the_registry_implies(page, served):
    open_editor(page, served)
    drawn = edges(page)
    norm = lambda n: "always" if n.startswith("__") else n  # noqa: E731
    dashed = {(norm(s), norm(d)) for s, d, is_dashed, _ in drawn if is_dashed}
    solid = [(s, d) for s, d, is_dashed, _ in drawn if not is_dashed]
    assert dashed == EXPECTED_DASHED
    assert solid == []  # the real agent has no AI-chosen arrows
    labels = {(norm(s), norm(d)): lab for s, d, _, lab in drawn}
    assert "start_booking" in labels[("identify", "visit_type")]
    assert "hand_off" in labels[("always", "end")]
    assert "change_choice" in labels[("always", "booking")] and "turn_down_doctors" in labels[("always", "booking")]


# ------------------------------------------------------------------ editing and saving
def test_save_is_off_until_something_changes(page, served):
    open_editor(page, served)
    assert save_button(page).is_disabled()


def test_edit_instructions_then_save_writes_the_file(page, served):
    open_editor(page, served)
    before = json.loads(served.agent_bytes())
    box(page, "visit_type").click()
    assert side(page).locator("input").first.input_value() == "visit_type"
    area = side(page).locator("textarea").first
    original = area.input_value()
    assert original == before["nodes"][1]["task_messages"][0]["content"]
    area.click()
    page.keyboard.press("Control+End")
    page.keyboard.type(" Keep it short.")
    assert page.get_by_text("Unsaved changes").is_visible()
    save_button(page).click()
    page.get_by_text("Saved. The next call uses it.").wait_for(timeout=3000)
    after = json.loads(served.agent_bytes())
    assert after["nodes"][1]["task_messages"][0]["content"] == original + " Keep it short."
    # Nothing else changed: every other key and value, including ones the panel doesn't show.
    after["nodes"][1]["task_messages"][0]["content"] = original
    assert after == before
    assert list(after) == list(before)
    for a, b in zip(after["nodes"], before["nodes"]):
        assert list(a) == list(b)
    assert save_button(page).is_disabled()
    shot(page, "02_saved")


def test_agent_settings_edit_and_save(page, served):
    open_editor(page, served)
    persona = side(page).locator("textarea")
    persona.click()
    page.keyboard.press("Control+End")
    page.keyboard.type(" Smile.")
    save_button(page).click()
    page.get_by_text("Saved. The next call uses it.").wait_for(timeout=3000)
    assert json.loads(served.agent_bytes())["persona"].endswith(" Smile.")


def test_renaming_a_stage_others_point_to_is_refused_on_save(page, served):
    open_editor(page, served)
    before = served.agent_bytes()
    box(page, "booking").click()
    name = side(page).locator("input").first
    name.fill("options")
    name.press("Enter")
    page.wait_for_timeout(300)
    assert box(page, "options").count() == 1
    save_button(page).click()
    problems = page.locator(".problems")
    problems.wait_for(timeout=3000)
    text = problems.inner_text()
    shot(page, "03_rename_refused")
    assert "booking" in text  # the tools that move to 'booking' are named
    assert served.agent_bytes() == before


def test_renaming_into_an_existing_name_is_stopped(page, served):
    open_editor(page, served)
    box(page, "booking").click()
    name = side(page).locator("input").first
    name.fill("end")
    name.press("Enter")
    page.wait_for_timeout(300)
    assert box(page, "booking").count() == 1
    assert page.locator(".problems").inner_text().count("end") >= 1
    # The name field should show the stage's real name again, not the refused one.
    assert side(page).locator("input").first.input_value() == "booking"


def test_deleting_the_start_stage_is_refused_on_save(page, served):
    open_editor(page, served)
    before = served.agent_bytes()
    box(page, "identify").click()
    page.get_by_role("button", name="Delete this stage").click()
    page.wait_for_timeout(300)
    assert box(page, "identify").count() == 0
    save_button(page).click()
    page.locator(".problems").wait_for(timeout=3000)
    text = page.locator(".problems").inner_text()
    shot(page, "04_delete_start_refused")
    assert "identify" in text
    assert served.agent_bytes() == before


def test_problem_list_stays_while_fixing(page, served):
    """Plan: Save 'shows any errors in plain words'. They should stay visible while the
    person fixes them, not vanish at the first key press."""
    open_editor(page, served)
    box(page, "identify").click()
    page.get_by_role("button", name="Delete this stage").click()
    save_button(page).click()
    page.locator(".problems").wait_for(timeout=3000)
    box(page, "visit_type").click()
    page.get_by_text("Calls start here").click()
    page.wait_for_timeout(300)
    assert page.locator(".problems").count() == 1


def test_dragging_makes_an_arrow_and_save_writes_it(page, served):
    open_editor(page, served)
    drag_arrow(page, "identify", "booking")
    solid = [(s, d) for s, d, dashed, _ in edges(page) if not dashed]
    shot(page, "05_dragged_arrow")
    assert solid == [("identify", "booking")]
    box(page, "identify").click()
    assert side(page).get_by_text("Arrows out").is_visible()
    save_button(page).click()
    page.get_by_text("Saved. The next call uses it.").wait_for(timeout=3000)
    identify = json.loads(served.agent_bytes())["nodes"][0]
    assert len(identify["edges"]) == 1
    arrow = identify["edges"][0]
    assert arrow["target"] == "booking"
    assert set(arrow) <= {"function", "description", "target", "properties", "required"}
    assert arrow["function"] and arrow["description"]


def test_new_stage_appears_selected_and_can_be_saved(page, served):
    open_editor(page, served)
    page.get_by_role("button", name="+ Stage").click()
    page.wait_for_timeout(400)
    assert box(page, "new_stage_1").count() == 1
    assert side(page).locator("input").first.input_value() == "new_stage_1"
    shot(page, "06_new_stage")
    # Is the new box on screen, where the person can see it?
    b = box(page, "new_stage_1").bounding_box()
    canvas = page.locator(".canvas").bounding_box()
    on_screen = b and b["x"] + b["width"] <= canvas["x"] + canvas["width"] and b["x"] >= canvas["x"]
    save_button(page).click()
    page.get_by_text("Saved. The next call uses it.").wait_for(timeout=3000)
    nodes = json.loads(served.agent_bytes())["nodes"]
    assert nodes[-1]["name"] == "new_stage_1"
    assert on_screen, f"new box at {b}, canvas {canvas}"


def test_arrow_from_a_stage_named_with_spaces(page, served):
    """A stage renamed 'new stage', then an arrow dragged into it: the arrow's name has a space.
    The save accepts it (the loader does too); the AI service only accepts names made of
    letters, digits, _ and - (beyond the plan's list: recorded for the reviewer)."""
    open_editor(page, served)
    page.get_by_role("button", name="+ Stage").click()
    name = side(page).locator("input").first
    name.fill("wrap up")
    name.press("Enter")
    page.wait_for_timeout(300)
    page.locator(".react-flow__controls-fitview").click()  # the new box starts off screen
    page.wait_for_timeout(500)
    drag_arrow(page, "booking", "wrap up")
    save_button(page).click()
    page.wait_for_timeout(800)
    shot(page, "10_arrow_name_with_space")
    saved = json.loads(served.agent_bytes())
    booking = next(n for n in saved["nodes"] if n["name"] == "booking")
    names = [e["function"] for e in booking.get("edges", [])]
    assert names, "the drag didn't make an arrow, or the save was refused"
    assert not any(" " in n for n in names), names


# ------------------------------------------------------------------ keys the panel doesn't show
def test_a_stage_without_instructions_key_can_be_selected(page, tmp_path):
    """task_messages is optional in the agent format (Node.from_dict defaults it to []).
    Selecting such a stage must not break the page."""
    agent = json.loads((start_server.__globals__["BACKEND"] / "clinic_agent.json").read_bytes())
    end = agent["nodes"][3]
    del end["task_messages"]
    served, proc = start_server(tmp_path, json.dumps(agent, indent=2).encode())
    try:
        open_editor(page, served)
        box(page, "end").click()
        page.wait_for_timeout(500)
        shot(page, "07_stage_without_instructions")
        assert page.errors == [], page.errors
        assert side(page).locator("input").first.input_value() == "end"
    finally:
        proc.terminate()
        proc.wait(10)


# ------------------------------------------------------------------ test call
def test_test_call_opens_the_call_page(page, served):
    open_editor(page, served)
    page.get_by_role("button", name="Test call").click()
    frame = page.frame_locator("aside.call iframe")
    frame.locator("#stand-in").wait_for(timeout=3000)
    link = page.get_by_role("link", name="open in a new tab")
    assert link.get_attribute("href") == "/client/"
    assert link.get_attribute("target") == "_blank"
    assert "microphone" in page.locator("aside.call iframe").get_attribute("allow")
    shot(page, "08_test_call")
    with page.context.expect_page() as new:
        link.click()
    new.value.wait_for_load_state()
    assert new.value.url.endswith("/client/")


def test_test_call_warns_about_unsaved_changes(page, served):
    open_editor(page, served)
    page.get_by_role("button", name="Test call").click()
    assert page.get_by_text("unsaved changes").count() == 0
    box(page, "end").click()
    side(page).locator("textarea").first.type(" x")
    assert page.get_by_text("You have unsaved changes").is_visible()


# ------------------------------------------------------------------ inspector
def test_inspector_shows_the_newest_call(page, served):
    open_editor(page, served)
    insp = page.locator(".inspector")
    insp.get_by_text("20261010-184339-8e2ba6.jsonl").wait_for(timeout=3000)
    text = insp.inner_text()
    assert "Stage: end" in text.replace("\n", " ") or "Stage:\nend" in text or "Stage: \nend" in text
    assert "Zoya Chida" in text
    assert "Dr. Michael Sato" in text and "Richmond Care Center" in text
    assert "booked" in text
    for tool in ("start_booking", "list_visit_types", "choose_visit_type", "change_choice", "choose_option",
                 "confirm_booking"):
        assert tool in text
    assert page.locator(".inspector .ev.tool").count() == 7
    assert page.locator(".inspector .ev.stage").count() == 6


def test_inspector_updates_live_when_a_line_is_appended(page, served):
    open_editor(page, served)
    page.locator(".inspector").get_by_text("20261010-184339-8e2ba6.jsonl").wait_for(timeout=3000)
    newest = served.log_dir / "20261010-184339-8e2ba6.jsonl"
    card = json.loads(newest.read_text().splitlines()[-1])["card"]
    with newest.open("a") as f:
        f.write(json.dumps({"at": "2026-10-10T18:47:15", "event": "ai_turn", "input_tokens": 2345,
                            "output_tokens": 17, "cached_input_tokens": 1024, "card": card}) + "\n")
    t0 = time.time()
    page.locator(".inspector .ev.ai").wait_for(timeout=2500)
    took = time.time() - t0
    text = page.locator(".inspector").inner_text()
    assert "2,345" in text
    assert "AI replies: 1" in text
    shot(page, "09_inspector_live")
    assert took < 2.5


def test_inspector_switches_to_a_new_call(page, served):
    open_editor(page, served)
    page.locator(".inspector").get_by_text("20261010-184339-8e2ba6.jsonl").wait_for(timeout=3000)
    newer = served.log_dir / "20261011-101010-abc123.jsonl"
    newer.write_text(json.dumps({
        "at": "2026-10-11T10:10:10", "event": "stage", "stage": "identify", "instructions": ["Hello"],
        "card": {"caller": None, "preferences": {"visit_description": ""}, "choices": {}, "status": "in_progress",
                 "offered_options": []}}) + "\n")
    page.locator(".inspector").get_by_text(newer.name).wait_for(timeout=2500)
    text = page.locator(".inspector").inner_text()
    assert "not identified yet" in text
    assert "Zoya" not in text


def test_inspector_live_switch_pauses_polling(page, served):
    open_editor(page, served)
    page.locator(".inspector").get_by_text("20261010-184339-8e2ba6.jsonl").wait_for(timeout=3000)
    calls = []
    page.on("request", lambda r: calls.append(r.url) if "calls/latest" in r.url else None)
    page.locator(".inspector input[type=checkbox]").uncheck()
    page.wait_for_timeout(300)
    calls.clear()
    page.wait_for_timeout(2500)
    assert calls == []
    page.locator(".inspector input[type=checkbox]").check()
    page.wait_for_timeout(1500)
    assert len(calls) >= 1


def test_inspector_with_no_calls(page, tmp_path):
    served, proc = start_server(tmp_path, copy_logs=False)
    try:
        open_editor(page, served)
        page.wait_for_timeout(1200)
        text = page.locator(".inspector").inner_text()
        assert "no calls yet" in text and "No call yet." in text
        assert page.errors == []
    finally:
        proc.terminate()
        proc.wait(10)


# ------------------------------------------------------------------ an agent with AI-chosen arrows
# example_flow.json (the starter agent) has solid arrows with collected fields
# (properties/required), and no registry tools.
def _example(tmp_path):
    from conftest import BACKEND
    return start_server(tmp_path, (BACKEND / "example_flow.json").read_bytes(), copy_logs=False)


def test_solid_arrows_of_the_example_agent(page, tmp_path):
    served, proc = _example(tmp_path)
    try:
        open_editor(page, served)
        drawn = edges(page)
        solid = {(s, d, lab) for s, d, dashed, lab in drawn if not dashed}
        assert solid == {("greeting", "collect_details", "choose_intent"),
                         ("collect_details", "offer_times", "record_details"),
                         ("offer_times", "confirm", "select_time")}
        assert [x for x in drawn if x[2]] == []
        shot(page, "11_example_agent")
    finally:
        proc.terminate()
        proc.wait(10)


def test_editing_an_arrow_keeps_its_fields(page, tmp_path):
    served, proc = _example(tmp_path)
    try:
        before = json.loads(served.agent_bytes())
        open_editor(page, served)
        box(page, "collect_details").click()
        when = side(page).locator(".arrow input").nth(1)
        when.click()
        page.keyboard.press("End")
        page.keyboard.type(" Only once.")
        save_button(page).click()
        page.get_by_text("Saved. The next call uses it.").wait_for(timeout=3000)
        after = json.loads(served.agent_bytes())
        edge_after = after["nodes"][1]["edges"][0]
        edge_before = before["nodes"][1]["edges"][0]
        assert edge_after["description"] == edge_before["description"] + " Only once."
        edge_after["description"] = edge_before["description"]
        assert after == before
    finally:
        proc.terminate()
        proc.wait(10)


def test_renaming_a_stage_moves_its_arrows_and_start(page, tmp_path):
    served, proc = _example(tmp_path)
    try:
        open_editor(page, served)
        box(page, "collect_details").click()
        name = side(page).locator("input").first
        name.fill("details")
        name.press("Enter")
        box(page, "greeting").click()
        name = side(page).locator("input").first
        name.fill("hello")
        name.press("Enter")
        page.wait_for_timeout(300)
        save_button(page).click()
        page.get_by_text("Saved. The next call uses it.").wait_for(timeout=3000)
        after = json.loads(served.agent_bytes())
        assert after["initial_node"] == "hello"
        assert [n["name"] for n in after["nodes"]] == ["hello", "details", "offer_times", "confirm"]
        assert after["nodes"][0]["edges"][0]["target"] == "details"
    finally:
        proc.terminate()
        proc.wait(10)


def test_deleting_a_stage_arrows_point_to_is_reported_not_silent(page, tmp_path):
    """Plan item 4: arrows to missing stages are caught by Save and shown in plain words.
    Deleting 'offer_times' leaves collect_details' arrow 'record_details' (with its
    collected fields) pointing nowhere: the person should be told, not lose it unseen."""
    served, proc = _example(tmp_path)
    try:
        before = served.agent_bytes()
        open_editor(page, served)
        box(page, "offer_times").click()
        page.get_by_role("button", name="Delete this stage").click()
        page.wait_for_timeout(300)
        save_button(page).click()
        page.wait_for_timeout(1000)
        shot(page, "12_delete_arrow_target")
        saved = json.loads(served.agent_bytes())
        collect = next(n for n in saved["nodes"] if n["name"] == "collect_details")
        told = page.locator(".problems").count() == 1
        kept = any(e["function"] == "record_details" for e in collect.get("edges", []))
        assert told or kept, "the arrow 'record_details' and its fields were removed without a word"
        if told:
            assert served.agent_bytes() == before
    finally:
        proc.terminate()
        proc.wait(10)


def test_inspector_does_not_pile_up_requests_on_a_slow_server(page, tmp_path):
    """Plan item 6: the editor fetches 'about once a second'. If an answer takes longer
    than that, the next question should wait, not stack up."""
    served, proc = start_server(tmp_path, env={"EDITOR_TEST_SLOW_LATEST": "3"})
    try:
        in_flight, most = [0], [0]

        def started(r):
            if "calls/latest" in r.url:
                in_flight[0] += 1
                most[0] = max(most[0], in_flight[0])

        def ended(r):
            if "calls/latest" in r.url:
                in_flight[0] -= 1

        page.on("request", started)
        page.on("requestfinished", ended)
        page.on("requestfailed", ended)
        open_editor(page, served)
        page.wait_for_timeout(6000)
        assert most[0] <= 1, f"{most[0]} inspector requests were waiting at once"
    finally:
        proc.terminate()
        proc.wait(10)


def _highlighted(page):
    return [n.get_attribute("data-id") for n in page.query_selector_all(".react-flow__node .box.selected")
            for n in [n.query_selector("xpath=..")]]


def test_highlighted_box_matches_the_side_panel_after_rename(page, served):
    open_editor(page, served)
    box(page, "booking").click()
    assert _highlighted(page) == ["booking"]
    name = side(page).locator("input").first
    name.fill("options")
    name.press("Enter")
    page.wait_for_timeout(300)
    assert side(page).locator("input").first.input_value() == "options"
    assert _highlighted(page) == ["options"]


def test_highlighted_box_matches_the_side_panel_after_adding_a_stage(page, served):
    open_editor(page, served)
    box(page, "identify").click()
    page.get_by_role("button", name="+ Stage").click()
    page.wait_for_timeout(300)
    assert side(page).locator("input").first.input_value() == "new_stage_1"
    assert _highlighted(page) in (["new_stage_1"], [])


def test_inspector_shows_why_a_tool_was_refused(page, served):
    """Plan item 6: 'each tool call with its short result'. A refused visit type comes back
    as {ok: false, reasons: [...]} (call/tools.py choose_visit_type); the reason is the result."""
    open_editor(page, served)
    page.locator(".inspector").get_by_text("20261010-184339-8e2ba6.jsonl").wait_for(timeout=3000)
    newest = served.log_dir / "20261010-184339-8e2ba6.jsonl"
    with newest.open("a") as f:
        f.write(json.dumps({"at": "2026-10-10T18:48:00", "event": "tool", "stage": "visit_type",
                            "tool": "choose_visit_type", "args": {"visit_type_id": "appt_021"},
                            "result": {"ok": False, "reasons": ["This visit needs a referral."],
                                       "alternatives": []}, "next_stage": None}) + "\n")
    page.locator(".inspector .ev.refused").wait_for(timeout=2500)
    assert "needs a referral" in page.locator(".inspector .ev.refused").inner_text()


def test_making_a_stage_tool_always_available_can_be_undone_from_the_stage(page, served):
    """Ticking a stage's tool as always-available makes Save refuse ('list it once'). The
    person should then be able to untick it in the stage; the stage's box is greyed out."""
    open_editor(page, served)
    side(page).locator("label.tool", has_text="choose_option").locator("input").check()
    save_button(page).click()
    page.locator(".problems").wait_for(timeout=3000)
    assert "choose_option" in page.locator(".problems").inner_text()
    box(page, "booking").click()
    stage_box = side(page).locator("label.tool", has_text="choose_option").locator("input")
    shot(page, "13_global_tool_trap")
    assert stage_box.is_enabled(), "the stage's tick can't be removed while the tool is always available"
