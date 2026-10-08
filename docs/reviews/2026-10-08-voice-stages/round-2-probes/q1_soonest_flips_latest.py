"""S1: "as soon as possible" on its own counts as a time change, so it becomes the
"latest" change and silently overturns the caller's newer place choice."""
from _setup import NEW, SKIN, call, notes, options, step

s = call()
step(s, "start_booking", {**NEW, "days": ["Friday"]})
step(s, "choose_visit_type", {"visit_type_id": SKIN})
print("1) wishes: Friday. Options:", options(s))
step(s, "change_choice", {"place": "Midtown"})
print("2) caller: 'Midtown, please'. latest =", s.card.preferences.latest)
print("   options:", options(s))
print("   notes:  ", notes(s))
step(s, "change_choice", {"soonest": True})
print("3) caller: 'whatever's soonest'. latest =", s.card.preferences.latest)
print("   options:", options(s))
print("   notes:  ", notes(s))
