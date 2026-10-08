"""S2: before options exist, turning one doctor down wipes the doctor the caller asked
for (and makes "doctor" the latest change)."""
from _setup import JAMES, SKIN, call, options, step

s = call()
step(s, "start_booking", {**JAMES, "doctor_name": "Dr. Daniel Smith", "place": "Midtown"})
p = s.card.preferences
print("after start_booking: doctor wish =", repr(p.doctor_name_heard), "| latest =", repr(p.latest))
out = step(s, "turn_down_doctors", {"doctor_name": "Dr. Kenji Kim"})
print("turn_down_doctors 'not Dr. Kim' in stage 2 ->", out.result, "| stage", s.stage)
print("now: doctor wish =", repr(p.doctor_name_heard), "| not =", p.not_provider_ids, "| latest =", repr(p.latest))
step(s, "choose_visit_type", {"visit_type_id": SKIN})
print("first options (caller asked for Dr. Daniel Smith):", options(s))
