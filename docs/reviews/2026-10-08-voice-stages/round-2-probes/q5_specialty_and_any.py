"""S5 / S6: small value-handling gaps.
- a specialty sent with change_choice before identification, or with a failed identity
  try, is dropped when start_booking then succeeds without it;
- visit_type "any" is stored as the visit description."""
from _setup import JAMES, call, step

s = call()
step(s, "change_choice", {"visit_type": "knee MRI", "specialty": "Radiology"})
print("stage 1 change with specialty Radiology -> listed:", s.listed_specialty)
step(s, "start_booking", dict(JAMES))
print("after start_booking (no specialty):", s.fill("{visit_types}")[:60])

s = call()
out = step(s, "start_booking", {**JAMES, "date_of_birth": "1984-03-13", "specialty": "Radiology",
                                "visit_description": "knee MRI"})
print("failed try with specialty ->", out.result["status"], "| visit kept:", s.card.preferences.visit_description)
step(s, "start_booking", dict(JAMES))
print("after the right birthday (no specialty):", s.fill("{visit_types}")[:60])

s = call()
step(s, "start_booking", dict(JAMES))
out = step(s, "change_choice", {"visit_type": "any"})
print("change_choice visit_type 'any' ->", out.result, "| visit description:", repr(s.card.preferences.visit_description))
