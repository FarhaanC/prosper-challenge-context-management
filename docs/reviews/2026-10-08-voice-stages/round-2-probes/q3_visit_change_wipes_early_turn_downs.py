"""S3: a turn-down said before any visit is chosen (now possible, decision 53) is wiped
by a change_choice visit_type in stages 1-2, so the doctor is offered after all."""
from _setup import NEW, SKIN, call, options, step

for where in ("identify", "visit_type"):
    s = call()
    if where == "visit_type":
        step(s, "start_booking", dict(NEW))
    step(s, "turn_down_doctors", {"doctor_name": "Dr. Kenji Kim"})
    print(f"[{where}] after 'not Dr. Kim': not =", s.card.preferences.not_provider_ids)
    out = step(s, "change_choice", {"visit_type": "a skin cancer check"})
    print(f"[{where}] change_choice visit_type ->", out.result, "| not =", s.card.preferences.not_provider_ids)
    if where == "identify":
        step(s, "start_booking", dict(NEW))
    step(s, "choose_visit_type", {"visit_type_id": SKIN})
    print(f"[{where}] options:", options(s))
