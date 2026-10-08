"""Probe 7.
(a) The AI must send dates as YYYY-MM-DD, but {today} never says the year. What does the AI
    see, and what comes back when it guesses the wrong year for "the 15th"?
(b) The agent file is meant to be editable data, but the tools compare against fixed stage
    names. Rename the first stage "identify" -> "greeting": the file still passes the
    load-time checks, and change_choice in that first stage now skips the identity check.
"""
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "backend"))

from agent_builder import AgentBuilder  # noqa: E402
from call import Clinic, run_tool  # noqa: E402
from clinic import BOOKING, IDENTIFY, VISIT_TYPE, Catalog, PatientDirectory, Schedule  # noqa: E402

AGENT = Path(__file__).resolve().parents[4] / "backend" / "clinic_agent.json"
cat = Catalog.load()
clinic = Clinic(cat, PatientDirectory.load(), Schedule(cat))

# (a)
s = clinic.new_call(clock=lambda: datetime(2026, 10, 6, 9))
print("(a) {today} =", repr(s.fill("{today}")))
s.enter_stage(IDENTIFY, [])
run_tool(s, "start_booking", {"full_name": "Farhan Jida", "returning": False})
s.enter_stage(VISIT_TYPE, [])
run_tool(s, "choose_visit_type", {"visit_type_id": "appt_027"})
s.enter_stage(BOOKING, [])
for guess in ["2024-10-15", "2025-10-15"]:
    print(f"    change_choice(time, days=['{guess}']) ->", run_tool(s, "change_choice", {"what": "time", "days": [guess]}).result)


# (b)
class FM:
    def __init__(self, s):
        self.state = {"session": s}


d = json.loads(AGENT.read_text())
d["nodes"][0]["name"] = "greeting"
d["initial_node"] = "greeting"
b = AgentBuilder.from_dict(d)          # passes every load-time check
s = clinic.new_call(clock=lambda: datetime(2026, 10, 6, 9))
first = b.build_initial_node(s)
change = next(f for f in b.global_functions() if f.name == "change_choice")
out = asyncio.run(change.handler({"what": "time", "days": ["Friday"]}, FM(s)))
moved_to = out[1]["name"] if isinstance(out, tuple) else "stays"
print(f"(b) first stage '{first['name']}': change_choice -> {out[0] if isinstance(out, tuple) else out}, "
      f"moves to: {moved_to}; caller identified: {s.card.caller is not None}")
