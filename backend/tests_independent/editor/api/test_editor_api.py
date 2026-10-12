"""Independent tests of the editor's server routes (Phase 1 plan, items 4 and 6).

Expected answers come from the plan, the decisions, the raw agent file, the raw
catalog.json and call logs, not from what the routes return.
Every test works on a temporary copy of the agent file and a temporary log folder.

The inspector tests used to copy the machine's real backend/call_logs/ and expect one
particular file to be the newest. That broke as soon as a newer call was made (or on a
machine with no call logs). They now make their own call logs with the real call code in
a temporary folder the test controls (fixture real_logs), so the result no longer depends
on which calls happen to have been made on the machine.
"""

import copy
import json
import shutil
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from editor_api import editor_routes

BACKEND = Path(__file__).resolve().parents[3]
REAL_AGENT = BACKEND / "clinic_agent.json"
RAW_CATALOG = json.loads((BACKEND / "data" / "catalog.json").read_text(encoding="utf-8"))


def raw_name(kind: str, id_: str) -> str:
    return next(x["name"] for x in RAW_CATALOG[kind] if x["id"] == id_)


@pytest.fixture
def agent_file(tmp_path):
    """A copy of the real agent file with plain (LF) line endings, as git stores it."""
    text = REAL_AGENT.read_bytes().replace(b"\r\n", b"\n")
    f = tmp_path / "clinic_agent.json"
    f.write_bytes(text)
    return f


@pytest.fixture
def log_dir(tmp_path):
    d = tmp_path / "call_logs"
    d.mkdir()
    return d


def client_for(agent_file: Path, log_dir: Path) -> TestClient:
    app = FastAPI()
    app.include_router(editor_routes(agent_file, log_dir))
    return TestClient(app)


@pytest.fixture
def client(agent_file, log_dir):
    return client_for(agent_file, log_dir)


@pytest.fixture
def agent(agent_file):
    return json.loads(agent_file.read_text(encoding="utf-8"))


def stage(agent: dict, name: str) -> dict:
    return next(n for n in agent["nodes"] if n["name"] == name)


# ------------------------------------------------------------------ loading
def test_load_returns_the_agent_file_as_it_is(client, agent):
    r = client.get("/api/editor/agent")
    assert r.status_code == 200
    assert r.json() == agent


def test_load_keeps_keys_order(client, agent):
    assert list(client.get("/api/editor/agent").json()) == list(agent)


# ------------------------------------------------------------------ saving
def test_save_an_edited_instruction_writes_it(client, agent_file, agent):
    edited = copy.deepcopy(agent)
    stage(edited, "visit_type")["task_messages"][0]["content"] += "\nSay 'lovely' once."
    r = client.post("/api/editor/agent", json=edited)
    assert r.status_code == 200
    assert r.json()["ok"] is True
    on_disk = json.loads(agent_file.read_text(encoding="utf-8"))
    assert on_disk == edited
    assert stage(on_disk, "visit_type")["task_messages"][0]["content"].endswith("Say 'lovely' once.")


def test_saved_file_is_what_load_returns_next(client, agent):
    edited = copy.deepcopy(agent)
    edited["persona"] = edited["persona"] + " Be brief."
    client.post("/api/editor/agent", json=edited)
    assert client.get("/api/editor/agent").json() == edited


def test_saving_unchanged_agent_leaves_file_byte_for_byte_same(client, agent_file, agent):
    before = agent_file.read_bytes()
    r = client.post("/api/editor/agent", json=agent)
    assert r.status_code == 200
    assert agent_file.read_bytes() == before


def test_saving_unchanged_agent_with_windows_line_endings(tmp_path, log_dir):
    """The agent file handed over has CRLF line endings (as do the call logs, written on
    the owner's machine). On this Linux test machine the save writes LF endings."""
    f = tmp_path / "crlf_agent.json"
    shutil.copy(REAL_AGENT, f)
    before = f.read_bytes()
    assert b"\r\n" in before
    c = client_for(f, log_dir)
    c.post("/api/editor/agent", json=json.loads(before))
    assert f.read_bytes() == before


def test_saved_file_with_non_english_text_reads_back(client, agent_file, agent):
    edited = copy.deepcopy(agent)
    edited["persona"] += " Say “olé” and café properly."
    assert client.post("/api/editor/agent", json=edited).status_code == 200
    assert json.loads(agent_file.read_text(encoding="utf-8"))["persona"].endswith("café properly.")


def test_saved_file_loads_in_the_voice_agent(client, agent_file, agent):
    """Save, then the agent's own loader (AgentBuilder.from_json, used by bot.py per call) accepts it."""
    from agent_builder import AgentBuilder
    edited = copy.deepcopy(agent)
    stage(edited, "end")["task_messages"][0]["content"] += " Thank them."
    client.post("/api/editor/agent", json=edited)
    AgentBuilder.from_json(agent_file)


def test_no_leftover_temp_file_after_save(client, agent_file, agent):
    client.post("/api/editor/agent", json=agent)
    assert sorted(p.name for p in agent_file.parent.iterdir()) == sorted(["clinic_agent.json", "call_logs"])


# ------------------------------------------------------------------ broken agents
def _broken(agent, how):
    a = copy.deepcopy(agent)
    how(a)
    return a


def _arrow_to_missing(a):
    stage(a, "identify")["edges"] = [{"function": "go_on", "description": "Go on.", "target": "nowhere"}]


def _delete_start(a):
    a["nodes"] = [n for n in a["nodes"] if n["name"] != "identify"]


def _start_points_nowhere(a):
    a["initial_node"] = "lobby"


def _unknown_stage_tool(a):
    stage(a, "booking")["tools"].append("teleport")


def _unknown_global_tool(a):
    a["global_tools"].append("fax_the_doctor")


def _delete_stage_tools_move_to(a):
    a["nodes"] = [n for n in a["nodes"] if n["name"] != "end"]


def _rename_stage_tools_move_to(a):
    stage(a, "booking")["name"] = "options"


def _two_stages_same_name(a):
    stage(a, "end")["name"] = "booking"


def _unknown_agent_key(a):
    a["colour"] = "blue"


def _unknown_stage_key(a):
    stage(a, "booking")["tool"] = ["choose_option"]


def _unknown_arrow_key(a):
    stage(a, "identify")["edges"] = [{"function": "go", "description": "d", "target": "end", "goes": "end"}]


def _arrow_missing_description(a):
    stage(a, "identify")["edges"] = [{"function": "go", "target": "end"}]


def _unknown_placeholder(a):
    stage(a, "booking")["task_messages"][0]["content"] += " {booking card}"


def _placeholder_in_persona(a):
    a["persona"] += " Today is {today}."


def _doubled_braces(a):
    stage(a, "end")["task_messages"][0]["content"] += " {{today}}"


def _bad_history(a):
    a["history"] = "forget"


def _parallel_not_bool(a):
    a["parallel_tool_calls"] = "no"


def _tool_in_stage_and_global(a):
    stage(a, "booking")["tools"].append("hand_off")


def _tool_listed_twice(a):
    stage(a, "booking")["tools"].append("choose_option")


def _no_stages(a):
    a["nodes"] = []


def _stage_without_name(a):
    del stage(a, "end")["name"]


def _instructions_not_text(a):
    stage(a, "end")["task_messages"][0]["content"] = 42


def _respond_immediately_not_bool(a):
    stage(a, "identify")["respond_immediately"] = "false"


def _no_tools_with_one_at_a_time(a):
    a["global_tools"] = []


BROKEN = [
    ("arrow to a missing stage", _arrow_to_missing, ["nowhere"]),
    ("start stage deleted", _delete_start, ["identify"]),
    ("start stage name points nowhere", _start_points_nowhere, ["lobby"]),
    ("unknown tool in a stage", _unknown_stage_tool, ["teleport"]),
    ("unknown always-available tool", _unknown_global_tool, ["fax_the_doctor"]),
    ("stage deleted that tools move to", _delete_stage_tools_move_to, ["end"]),
    ("stage renamed that tools move to", _rename_stage_tools_move_to, ["booking"]),
    ("two stages with one name", _two_stages_same_name, ["booking"]),
    ("unknown key on the agent", _unknown_agent_key, ["colour"]),
    ("unknown key on a stage", _unknown_stage_key, ["tool"]),
    ("unknown key on an arrow", _unknown_arrow_key, ["goes"]),
    ("arrow without 'when to use it'", _arrow_missing_description, ["description"]),
    ("unknown placeholder", _unknown_placeholder, ["booking card"]),
    ("placeholder in the persona", _placeholder_in_persona, ["today"]),
    ("doubled braces", _doubled_braces, ["braces"]),
    ("bad history setting", _bad_history, ["forget"]),
    ("one-at-a-time setting not yes/no", _parallel_not_bool, ["parallel_tool_calls"]),
    ("tool in a stage and always available", _tool_in_stage_and_global, ["hand_off"]),
    ("tool listed twice", _tool_listed_twice, ["choose_option"]),
    ("no stages at all", _no_stages, []),
    ("stage without a name", _stage_without_name, ["name"]),
    ("instructions that aren't text", _instructions_not_text, ["task_messages"]),
    ("respond_immediately not yes/no", _respond_immediately_not_bool, ["respond_immediately"]),
    ("a stage with no tools while one-at-a-time is on", _no_tools_with_one_at_a_time, ["end"]),
]


@pytest.mark.parametrize("label,how,mentions", BROKEN, ids=[b[0] for b in BROKEN])
def test_broken_agent_is_refused_and_file_untouched(client, agent_file, agent, label, how, mentions):
    before = agent_file.read_bytes()
    r = client.post("/api/editor/agent", json=_broken(agent, how))
    assert r.status_code == 422, r.text
    body = r.json()
    assert body["ok"] is False
    problems = body["problems"]
    assert isinstance(problems, list) and problems
    assert all(isinstance(p, str) and p.strip() for p in problems)
    # Problems are sentences, not a Python traceback or a bullet-prefixed blob.
    assert not any(p.startswith("- ") or "Traceback" in p or "\n" in p for p in problems)
    text = " ".join(problems)
    for word in mentions:
        assert word in text, f"{label}: {problems}"
    assert agent_file.read_bytes() == before
    assert not list(agent_file.parent.glob("*.saving"))


def test_all_problems_are_listed_at_once(client, agent):
    a = _broken(agent, _arrow_to_missing)
    _unknown_stage_tool(a)
    _start_points_nowhere(a)
    problems = client.post("/api/editor/agent", json=a).json()["problems"]
    text = " ".join(problems)
    assert "nowhere" in text and "teleport" in text and "lobby" in text
    assert len(problems) >= 3


@pytest.mark.parametrize("label,how,mentions", [b for b in BROKEN if b[0] in (
    "arrow to a missing stage", "start stage deleted", "stage deleted that tools move to",
    "two stages with one name", "unknown key on a stage")], ids=lambda x: x if isinstance(x, str) else "")
def test_problems_use_the_editors_words(client, agent, label, how, mentions):
    """Plan item 4: errors 'in plain words'. The editor calls them stages, arrows and tools;
    the file's internal words (node, edge, initial_node, global_tools) shouldn't leak."""
    problems = client.post("/api/editor/agent", json=_broken(agent, how)).json()["problems"]
    jargon = ("node", "edge", "initial_node", "global_tools")
    leaked = [p for p in problems if any(j in p.lower() for j in jargon)]
    assert not leaked, leaked


def test_list_of_unhashable_tool_names_is_refused_in_plain_words(client, agent_file, agent):
    a = copy.deepcopy(agent)
    stage(a, "booking")["tools"] = [["choose_option"]]
    before = agent_file.read_bytes()
    r = client.post("/api/editor/agent", json=a)
    assert r.status_code == 422
    assert agent_file.read_bytes() == before
    assert not any("unhashable" in p or "malformed" in p for p in r.json()["problems"]), r.json()


def test_non_object_body_gets_the_same_answer_shape(client, agent_file):
    """The page treats every 422 as {ok: false, problems: [...]}."""
    before = agent_file.read_bytes()
    r = client.post("/api/editor/agent", json=["not", "an", "agent"])
    assert r.status_code == 422
    assert agent_file.read_bytes() == before
    assert "problems" in r.json(), r.json()


# ------------------------------------------------------------------ tool registry
# What tools.py's own header table and the decisions say each tool can move to.
EXPECTED_MOVES = {
    "start_booking": {"visit_type", "end"},
    "list_visit_types": set(),
    "choose_visit_type": {"booking"},
    "choose_option": set(),
    "confirm_booking": {"end", "booking"},
    "change_choice": {"booking", "visit_type"},
    "turn_down_doctors": {"booking", "visit_type"},
    "answer_question": set(),
    "hand_off": {"end"},
}


def test_tool_route_lists_every_registry_tool(client):
    from call import TOOLS
    tools = client.get("/api/editor/tools").json()
    assert [t["name"] for t in tools] == list(TOOLS)
    for t in tools:
        reg = TOOLS[t["name"]]
        assert t["description"] == reg.description
        assert set(t["moves_to"]) == set(reg.moves_to)
        assert set(t["fields"]) == set(reg.properties)
        assert t["required"] == list(reg.required)


def test_tool_route_moves_match_the_documented_table(client):
    tools = {t["name"]: set(t["moves_to"]) for t in client.get("/api/editor/tools").json()}
    assert tools == EXPECTED_MOVES


def test_placeholders_route(client):
    p = client.get("/api/editor/placeholders").json()
    for name in ("booking_card", "options", "specialties", "today", "outcome", "visit_types", "just_happened"):
        assert name in p and isinstance(p[name], str) and p[name]


# ------------------------------------------------------------------ inspector
def test_inspector_with_no_log_folder(tmp_path, agent_file):
    c = client_for(agent_file, tmp_path / "does_not_exist")
    r = c.get("/api/editor/calls/latest")
    assert r.status_code == 200
    assert r.json() == {"file": None, "events": [], "card": None}


def test_inspector_with_empty_log_folder(client):
    assert client.get("/api/editor/calls/latest").json() == {"file": None, "events": [], "card": None}


NEWEST_LOG = "20261010-184339-8e2ba6.jsonl"   # the name the old real newest log had
OLDER_LOG = "20261010-151208-3c91d0.jsonl"    # an earlier call the same day


@pytest.fixture
def real_logs(tmp_path):
    """A folder of call logs written by the real call code, in place of backend/call_logs/.

    The newest is the call the old real log held (10 Oct, 18:43): new patient Zoya Chida,
    New Patient Consultation, afternoon, booked option 2. The older one is a call handed to
    staff. Each is renamed to a fixed name: the clinic names a log by the moment it opens it,
    so the names, and so which log is newest, are set by the test, not by the machine.
    """
    from datetime import datetime
    from call import Clinic, run_tool

    made, out = tmp_path / "made", tmp_path / "real_logs"
    out.mkdir()
    clinic = Clinic.load(bookings_file=None, log_dir=made)

    def run(now, steps):
        s = clinic.new_call(clock=lambda: now)
        s.enter_stage("identify", ["Greet the caller."])
        for tool, args in steps:
            o = run_tool(s, tool, args)
            assert o.result.get("ok") is True, (tool, o.result)
            if o.next_stage:
                s.enter_stage(o.next_stage, [f"Stage {o.next_stage}."])
        return s.log_path

    older = run(datetime(2026, 10, 10, 15, 12), [("hand_off", {"reason": "cancel"})])
    older.rename(out / OLDER_LOG)
    newest = run(datetime(2026, 10, 10, 18, 43), [
        # Decisions 77-78: a new patient's name is saved from the confirmed letters.
        ("start_booking", {"full_name": "Zoya Chida", "returning": False,
                           "spelled_first_name": "Z, O, Y, A", "spelled_last_name": "C, H, I, D, A"}),
        ("list_visit_types", {"specialty": "General"}),
        ("choose_visit_type", {"visit_type_id": "appt_000", "time_of_day": "afternoon"}),
        ("choose_option", {"option_id": "2"}),
        ("confirm_booking", {}),
    ])
    newest.rename(out / NEWEST_LOG)
    return out


def _copy_real_logs(real_logs, log_dir):
    for f in real_logs.glob("*.jsonl"):
        shutil.copy(f, log_dir / f.name)


def test_inspector_newest_log_wins(client, log_dir, real_logs):
    _copy_real_logs(real_logs, log_dir)
    body = client.get("/api/editor/calls/latest").json()
    assert body["file"] == NEWEST_LOG
    raw_lines = (real_logs / body["file"]).read_text(encoding="utf-8").splitlines()
    older_lines = (real_logs / OLDER_LOG).read_text(encoding="utf-8").splitlines()
    # The old real log had 13 lines (it also held lines bot.py writes); this one is made
    # by the call code alone: a stage line per stage and a tool line per tool call.
    assert len(body["events"]) == len(raw_lines) == 1 + 5 + 3
    assert len(older_lines) != len(raw_lines), "the two logs must be told apart"


def test_inspector_newer_call_replaces_older(client, log_dir, real_logs):
    _copy_real_logs(real_logs, log_dir)
    assert client.get("/api/editor/calls/latest").json()["file"] == NEWEST_LOG
    newer = log_dir / "20261011-090000-abcdef.jsonl"
    newer.write_text(json.dumps({"at": "2026-10-11T09:00:00", "event": "stage", "stage": "identify",
                                 "instructions": ["hi"], "card": {"status": "in_progress"}}) + "\n")
    body = client.get("/api/editor/calls/latest").json()
    assert body["file"] == newer.name
    assert [e["event"] for e in body["events"]] == ["stage"]


def test_inspector_events_keep_order_and_drop_card(client, log_dir, real_logs):
    _copy_real_logs(real_logs, log_dir)
    body = client.get("/api/editor/calls/latest").json()
    raw = [json.loads(l) for l in (real_logs / body["file"]).read_text(encoding="utf-8").splitlines()]
    assert len(body["events"]) == len(raw)
    for got, want in zip(body["events"], raw):
        want = dict(want)
        want.pop("card")
        assert got == want


def test_inspector_card_from_the_real_newest_log(client, log_dir, real_logs):
    _copy_real_logs(real_logs, log_dir)
    card = client.get("/api/editor/calls/latest").json()["card"]
    assert card["caller"] == "Zoya Chida"
    assert card["new_patient"] is True
    assert card["visit"] == raw_name("appointment_types", "appt_000") == "New Patient Consultation"
    assert card["doctor"] == raw_name("providers", "prov_032")
    assert card["place"] == raw_name("locations", "loc_007")
    assert card["time"] == "2026-10-12T13:00:00"
    assert card["status"] == "booked"
    assert len(card["options_on_offer"]) == 3
    assert any("Dr. Michael Sato" in o for o in card["options_on_offer"])


def test_inspector_card_before_the_caller_is_known(client, log_dir):
    (log_dir / "20261011-100000-aaaaaa.jsonl").write_text(json.dumps({
        "at": "2026-10-11T10:00:00", "event": "stage", "stage": "identify", "instructions": ["x"],
        "card": {"caller": None, "preferences": {"visit_description": ""}, "choices": {}, "status": "in_progress",
                 "offered_options": []}}) + "\n")
    card = client.get("/api/editor/calls/latest").json()["card"]
    assert card["caller"] == ""
    assert card["doctor"] == "" and card["place"] == "" and card["visit"] == ""
    assert card["status"] == "in_progress"
    assert card["options_on_offer"] == []


def test_inspector_skips_a_half_written_last_line(client, log_dir, real_logs):
    src = real_logs / NEWEST_LOG
    lines = src.read_text(encoding="utf-8").splitlines()
    f = log_dir / "20261011-120000-bbbbbb.jsonl"
    f.write_text("\n".join(lines[:5]) + "\n" + lines[5][: len(lines[5]) // 2], encoding="utf-8")
    body = client.get("/api/editor/calls/latest").json()
    assert body["file"] == f.name
    assert len(body["events"]) == 5
    # The card is the one on the last whole line.
    assert body["card"]["status"] == json.loads(lines[4])["card"]["status"]


def test_inspector_uses_latest_card_not_first(client, log_dir, real_logs):
    src = real_logs / NEWEST_LOG
    lines = src.read_text(encoding="utf-8").splitlines()
    f = log_dir / "20261011-130000-cccccc.jsonl"
    f.write_text("\n".join(lines[:5]) + "\n", encoding="utf-8")
    card = client.get("/api/editor/calls/latest").json()["card"]
    # After line 5 (choose_visit_type accepted), the visit is chosen but no doctor yet.
    assert card["visit"] == "New Patient Consultation"
    assert card["doctor"] == ""
    assert card["status"] == "in_progress"


def test_inspector_sees_a_line_appended_later(client, log_dir):
    f = log_dir / "20261011-140000-dddddd.jsonl"
    f.write_text(json.dumps({"at": "t", "event": "stage", "stage": "identify", "instructions": []}) + "\n")
    assert len(client.get("/api/editor/calls/latest").json()["events"]) == 1
    with f.open("a") as fh:
        fh.write(json.dumps({"at": "t", "event": "ai_turn", "input_tokens": 1200, "output_tokens": 30,
                             "cached_input_tokens": 0}) + "\n")
    events = client.get("/api/editor/calls/latest").json()["events"]
    assert [e["event"] for e in events] == ["stage", "ai_turn"]


# ------------------------------------------------------------------ token lines
def test_token_lines_come_through_the_inspector_route(client, log_dir):
    """A session's log gets ai_turn lines (decision 45) and the route returns them with their numbers."""
    from call import Clinic
    clinic = Clinic.load(bookings_file=None, log_dir=log_dir)
    session = clinic.new_call()
    session.enter_stage("identify", ["hello"])
    session.log({"event": "ai_turn", "input_tokens": 1834, "output_tokens": 41, "cached_input_tokens": 1024})
    events = client.get("/api/editor/calls/latest").json()["events"]
    turns = [e for e in events if e["event"] == "ai_turn"]
    assert turns == [{"at": turns[0]["at"], "event": "ai_turn", "input_tokens": 1834, "output_tokens": 41,
                      "cached_input_tokens": 1024}]


def _run_token_log(frames):
    import asyncio
    from pipecat.tests.utils import run_test
    from agent_builder import TokenLog
    written = []
    down, _ = asyncio.run(run_test(TokenLog(written.append), frames_to_send=frames))
    # Every frame is passed on (usage notes are "system" frames, so Pipecat may reorder them).
    assert sorted(type(f).__name__ for f in down) == sorted(type(f).__name__ for f in frames)
    return written


def _usage(prompt, completion, cached=None):
    from pipecat.metrics.metrics import LLMTokenUsage, LLMUsageMetricsData
    return LLMUsageMetricsData(processor="llm", model="gpt-4o", value=LLMTokenUsage(
        prompt_tokens=prompt, completion_tokens=completion, total_tokens=prompt + completion,
        cache_read_input_tokens=cached))


def test_token_log_writes_one_line_per_usage_note_and_passes_frames_on():
    from pipecat.frames.frames import MetricsFrame, TextFrame
    written = _run_token_log([MetricsFrame(data=[_usage(1500, 20)]), TextFrame("hi"),
                              MetricsFrame(data=[_usage(1700, 12, cached=1024)])])
    assert written == [
        {"event": "ai_turn", "input_tokens": 1500, "output_tokens": 20, "cached_input_tokens": 0},
        {"event": "ai_turn", "input_tokens": 1700, "output_tokens": 12, "cached_input_tokens": 1024},
    ]


def test_token_log_ignores_other_metrics():
    from pipecat.frames.frames import MetricsFrame
    from pipecat.metrics.metrics import ProcessingMetricsData, TTFBMetricsData, TTSUsageMetricsData
    written = _run_token_log([MetricsFrame(data=[TTFBMetricsData(processor="llm", value=0.4),
                                                 ProcessingMetricsData(processor="stt", value=0.1),
                                                 TTSUsageMetricsData(processor="tts", value=42)])])
    assert written == []


# ------------------------------------------------------------------ a call starting while saving
def test_a_call_starting_during_saves_never_reads_half_a_file(client, agent_file, agent):
    """bot.py reads the agent file at the start of every call (AgentBuilder.from_json).
    While the editor saves over and over, every read must get a whole, valid agent."""
    import threading
    from agent_builder import AgentBuilder
    stop, failures, reads = threading.Event(), [], [0]

    def keep_starting_calls():
        while not stop.is_set():
            try:
                AgentBuilder.from_json(agent_file)
                reads[0] += 1
            except Exception as e:  # noqa: BLE001 - any failure is the finding
                failures.append(repr(e))

    t = threading.Thread(target=keep_starting_calls)
    t.start()
    try:
        for i in range(150):
            a = copy.deepcopy(agent)
            a["persona"] += " x" * (i % 7) + " " + "y" * (i * 37 % 5000)
            assert client.post("/api/editor/agent", json=a).status_code == 200
    finally:
        stop.set()
        t.join()
    assert reads[0] > 0
    assert failures == []


# ------------------------------------------------------------------ beyond the plan's list
# These are agents the save accepts (and the voice agent's loader accepts too) but that the
# AI service can't run. The editor makes them easy to create: a dragged arrow is named
# "go_to_<stage name>", and stage names and arrow names are free text.
def test_arrow_name_with_a_space_is_refused(client, agent):
    a = copy.deepcopy(agent)
    stage(a, "identify")["edges"] = [{"function": "go_to_new stage 1", "description": "d", "target": "end"}]
    assert client.post("/api/editor/agent", json=a).status_code == 422


def test_empty_arrow_name_is_refused(client, agent):
    a = copy.deepcopy(agent)
    stage(a, "identify")["edges"] = [{"function": "", "description": "d", "target": "end"}]
    assert client.post("/api/editor/agent", json=a).status_code == 422


def test_two_arrows_with_one_name_in_a_stage_are_refused(client, agent):
    a = copy.deepcopy(agent)
    stage(a, "identify")["edges"] = [{"function": "go_to_end", "description": "d", "target": "end"},
                                     {"function": "go_to_end", "description": "d", "target": "booking"}]
    assert client.post("/api/editor/agent", json=a).status_code == 422


def test_arrow_named_like_a_tool_is_refused(client, agent):
    a = copy.deepcopy(agent)
    stage(a, "booking")["edges"] = [{"function": "hand_off", "description": "d", "target": "end"}]
    assert client.post("/api/editor/agent", json=a).status_code == 422
