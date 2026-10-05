import sys, json, math; sys.path.insert(0,'/tmp/claude-0/-home-claude/7d014f89-7c13-557c-9246-c7fae4f61e23/scratchpad/round2/reviewer/backend')
from datetime import datetime
from clinic import *
from clinic.catalog import distance_miles
cat=Catalog.load(); NOW=datetime(2026,10,6,9,0); new=Caller("New Person"); SKIN="appt_027"
def show(r):
    print(" notes:", r.notes)
    for o in r.options: print("  ", o.spoken)
card=BookingCard(caller=new); c=card.choices; c.visit_type_id=SKIN; c.provider_id="prov_001"; c.location_id="loc_007"
card.change_choice("location","the Midtown one")
print("A2) chose Dr Daniel Chen @Richmond, then 'the Midtown one':"); show(find_options(cat,Schedule(cat),new,SKIN,card.preferences,NOW))
card=BookingCard(caller=new); c=card.choices; c.visit_type_id=SKIN; c.provider_id="prov_001"; c.location_id="loc_007"
card.change_choice("time",days=["Wednesday"])
print("C2) chose Chen @Richmond, then 'Wednesday':"); show(find_options(cat,Schedule(cat),new,SKIN,card.preferences,NOW))
s=Schedule(cat)
print("Chen location by weekday:", [(d, s.location_on("prov_001", datetime(2026,10,5+d).date())) for d in range(5)])
# facts landmark closest vs real distance
for name,pt in cat.landmarks.items():
    a=min(cat.locations.values(), key=lambda l:(l.lat-pt[0])**2+(l.lon-pt[1])**2)
    b=min(cat.locations.values(), key=lambda l:distance_miles(pt,(l.lat,l.lon)))
    if a.id!=b.id: print("facts closest differs for", name, a.name, "vs", b.name)
# slot edge cases
dur_checks=[]
for pid,lid in [("prov_014","loc_004")]:
    for dur in [10,30,45,60]:
        sl=s.open_slots(pid,lid,dur,NOW)
        bad=[x for x in sl if (x.hour==12) or (x.hour==11 and x.minute==30 and dur>30) or (x+__import__('datetime').timedelta(minutes=dur)).time()>__import__('datetime').time(17)]
        print("dur",dur,"n",len(sl),"first",sl[0],"last",sl[-1],"bad",bad, "horizon days", (sl[-1].date()-NOW.date()).days)
# missing extras -> lat/lon 0
raw=json.load(open('../reviewer/backend/data/catalog.json')); ex=json.load(open('../reviewer/backend/data/location_extras.json'))
del ex["locations"]["loc_005"]
cat2=Catalog(raw,ex)
r=find_options(cat2,Schedule(cat2),new,SKIN,Preferences(location_hint="near Hayes Valley"),NOW); print("missing coords:"); show(r)
