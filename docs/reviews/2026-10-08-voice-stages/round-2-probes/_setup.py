"""Shared setup for the round-2 probes. Run each probe from backend/:
    python3 ../docs/reviews/2026-10-08-voice-stages/round-2-probes/<file>.py
"""
import logging
import sys
from datetime import datetime
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[4] / "backend"
sys.path.insert(0, str(BACKEND))
logging.disable(logging.CRITICAL)

from call import Clinic, run_tool  # noqa: E402
from clinic import Catalog, PatientDirectory, Schedule  # noqa: E402

NOW = datetime(2026, 10, 6, 9, 0)  # Tuesday 6 October 2026, 9 AM clinic time
CATALOG = Catalog.load()
NEW = {"full_name": "Farhan Jida", "returning": False}
JAMES = {"full_name": "James Wilson", "returning": True, "date_of_birth": "1984-03-12"}
SKIN = "appt_027"


def clinic():
    return Clinic(CATALOG, PatientDirectory.load(), Schedule(CATALOG))


def call(stage="identify"):
    s = clinic().new_call(clock=lambda: NOW)
    s.enter_stage(stage, [])
    return s


def step(s, tool, args=None):
    out = run_tool(s, tool, dict(args or {}))
    if out.next_stage:
        s.enter_stage(out.next_stage, [])
    return out


def options(s):
    return [f"#{o.option_id} {CATALOG.providers[o.provider_id].name} @ {CATALOG.locations[o.location_id].name} "
            f"{o.start:%a %d %b %H:%M}" for o in s.card.offered_options]


def notes(s):
    return [line for line in s.fill("{options}").splitlines() if line.startswith("- ") and "Option " not in line]
