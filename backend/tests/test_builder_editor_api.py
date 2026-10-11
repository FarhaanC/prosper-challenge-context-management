"""Builder tests for the editor's server (editor_api.py) and the token counts in the call log
(agent_builder/token_log.py, decision 45). The browser side is covered by the independent
browser tests (tests_independent/editor/browser), which need Playwright."""

import asyncio
import json
import shutil
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pipecat.frames.frames import MetricsFrame
from pipecat.metrics.metrics import LLMTokenUsage, LLMUsageMetricsData

from agent_builder import TokenLog
from call import TOOLS
from editor_api import editor_routes

BACKEND = Path(__file__).resolve().parent.parent


@pytest.fixture
def setup(tmp_path):
    agent_file = tmp_path / "agent.json"
    shutil.copy(BACKEND / "clinic_agent.json", agent_file)
    logs = tmp_path / "logs"
    logs.mkdir()
    app = FastAPI()
    app.include_router(editor_routes(agent_file, logs))
    return TestClient(app), agent_file, logs


def test_load_gives_the_agent_file_as_it_is(setup):
    client, agent_file, _ = setup
    assert client.get("/api/editor/agent").json() == json.loads(agent_file.read_text(encoding="utf-8"))


@pytest.mark.parametrize("line_end", [b"\n", b"\r\n"])
def test_saving_an_unchanged_agent_changes_nothing_in_the_file(setup, line_end):
    """Byte for byte, with either kind of line ending (a Windows checkout has \r\n)."""
    client, agent_file, _ = setup
    agent_file.write_bytes(agent_file.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", line_end))
    before = agent_file.read_bytes()
    assert client.post("/api/editor/agent", json=json.loads(before)).json() == {"ok": True}
    assert agent_file.read_bytes() == before, "same layout, so git shows only real edits"
    assert not list(agent_file.parent.glob("*.saving")), "no temporary file left behind"


def test_an_edited_instruction_is_saved(setup):
    client, agent_file, _ = setup
    agent = client.get("/api/editor/agent").json()
    agent["nodes"][2]["task_messages"][0]["content"] += "\n\nNEW LINE"
    assert client.post("/api/editor/agent", json=agent).status_code == 200
    saved = json.loads(agent_file.read_text(encoding="utf-8"))
    assert saved["nodes"][2]["task_messages"][0]["content"].endswith("NEW LINE")


@pytest.mark.parametrize("break_it, says", [
    (lambda a: a["nodes"][3].update(name="finish"), "There's no stage called 'end', but the code of "
                                                     "confirm_booking, hand_off, start_booking moves the call there"),
    (lambda a: a.update(initial_node="nowhere"), "The start stage 'nowhere' doesn't exist."),
    (lambda a: a["nodes"][0].update(edges=[{"function": "go to end", "description": "d", "target": "end"}]),
     "a name can only use letters, digits, _ and -"),
    (lambda a: a["nodes"][0].update(edges=[{"function": "hand_off", "description": "d", "target": "end"}]),
     "has the same name as a tool"),
    (lambda a: a["nodes"][0].update(edges=[{"function": "go", "description": "d", "target": "end"}] * 2),
     "two arrows called 'go'"),
    (lambda a: a["nodes"][1]["tools"].append("book_it"), "isn't in the tool registry"),
    (lambda a: a["nodes"][2]["task_messages"][0].update(content="{optoins}"), "unknown placeholder {optoins}"),
    (lambda a: a["nodes"][0].update(position={"x": 1}), "unknown key 'position'"),
])
def test_a_broken_agent_is_refused_with_every_problem_and_nothing_is_saved(setup, break_it, says):
    client, agent_file, _ = setup
    before = agent_file.read_text(encoding="utf-8")
    agent = json.loads(before)
    break_it(agent)
    response = client.post("/api/editor/agent", json=agent)
    assert response.status_code == 422 and response.json()["ok"] is False
    assert any(says in p for p in response.json()["problems"]), response.json()["problems"]
    assert agent_file.read_text(encoding="utf-8") == before


def test_the_tool_registry_is_what_the_code_has(setup):
    client, _, _ = setup
    tools = {t["name"]: t for t in client.get("/api/editor/tools").json()}
    assert set(tools) == set(TOOLS)
    assert tools["start_booking"]["moves_to"] == ["visit_type", "end"]
    assert tools["answer_question"]["moves_to"] == []
    assert tools["change_choice"]["description"] == TOOLS["change_choice"].description


def test_the_inspector_reads_the_newest_call_with_names_on_the_card(setup):
    client, _, logs = setup
    assert client.get("/api/editor/calls/latest").json() == {"file": None, "events": [], "card": None}
    card = {"caller": {"name": "Farhan Jida", "is_new_patient": True}, "preferences": {"visit_description": ""},
            "choices": {"visit_type_id": "appt_027", "provider_id": "", "location_id": "", "slot": None},
            "status": "in_progress", "offered_options": [{"spoken": "Dr. A at B, Monday at 9 AM"}]}
    (logs / "20261011-090000-aaaaaa.jsonl").write_text(json.dumps({"at": "x", "event": "stage", "card": card}) + "\n")
    newer = logs / "20261011-100000-bbbbbb.jsonl"
    newer.write_text(
        json.dumps({"at": "2026-10-11T10:00:01", "event": "stage", "stage": "booking", "instructions": ["..."], "card": card})
        + "\n" + json.dumps({"at": "2026-10-11T10:00:02", "event": "ai_turn", "input_tokens": 1200, "output_tokens": 30,
                             "card": card})
        + "\n" + '{"at": "half a line')  # being written right now
    latest = client.get("/api/editor/calls/latest").json()
    assert latest["file"] == newer.name
    assert [e["event"] for e in latest["events"]] == ["stage", "ai_turn"]
    assert all("card" not in e for e in latest["events"])
    assert latest["card"]["caller"] == "Farhan Jida" and latest["card"]["visit"] == "Skin Cancer Screening"
    assert latest["card"]["options_on_offer"] == ["Dr. A at B, Monday at 9 AM"]


def test_token_counts_go_into_the_call_log():
    lines = []
    step = TokenLog(lines.append)
    usage = LLMTokenUsage(prompt_tokens=1500, completion_tokens=42, total_tokens=1542, cache_read_input_tokens=1024)
    passed = []

    async def push_frame(frame, direction=None):
        passed.append(frame)

    step.push_frame = push_frame
    frame = MetricsFrame(data=[LLMUsageMetricsData(processor="llm", model="gpt-4o", value=usage)])

    async def run():
        from pipecat.processors.frame_processor import FrameDirection
        await step.process_frame(frame, FrameDirection.DOWNSTREAM)

    asyncio.run(run())
    assert lines == [{"event": "ai_turn", "input_tokens": 1500, "output_tokens": 42, "cached_input_tokens": 1024}]
    assert passed == [frame], "every frame is passed on"
