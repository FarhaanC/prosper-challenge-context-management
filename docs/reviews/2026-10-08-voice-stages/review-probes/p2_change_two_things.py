"""Probe 2: in the booking stage the caller says "Can I see Dr. Kim on Friday instead?"
(or "Friday afternoon at Midtown"). The AI can only send one change_choice call, because
the call moves the stage and the reset wipes what the caller said. Does the tool keep
the second wish if the AI sends it in the same call, or refuse it? Neither: it is dropped.
"""
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "backend"))

from call import Clinic, run_tool  # noqa: E402
from clinic import BOOKING, IDENTIFY, Catalog, PatientDirectory, Schedule  # noqa: E402

NOW = datetime(2026, 10, 6, 9, 0)


def at_booking(clinic):
    s = clinic.new_call(clock=lambda: NOW)
    s.enter_stage(IDENTIFY, [])
    run_tool(s, "start_booking", {"full_name": "Farhan Jida", "returning": False})
    s.enter_stage("visit_type", [])
    assert run_tool(s, "choose_visit_type", {"visit_type_id": "appt_027"}).next_stage == BOOKING
    s.enter_stage(BOOKING, [])
    return s


cat = Catalog.load()
clinic = Clinic(cat, PatientDirectory.load(), Schedule(cat))

for args in [
    {"what": "doctor", "new_value": "Dr. Kenji Kim", "days": ["Friday"]},
    {"what": "location", "new_value": "Midtown", "days": ["Friday"], "time_of_day": "afternoon"},
    {"what": "language", "new_value": "Spanish", "time_of_day": "morning"},
    {"what": "visit_type", "new_value": "mole removal", "days": ["Friday"]},
]:
    s = at_booking(clinic)
    out = run_tool(s, "change_choice", args)
    p = s.card.preferences
    print(f"change_choice{args}\n  -> {out.result}, next stage {out.next_stage}")
    print(f"  card days={p.days} time_of_day={p.time_of_day!r}")
    days = sorted({o.start.strftime('%A %p') for o in s.card.offered_options})
    print(f"  options now on offer: {days}\n")
