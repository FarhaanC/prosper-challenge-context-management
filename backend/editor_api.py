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
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from agent_builder import AgentBuilder
from call import CALL_LOG_DIR, PLACEHOLDERS, TOOLS
from clinic import Catalog

_catalog = None


def _names():
    """The catalog, loaded once, to turn ids on the booking card into names for the inspector."""
    global _catalog
    if _catalog is None:
        _catalog = Catalog.load()
    return _catalog


def problems_with(agent: dict) -> list:
    """Every problem the voice agent would refuse this agent file for (empty if none)."""
    try:
        AgentBuilder.from_dict(agent)
    except ValueError as e:
        lines = str(e).splitlines()
        return [line.removeprefix("- ") for line in lines[1:]] or lines
    except (KeyError, TypeError) as e:  # a shape the checks didn't expect
        return [f"The agent file is malformed: {e}"]
    return []


def editor_routes(agent_file: Path, log_dir: Path = CALL_LOG_DIR) -> APIRouter:
    """The editor's routes, for the agent file the voice agent runs."""
    router = APIRouter(prefix="/api/editor")

    @router.get("/agent")
    def get_agent():
        return json.loads(agent_file.read_text(encoding="utf-8"))

    @router.post("/agent")
    def save_agent(agent: dict):
        problems = problems_with(agent)
        if problems:
            return JSONResponse({"ok": False, "problems": problems}, status_code=422)
        temp = agent_file.with_suffix(".saving")
        temp.write_text(json.dumps(agent, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(temp, agent_file)  # all or nothing: a call starting now never reads half a file
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
        return latest_call(log_dir)

    return router


def _readable(card: dict) -> dict:
    """The booking card with names instead of ids."""
    c, choices = _names(), card.get("choices", {})
    vt, doctor, place = choices.get("visit_type_id"), choices.get("provider_id"), choices.get("location_id")
    return {
        "caller": (card.get("caller") or {}).get("name", ""),
        "new_patient": (card.get("caller") or {}).get("is_new_patient"),
        "wants": card.get("preferences", {}).get("visit_description", ""),
        "visit": c.visit_types[vt].name if vt in c.visit_types else "",
        "doctor": c.providers[doctor].name if doctor in c.providers else "",
        "place": c.locations[place].name if place in c.locations else "",
        "time": choices.get("slot") or "",
        "status": card.get("status", ""),
        "options_on_offer": [o.get("spoken", "") for o in card.get("offered_options", [])],
    }


def latest_call(log_dir: Path) -> dict:
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
    return {"file": newest.name, "events": events, "card": _readable(card) if card else None}
