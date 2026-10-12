"""Helpers for the voice-stage tests (build 349b652, decisions 43-49).

Expected answers come from the plan, the decisions, INTERFACE.md and the raw data
files (via reference.py). Nothing here imports from call/ or agent_builder/ except
the names INTERFACE.md tells a tester to call (Clinic, run_tool, ...), and no
expected value is copied from the code's output.
"""

from __future__ import annotations

import json
import math
import re
from datetime import datetime, timedelta
from pathlib import Path

from reference import DATA, LOC, PROV, RAW, SPECIALTIES, VT, ref_bookable, ref_pairs  # noqa: F401

BACKEND = Path(__file__).resolve().parent.parent
REPO = BACKEND.parent
AGENT_FILE = BACKEND / "clinic_agent.json"
EXTRAS = json.loads((DATA / "location_extras.json").read_text(encoding="utf-8"))
PATIENTS = json.loads((DATA / "patients.json").read_text(encoding="utf-8"))["patients"]
PATIENT = {p["name"]: p for p in PATIENTS}

# Tuesday 6 Oct 2026, 09:00 clinic time (the same "now" as the earlier rounds).
NOW = datetime(2026, 10, 6, 9, 0)

IDENTIFY, VISIT_TYPE, BOOKING, END = "identify", "visit_type", "booking", "end"

# The plan: "a new-patient visit with a family doctor" is the alternative for a refused
# visit. Primary care in the catalog's own words.
PRIMARY_CARE = {"General", "Family Medicine", "Internal Medicine"}

SKIN_CHECK = "appt_027"      # Skin Cancer Screening (Dermatology, no referral, open to new)
KNEE_MRI = "appt_065"        # MRI - Knee (Radiology, referral, existing patients only, imaging)
GARCIAS = {pid for pid, p in PROV.items() if p["name"].split()[-1] == "Garcia"}
CHENS = {pid for pid, p in PROV.items() if p["name"].split()[-1] == "Chen"}

# Decisions 77-78 (11 Oct): a new patient's name is saved from the letters the caller
# confirmed, so a new patient's start_booking carries both spelled names. The letters
# spell the same name as before, so every expected "Farhan Jida" still holds.
NEW = {"full_name": "Farhan Jida", "returning": False,
       "spelled_first_name": "F, A, R, H, A, N", "spelled_last_name": "J, I, D, A"}
JAMES = {"full_name": "James Wilson", "returning": True, "date_of_birth": PATIENT["James Wilson"]["date_of_birth"]}


# ------------------------------------------------------------------ geography
def miles(a, b):
    """Great-circle distance in miles between two (lat, lon) points."""
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 3958.8 * 2 * math.asin(math.sqrt(h))


def loc_point(lid):
    e = EXTRAS["locations"][lid]
    return (e["lat"], e["lon"])


def landmark(name):
    return tuple(EXTRAS["landmarks"][name])


# ------------------------------------------------------------------ times
def spoken(dt: datetime) -> str:
    """My own spoken form: 'Wednesday 7 October at 9:30 AM' / 'at 11 AM'."""
    hour = dt.hour % 12 or 12
    clock = f"{hour}:{dt.minute:02d}" if dt.minute else f"{hour}"
    return f"{dt:%A} {dt.day} {dt:%B} at {clock} {'AM' if dt.hour < 12 else 'PM'}"


def overlaps(a_start, a_min, b_start, b_min):
    return a_start < b_start + timedelta(minutes=b_min) and b_start < a_start + timedelta(minutes=a_min)


# ------------------------------------------------------------------ a call
def make_clinic(catalog, directory, bookings_file=None, log_dir=None, patients=None):
    from call import Clinic
    from clinic import Schedule
    return Clinic(catalog, patients or directory, Schedule(catalog), bookings_file=bookings_file, log_dir=log_dir)


def new_call(clinic, now=NOW):
    s = clinic.new_call(clock=lambda: now)
    s.enter_stage(IDENTIFY, [])
    return s


def step(session, tool, args=None):
    """Run one tool as the voice agent would, and enter the next stage if it moves."""
    from call import run_tool
    out = run_tool(session, tool, dict(args or {}))
    if out.next_stage:
        session.enter_stage(out.next_stage, [])
    return out


def snapshot(session):
    """Everything about the call that a refused tool call must leave alone."""
    return session.stage, json.dumps(session.card.to_dict(), sort_keys=True, default=str)


def offered(session):
    return [(o.option_id, o.provider_id, o.location_id, o.start) for o in session.card.offered_options]


def to_visit_type(clinic, who=NEW, **wishes):
    s = new_call(clinic)
    out = step(s, "start_booking", {**who, **wishes})
    assert out.result.get("ok") is True and s.stage == VISIT_TYPE, out.result
    return s


def to_booking(clinic, vt=SKIN_CHECK, who=NEW, **wishes):
    s = to_visit_type(clinic, who, **wishes)
    out = step(s, "choose_visit_type", {"visit_type_id": vt})
    assert out.result.get("ok") is True and s.stage == BOOKING, out.result
    assert s.card.offered_options, "no options on offer after choose_visit_type"
    return s


def result_text(result) -> str:
    """Every string in a tool result, joined: where an instruction for the AI would be."""
    out = []

    def walk(x):
        if isinstance(x, str):
            out.append(x)
        elif isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, (list, tuple)):
            for v in x:
                walk(v)
    walk(result)
    return " ".join(out)


# ------------------------------------------------------------------ the {options} text
OPTION_LINE = re.compile(r"^\s*-?\s*Option (\d+):\s*(.*)$")


def option_lines(text):
    """{number: rest of line} for every 'Option N:' line."""
    found = {}
    for line in text.splitlines():
        m = OPTION_LINE.match(line)
        if m:
            found[m.group(1)] = m.group(2)
    return found


def section(text, heading_start):
    """The bullet lines under the heading that starts with `heading_start`, up to the next heading."""
    lines, inside = [], False
    for line in text.splitlines():
        if line.startswith(heading_start):
            inside = True
            continue
        if inside:
            if line.startswith("- "):
                lines.append(line[2:])
            elif line.strip():
                inside = False
    return lines


# ------------------------------------------------------------------ INTERFACE.md
def interface_tools():
    """Each tool as INTERFACE.md shows it: {name: (description, required, moves_to, properties)}."""
    text = (REPO / "INTERFACE.md").read_text(encoding="utf-8")
    part = text.split("## Tools (exactly what the AI is shown)", 1)[1]
    tools = {}
    for block in re.split(r"^### ", part, flags=re.M)[1:]:
        name, rest = block.split("\n", 1)
        desc, rest = rest.strip().split("\n\nRequired:", 1)
        req_text, rest = rest.split(". Can move to:", 1)
        required = [] if req_text.strip() == "none" else json.loads(req_text.strip().replace("'", '"'))
        moves_text, rest = rest.split("\n", 1)
        moves_text = moves_text.strip().rstrip(".")
        moves = [] if moves_text == "stays" else json.loads(moves_text.replace("'", '"'))
        props = json.loads(rest.split("```json", 1)[1].split("```", 1)[0])
        tools[name.strip()] = (desc.strip(), required, moves, props)
    return tools
