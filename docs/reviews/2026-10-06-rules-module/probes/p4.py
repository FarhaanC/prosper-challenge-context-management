import sys, json, random, time; sys.path.insert(0,'../reviewer/backend')
from datetime import datetime
from clinic import *
random.seed(1)
raw=json.load(open('../reviewer/backend/data/catalog.json')); ex=json.load(open('../reviewer/backend/data/location_extras.json'))
locs=[]; exl={}
for i in range(500):
    b=raw["locations"][i%8]; lid=f"L{i}"
    locs.append({**b,"id":lid,"name":f"{b['name']} {i}"})
    exl[lid]={"neighbourhood":"x","lat":37.7+random.random()*0.1,"lon":-122.5+random.random()*0.1}
provs=[]
for i in range(2000):
    b=raw["providers"][i%50]
    provs.append({**b,"id":f"P{i}","name":b["name"]+("" if i<50 else f" {i}"),"location_ids":random.sample([l["id"] for l in locs],len(b["location_ids"]))})
big={"locations":locs,"providers":provs,"appointment_types":raw["appointment_types"],"policies":[]}
t=time.time(); cat=Catalog(big,{"locations":exl,"landmarks":ex["landmarks"]}); print("load %.2fs"%(time.time()-t))
NOW=datetime(2026,10,6,9); ret=Caller("x","p",False,cat.specialties())
print("pairs for skin check:", len(can_book_visit_type(cat,ret,"appt_027").valid_pairs))
for vt,pref in [("appt_027",Preferences()),("appt_027",Preferences(location_hint="near Downtown")),("appt_002",Preferences(days=["Saturday"]))]:
    t=time.time(); r=find_options(cat,Schedule(cat),ret,vt,pref,NOW); print(vt,pref.location_hint or pref.days,"find_options %.2fs"%(time.time()-t))
t=time.time()
for v in cat.visit_types_in("Family Medicine"): can_book_visit_type(cat,ret,v.id)
print("list_visit_types(Family Medicine) %.3fs"%(time.time()-t))
t=time.time(); cat.find_providers_by_name("Dr. Garsha"); print("name search %.3fs"%(time.time()-t))
t=time.time(); cat.resolve_place("near Twin Peaks"); print("place %.3fs"%(time.time()-t))
s=Schedule(cat); o=r.options[0]; t=time.time(); check_booking(cat,s,ret,"appt_002",o.provider_id,o.location_id,o.start,NOW); print("check_booking %.3fs"%(time.time()-t))
# naive at current size
cat0=Catalog.load(); t=time.time()
for vt in cat0.visit_types: find_options(cat0,Schedule(cat0),ret,vt,Preferences(),NOW)
print("small catalog: all 82 find_options %.2fs"%(time.time()-t))
