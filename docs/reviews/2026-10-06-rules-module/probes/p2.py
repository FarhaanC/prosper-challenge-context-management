import sys, json; sys.path.insert(0,'../reviewer/backend')
from datetime import datetime
from clinic import *
cat=Catalog.load(); pts=PatientDirectory.load(); NOW=datetime(2026,10,6,9,0)
new=Caller("New Person")
def show(r):
    print(" notes:", r.notes)
    for o in r.options: print("  ", o.spoken)
SKIN="appt_027"
# A: location change with old doctor kept as wish
derm=[p for p in cat.providers_offering(SKIN)]
for p in derm: print(p.id,p.name,p.location_ids,p.accepting_new_patients,p.languages)
r=find_options(cat,Schedule(cat),new,SKIN,Preferences(),NOW); show(r)
o=r.options[0]
card=BookingCard(caller=new); card.choices.visit_type_id=SKIN; card.choices.provider_id=o.provider_id; card.choices.location_id=o.location_id; card.choices.slot=o.start
# pick a location where this derm doesn't work but another derm (taking new) does
other_locs={l for p in derm if p.accepting_new_patients for l in p.location_ids}-set(cat.providers[o.provider_id].location_ids)
print("chosen", o.provider_name, o.location_name, "-> switch to", [cat.locations[l].name for l in other_locs])
target=cat.locations[sorted(other_locs)[0]]
print("stage", card.change_choice("location", "the "+target.name.split()[0]+" one"), card.preferences)
print("A) location change:"); show(find_options(cat,Schedule(cat),new,SKIN,card.preferences,NOW))
print("   same request without the leftover doctor wish:"); show(find_options(cat,Schedule(cat),new,SKIN,Preferences(location_hint=card.preferences.location_hint),NOW))
# B: doctor wish + language
print("B) doctor + language:"); show(find_options(cat,Schedule(cat),new,SKIN,Preferences(preferred_provider_id=o.provider_id, language="Spanish"),NOW))
# C: time change keeps doctor+location -> misleading note
card=BookingCard(caller=new); card.choices.visit_type_id=SKIN; card.choices.provider_id=o.provider_id; card.choices.location_id=o.location_id
card.change_choice("time", days=["Thursday"])
print("C) time change to Thursday:"); show(find_options(cat,Schedule(cat),new,SKIN,card.preferences,NOW))
print("   Thursday with anyone:"); show(find_options(cat,Schedule(cat),new,SKIN,Preferences(days=["Thursday"]),NOW))
# D: unknown time words silently ignored
for t in ["early morning","lunchtime","evening","after 3"]:
    r=find_options(cat,Schedule(cat),new,SKIN,Preferences(time_of_day=t),NOW); print("D)",t,[x.start.strftime('%a %H:%M') for x in r.options], r.notes)
for d in ["next Thursday","Thurs","Th","this Friday","Oct 13","13/10/2026"]:
    r=find_options(cat,Schedule(cat),new,SKIN,Preferences(days=[d]),NOW); print("D)",d,[x.start.strftime('%a %d %H:%M') for x in r.options], r.notes)
# E: language spelling
for lang in ["spanish","Español","Chinese","mandarin chinese"]:
    r=find_options(cat,Schedule(cat),new,SKIN,Preferences(language=lang),NOW); print("E)",lang,r.notes)
# F: marina district
r=find_options(cat,Schedule(cat),new,SKIN,Preferences(location_hint="near the Marina District"),NOW); print("F)"); show(r)
# G: unknown id crash
for f in [lambda: can_book_visit_type(cat,new,"appt_999"), lambda: find_options(cat,Schedule(cat),new,"MRI",Preferences(),NOW)]:
    try: f(); print("G) no crash")
    except Exception as e: print("G) crash", type(e).__name__, e)
print("G2)", check_booking(cat,Schedule(cat),new,"appt_999","prov_001","loc_001",NOW,NOW))
# H: read_back on incomplete card / summary duplicates / to_dict json
c=BookingCard(caller=new); c.choices.visit_type_id=SKIN
try: c.read_back(cat)
except Exception as e: print("H) read_back incomplete:", type(e).__name__, e)
c=BookingCard(caller=new, preferences=Preferences(doctor_name_heard="Garcia")); c.choices.visit_type_id=SKIN; c.choices.provider_id=o.provider_id; c.choices.location_id=o.location_id
c.change_choice("visit type","knee mri"); print("H) summary:", c.summary(cat))
c.offered_options=r.options
try: json.dumps(c.to_dict()); print("H) to_dict json ok")
except Exception as e: print("H) to_dict json fails", e)
# I: answer_question doctor truncation & Cohen
a=answer_question(cat,"doctor","Dr. Chen"); print("I) Chen results", len(a["results"]), a["message"])
a=answer_question(cat,"doctor","Dr. Cohen"); print("I) Cohen ->", [x["name"] for x in a["results"]], a["message"])
# J: misaligned / timezone start
print("J)", check_booking(cat,Schedule(cat),new,SKIN,o.provider_id,o.location_id,o.start.replace(minute=o.start.minute+5),NOW))
