from common import *
s = Schedule(cat)
import collections
by = collections.defaultdict(list)
for p in cat.providers.values(): by[p.name].append(p)
for name, ps in by.items():
    if len(ps) > 1:
        print(name, [(p.id, p.specialty, p.location_ids, p.accepting_new_patients, len(p.appointment_type_ids)) for p in ps],
              "shared types:", sorted(set(ps[0].appointment_type_ids) & set(ps[1].appointment_type_ids))[:5])
# Linda Ramirez / Michael Sato: find a visit both can do
for name in ["Dr. Linda Ramirez", "Dr. Michael Sato", "Dr. Maria Garcia"]:
    a, b = by[name]
    shared = sorted(set(a.appointment_type_ids) & set(b.appointment_type_ids))
    if not shared: continue
    vt = shared[0]; caller = ret()
    print("\n##", name, "visit", vt, cat.visit_types[vt].name)
    card = card_for(caller, vt)
    card.turn_down_doctors(cat, provider_ids=[a.id])
    print(" turned down one:", a.id); 
    card.change_choice("doctor", name)
    r = search(s, card); show(r)
    print(" summary:", card.summary(cat).replace("\n", " || "))
    # both turned down, surname alone
    card = card_for(caller, vt); card.turn_down_doctors(cat, provider_ids=[a.id, b.id])
    card.change_choice("doctor", "Dr. " + name.split()[-1])
    r = search(s, card); print(" both down, surname:"); show(r)
    # all doctors offering vt turned down -> no_other_doctor wording
    card = card_for(caller, vt); card.turn_down_doctors(cat, provider_ids=[p.id for p in cat.providers_offering(vt)])
    r = search(s, card); print(" all down:"); show(r)
