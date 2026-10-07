from common import *
from datetime import timedelta
s = Schedule(cat)
print("== A. every_valid empty + a turned-down doctor (fully booked calendar)")
vt = "appt_027"; vtobj = cat.visit_types[vt]
s2 = Schedule(cat)
for p in cat.providers_offering(vt):
    for lid in p.location_ids:
        for t in s2.open_slots(p.id, lid, 30, NOW):
            try: s2.book(p.id, t, 30)
            except Exception: pass
try:
    r = find_options(cat, s2, new(), vt, Preferences(not_provider_ids=["prov_001"]), NOW); show(r)
except Exception as e:
    print("   CRASH:", type(e).__name__, e)
r = find_options(cat, s2, new(), vt, Preferences(doctor_name_heard="Dr. Garcia"), NOW); print("  (no turn-down, Garcia wish):"); show(r)

print("== B. pick a turned-down doctor from a no_other_doctor offer; summary before any change")
card = card_for(new(), vt)
everyone = sorted({p.id for p in cat.providers_offering(vt)})
card.turn_down_doctors(cat, provider_ids=everyone)
r = search(s, card); show(r)
choose(card, r.options[0])
print("  ", card.summary(cat).replace("\n", " || "))
print("== C. ...then a DOCTOR change ('' = no doctor wish): is the picked doctor still turned down?")
card.change_choice("doctor", "")
print("   not_provider_ids:", card.preferences.not_provider_ids)

print("== D. days list with mixed times of day")
for days, tod in [(["Thursday morning", "Friday afternoon"], ""), (["Thursday afternoon"], "morning")]:
    r = find_options(cat, s, new(), vt, Preferences(days=days, time_of_day=tod), NOW)
    print("  ", days, repr(tod), [n.kind for n in r.notes], [o.spoken for o in r.options])
card = card_for(new(), vt); card.change_choice("time", days=["Thursday morning", "Friday afternoon"])
print("   change_choice(days=[...]) ->", card.preferences.days, repr(card.preferences.time_of_day))

print("== E. language values")
for lang in ["Chinese", "English Spanish", "Spanish English", "Sign language", "ASL", "Mandarin Chinese", "Klingon", "any",
             "", "  ", "español", "Portugese", "Spanish.", "SPANISH", "Cantonese Chinese"]:
    card = card_for(new(), "appt_002"); card.change_choice("language", lang)
    r = search(s, card)
    print(f"   {lang!r:20} stored={card.preferences.language!r:20}", [(n.kind, n.say[:90]) for n in r.notes], [o.provider_name for o in r.options])
