from common import *
import json, random, time
random.seed(1)
B='/tmp/claude-0/-home-claude/7d014f89-7c13-557c-9246-c7fae4f61e23/scratchpad/round3/reviewer/backend/data/'
raw=json.load(open(B+'catalog.json')); ex=json.load(open(B+'location_extras.json'))
locs=[]; exl={}
for i in range(500):
    b=raw["locations"][i%8]; lid=f"L{i}"
    locs.append({**b,"id":lid,"name":f"{b['name']} {i}"})
    exl[lid]={"neighbourhood":"x","lat":37.7+random.random()*0.1,"lon":-122.5+random.random()*0.1}
provs=[]
first=["Ana","Ben","Chloe","Dev","Eli","Fay","Gus","Hana","Ivan","Jun"]; last=["Garcia","Chen","Nguyen","Patel","Kim","Smith","Lopez","Wong","Singh","Brown","Tran","Lee","Park","Ali","Khan"]
for i in range(2000):
    b=raw["providers"][i%50]
    name = b["name"] if i<50 else f"Dr. {random.choice(first)} {random.choice(last)}{'' if random.random()<.5 else random.choice(['son','ez','ova','i'])}"
    provs.append({**b,"id":f"P{i}","name":name,"location_ids":random.sample([l["id"] for l in locs],len(b["location_ids"]))})
big={"locations":locs,"providers":provs,"appointment_types":raw["appointment_types"],"policies":[]}
t=time.time(); C=Catalog(big,{"locations":exl,"landmarks":ex["landmarks"]}); print("load %.2fs"%(time.time()-t))
ALLREF = Caller("A","pat_y",False,C.specialties())
def tm(label, f, reps=3):
    ts=[]
    for _ in range(reps):
        t=time.perf_counter(); f(); ts.append(time.perf_counter()-t)
    print(f"{label:60} first {ts[0]*1000:7.1f} ms  min {min(ts)*1000:7.1f} ms")
print("pairs appt_002:", len(can_book_visit_type(C,ALLREF,"appt_002").valid_pairs))
for v,kw in [("appt_002",{}),("appt_002",{"days":["Saturday"]}),("appt_002",{"days":["2026-12-25"]}),
             ("appt_002",{"days":["Monday"],"time_of_day":"afternoon","language":"Hindi"}),
             ("appt_002",{"preferred_provider_id":"P7","days":["Saturday"],"language":"Klingon"}),
             ("appt_002",{"doctor_name_heard":"Dr. Garsha"}),("appt_002",{"doctor_name_heard":"Dr. Chen"}),
             ("appt_002",{"location_hint":"near Downtown"}),("appt_002",{"language":"Klingon"}),
             ("appt_002",{"not_provider_ids":["P7"]}),("appt_002",{"days":["today"],"time_of_day":"afternoon"})]:
    tm(f"fresh {v} {kw}"[:60], lambda: find_options(C,Schedule(C),ALLREF,v,Preferences(**kw),NOW))
tm("resolve_place 'the one on Geary'", lambda: C.resolve_place("the one on Geary"))
tm("resolve_place 'near Twin Peaks' (unknown)", lambda: C.resolve_place("near Twin Peaks xyz"+str(random.random())))
tm("match_specialty", lambda: C.match_specialty("hematologist"+str(random.random())))
tm("match_providers uncached", lambda: C.match_providers("Dr. Quentin Blorft"+str(random.random())))
import clinic.fuzzy as F
print(F._normalize.cache_info()); print(F.similarity.cache_info())
