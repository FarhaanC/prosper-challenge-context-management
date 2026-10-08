"""Probe 6: the caller asked for the soonest time, picked an option, and the time was taken
before confirm_booking. confirm_booking runs card.change_choice("time") to go back to
choosing, and every time change sets soonest = False. The caller's "as soon as possible"
silently disappears, and the next options are no longer the earliest ones.
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
                              "soonest": True, "place": "Richmond"})
s.enter_stage(VISIT_TYPE, [])
run_tool(s, "choose_visit_type", {"visit_type_id": "appt_065"})
s.enter_stage(BOOKING, [])
print("before:", s.card.preferences.soonest, [o.spoken for o in s.card.offered_options])
o = s.card.offered_options[0]
run_tool(s, "choose_option", {"option_id": o.option_id})
clinic.schedule.book(o.provider_id, o.start, 45)          # someone else takes it meanwhile
out = run_tool(s, "confirm_booking", {})
print("confirm:", out.result, out.next_stage)
print("after: soonest =", s.card.preferences.soonest)
print(s.fill("{booking_card}"))
print(s.fill("{options}"))
