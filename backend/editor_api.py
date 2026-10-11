#
# The editor's small server (Phase 1). Its routes are added to the voice agent's own
# web server (bot.py), so one program serves the call page (/client), the editor
# (/editor) and these routes (/api/editor/...).
#
#   GET  /api/editor/agent         the agent file as it is on disk
#   POST /api/editor/agent         check an edited agent; save it only if it has no problems
#   GET  /api/editor/tools         the tool registry: what the AI is told, and where each tool can move
#   GET  /api/editor/placeholders  the {placeholders} stage instructions may use
#   GET  /api/editor/calls/latest  the newest call log, for the inspector
#
# Saving uses the same checks the voice agent runs when it loads the file
# (AgentBuilder), so the editor can't save a file the agent would refuse. The agent
# reads the file at the start of every call: save, call, and the change is live.
#

import json
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse

from agent_builder import AgentBuilder, AgentFileProblems
from call import CALL_LOG_DIR, PLACEHOLDERS, TOOLS
from clinic import Catalog

REPLACE_TRIES = 5          # Windows refuses to replace a file another program is reading
REPLACE_WAIT_SECONDS = 0.1  # so wait a moment and try again (a call reads the file in milliseconds)


def problems_with(agent: Any) -> list:
    """Every problem the voice agent would refuse this agent file for (empty if none)."""
    try:
        AgentBuilder.from_dict(agent)
    except AgentFileProblems as e:
        return e.problems
    return []


def editor_routes(agent_file: Path, log_dir: Path = CALL_LOG_DIR, catalog: Optional[Catalog] = None) -> APIRouter:
    """The editor's routes, for the agent file the voice agent runs. `catalog` turns ids on
    the booking card into names for the inspector (the agent passes the one it already has)."""
    catalog = catalog or Catalog.load()
    router = APIRouter(prefix="/api/editor")
    saving = threading.Lock()  # one save at a time

    @router.get("/agent")
    def get_agent():
        return json.loads(agent_file.read_text(encoding="utf-8"))

    @router.post("/agent")
    def save_agent(agent: Any = Body(...)):
        problems = problems_with(agent)
        if problems:
            return JSONResponse({"ok": False, "problems": problems}, status_code=422)
        with saving:
            _write_whole(agent_file, json.dumps(agent, indent=2, ensure_ascii=False) + "\n")
        return {"ok": True}

    @router.get("/tools")
    def get_tools():
        return [{"name": t.name, "description": t.description, "moves_to": list(t.moves_to),
                 "fields": list(t.properties), "required": t.required} for t in TOOLS.values()]

    @router.get("/placeholders")
    def get_placeholders():
        return PLACEHOLDERS

    @router.get("/calls/latest")
    def get_latest_call():
        return latest_call(log_dir, catalog)

    return router


def _write_whole(path: Path, text: str) -> None:
    """Replace the file all at once, so a call starting now reads the old file or the new one,
    never half of one. Keeps the file's line endings (Windows or not), so an unchanged save
    changes nothing."""
    newline = "\r\n" if path.exists() and b"\r\n" in path.read_bytes() else "\n"
    handle, temp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.stem}-", suffix=".saving")
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline=newline) as f:
            f.write(text)
        for attempt in range(REPLACE_TRIES):
            try:
                os.replace(temp, path)
                return
            except PermissionError:
                if attempt == REPLACE_TRIES - 1:
                    raise
                time.sleep(REPLACE_WAIT_SECONDS)
    finally:
        if os.path.exists(temp):
            os.remove(temp)


def _readable(card: dict, catalog: Catalog) -> dict:
    """The booking card with names instead of ids."""
    choices = card.get("choices", {})
    vt, doctor, place = choices.get("visit_type_id"), choices.get("provider_id"), choices.get("location_id")
    return {
        "caller": (card.get("caller") or {}).get("name", ""),
        "new_patient": (card.get("caller") or {}).get("is_new_patient"),
        "wants": card.get("preferences", {}).get("visit_description", ""),
        "visit": catalog.visit_types[vt].name if vt in catalog.visit_types else "",
        "doctor": catalog.providers[doctor].name if doctor in catalog.providers else "",
        "place": catalog.locations[place].name if place in catalog.locations else "",
        "time": choices.get("slot") or "",
        "status": card.get("status", ""),
        "options_on_offer": [o.get("spoken", "") for o in card.get("offered_options", [])],  # the latest offer
    }


def latest_call(log_dir: Path, catalog: Catalog) -> dict:
    """The newest call log: every event, and the latest booking card with names."""
    logs = sorted(Path(log_dir).glob("*.jsonl")) if Path(log_dir).exists() else []
    if not logs:
        return {"file": None, "events": [], "card": None}
    newest = logs[-1]  # file names start with the date and time, so the last is the newest
    events = []
    for line in newest.read_text(encoding="utf-8").splitlines():
        try:
            events.append(json.loads(line))
        except ValueError:
            continue  # the line being written right now; the next poll will have it whole
    card = next((e["card"] for e in reversed(events) if "card" in e), None)
    for e in events:
        e.pop("card", None)  # the inspector shows only the latest card
    return {"file": newest.name, "events": events, "card": _readable(card, catalog) if card else None}
