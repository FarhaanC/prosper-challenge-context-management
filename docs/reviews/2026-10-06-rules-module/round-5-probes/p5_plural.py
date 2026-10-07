from common import *
s = Schedule(cat)
for surname, vt in [("Garcia", "appt_000"), ("Sato", "appt_000"), ("Chen", "appt_000")]:
    able = sorted({p.id for p in cat.providers_offering(vt) if p.name.endswith(" " + surname)
                   and any(s.open_slots(p.id, l, cat.visit_types[vt].duration_min, NOW) for l in p.location_ids)})
    card = card_for(ret(), vt); card.turn_down_doctors(cat, provider_ids=able)
    card.change_choice("doctor", "Dr. " + surname)
    r = search(s, card); print(surname, [cat.providers[i].name for i in able]); show(r)
