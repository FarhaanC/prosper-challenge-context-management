"""Shared setup for the round-6 probes. Run each probe from this folder: python3 p1_x.py"""
import copy, json, sys
from datetime import datetime
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "work" / "backend"
sys.path.insert(0, str(BACKEND))
from clinic import *  # noqa
from clinic import Catalog, Schedule, Caller, Preferences, BookingCard, Choices, find_options  # noqa

RAW = json.loads((BACKEND / "data" / "catalog.json").read_text())
EXTRAS = json.loads((BACKEND / "data" / "location_extras.json").read_text())
NOW = datetime(2026, 10, 6, 9, 0)  # Tuesday
catalog = Catalog(RAW, EXTRAS)
schedule = Schedule(catalog)
NEW = Caller(name="Test New")
def says(r): return [(n.kind, n.say) for n in r.notes]
