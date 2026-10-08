"""Probe 4: send each tool odd but plausible values (what gpt-4o might send) at the booking
stage and the visit_type stage. Report (a) any exception that escapes run_tool (in the voice
call Pipecat turns it into {"status": "error", ...} and the call log gets no line), and
(b) any reply with ok false that still changed the booking card.
"""
import copy
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "backend"))

from call import Clinic, run_tool  # noqa: E402
from clinic import BOOKING, IDENTIFY, VISIT_TYPE, Catalog, PatientDirectory, Schedule  # noqa: E402

NOW = datetime(2026, 10, 6, 9, 0)
cat = Catalog.load()
clinic = Clinic(cat, PatientDirectory.load(), Schedule(cat))


def at(stage):
    s = clinic.new_call(clock=lambda: NOW)
    s.enter_stage(IDENTIFY, [])
    run_tool(s, "start_booking", {"full_name": "Farhan Jida", "returning": False, "visit_description": "skin check"})
    s.enter_stage(VISIT_TYPE, [])
    if stage == BOOKING:
        run_tool(s, "choose_visit_type", {"visit_type_id": "appt_027"})
        s.enter_stage(BOOKING, [])
    return s


ODD = [
    (BOOKING, "change_choice", {"what": "time", "days": ["2026-02-30"]}),
    (BOOKING, "change_choice", {"what": "time", "days": ["next Thursday"]}),
    (BOOKING, "change_choice", {"what": "time", "days": [], "time_of_day": "evening"}),
    (BOOKING, "change_choice", {"what": "time", "days": ["2026-10-01"]}),
    (BOOKING, "change_choice", {"what": "location", "new_value": "Union Square"}),
    (BOOKING, "change_choice", {"what": "location", "new_value": "the Mission"}),
    (BOOKING, "change_choice", {"what": "language", "new_value": "Klingon"}),
    (BOOKING, "change_choice", {"what": "doctor", "new_value": "Dr. Nobody"}),
    (BOOKING, "change_choice", {"what": "doctor", "new_value": 7}),
    (BOOKING, "change_choice", {"what": "Time"}),
    (BOOKING, "choose_option", {"option_id": "Option 1"}),
    (BOOKING, "choose_option", {"option_id": 1.0}),
    (BOOKING, "turn_down_doctors", {"doctor_name": "Dr. Nobody"}),
    (BOOKING, "turn_down_doctors", {"current": True}),
    (BOOKING, "turn_down_doctors", {"doctor_id": "prov_999"}),
    (BOOKING, "answer_question", {"about": "doctor", "name": ["Dr. Chen"]}),
    (BOOKING, "answer_question", {"about": "insurance", "name": "Aetna"}),
    (BOOKING, "hand_off", {"reason": "Speak_to_staff"}),
    (VISIT_TYPE, "list_visit_types", {"specialty": "skin doctor"}),
    (VISIT_TYPE, "list_visit_types", {"specialty": 3}),
    (VISIT_TYPE, "choose_visit_type", {"visit_type_id": "appt_065", "days": ["Friday"], "language": "Spanish"}),
    (VISIT_TYPE, "choose_visit_type", {"visit_type_id": "appt_027", "days": ["2026-02-30"]}),
    (VISIT_TYPE, "choose_visit_type", {"visit_type_id": "appt_027", "place": "Union Square"}),
]

for stage, tool, args in ODD:
    s = at(stage)
    before = copy.deepcopy(s.card.to_dict())
    try:
        out = run_tool(s, tool, args)
    except Exception as e:  # escapes run_tool: Pipecat would answer {"status": "error", "error": str(e)}
        print(f"CRASH  {stage:10} {tool}{args}: {type(e).__name__}: {e}")
        continue
    ok = out.result.get("ok", out.result.get("found"))
    changed = s.card.to_dict() != before
    flag = "CHANGED-ON-REFUSAL" if ok is False and changed else ""
    print(f"{flag:18} {stage:10} {tool}{args}\n{'':18} -> ok={ok} next={out.next_stage} {str(out.result)[:260]}")
    if out.next_stage == BOOKING:
        notes = [f"{n.kind}: {n.say}" for n in s.offer.notes]
        print(f"{'':18}    notes: {notes}; options: {len(s.card.offered_options)}")
