"""S4: choose_visit_type outside stage 2 (typed loop, or an edited agent file) changes the
visit but keeps the doctor, place and time chosen for the OLD visit; confirm_booking then
saves a visit the caller never heard read back. Decision 55 says the code, not the stage
lists, enforces the order of a call."""
from _setup import CATALOG, NEW, SKIN, call, step

s = call()
step(s, "start_booking", dict(NEW))
step(s, "choose_visit_type", {"visit_type_id": SKIN})
rb = step(s, "choose_option", {"option_id": "1"}).result["read_back"]
print("read back to the caller:", rb)
other = "appt_028"
out = step(s, "choose_visit_type", {"visit_type_id": other})
c = s.card.choices
print(f"choose_visit_type {other} ({CATALOG.visit_types[other].name}) in the booking stage ->", out.result,
      "| still chosen:", c.provider_id, c.location_id, c.slot)
out = step(s, "confirm_booking", {})
print("confirm_booking ->", out.result)
