"""Shared setup for the round-7 probes. Run from this folder: python3 <probe>.py"""
import sys
from datetime import datetime
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "work" / "backend"
sys.path.insert(0, str(BACKEND))

from clinic import *  # noqa
from clinic import Catalog, Caller, PatientDirectory, Schedule, Preferences, BookingCard, find_options, answer_question  # noqa

NOW = datetime(2026, 10, 6, 9, 0)
catalog = Catalog.load()
NEW = Caller(name="Farhan Jida")
SKIN = "appt_027"


def show(r):
    return [(n.kind, n.say) for n in r.notes], [(o.provider_name, o.location_id) for o in r.options]
