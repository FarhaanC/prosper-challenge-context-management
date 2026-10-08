"""Probe 5: the caller says "a skin check" at the start, then in stage 2 settles on a knee MRI
(the AI simply lists Radiology and calls choose_visit_type, which is what the visit_type stage
tells it to do). The booking card the AI is shown in the booking stage then says
"visit: skin check" next to "Agreed so far: MRI - Knee".
"""
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "backend"))

from call import Clinic, run_tool  # noqa: E402
from clinic import BOOKING, IDENTIFY, VISIT_TYPE, Catalog, PatientDirectory, Schedule  # noqa: E402

cat = Catalog.load()
clinic = Clinic(cat, PatientDirectory.load(), Schedule(cat))
s = clinic.new_call(clock=lambda: datetime(2026, 10, 6, 9))
s.enter_stage(IDENTIFY, [])
run_tool(s, "start_booking", {"full_name": "James Wilson", "returning": True, "date_of_birth": "1984-03-12",
                              "visit_description": "skin check"})
s.enter_stage(VISIT_TYPE, [])
out = run_tool(s, "choose_visit_type", {"visit_type_id": "appt_065"})
assert out.next_stage == BOOKING
print(s.fill("{booking_card}"))
