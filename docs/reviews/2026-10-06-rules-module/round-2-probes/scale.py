from common import *
import json, random, time
random.seed(1)
B='/tmp/claude-0/-home-claude/7d014f89-7c13-557c-9246-c7fae4f61e23/scratchpad/round2/reviewer/backend/data/'
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
NOW=datetime(2026,10,6,9)
print("pairs skin:", len(can_book_visit_type(C,ALLREF,"appt_027").valid_pairs))
def tm(label, f, reps=1):
    ts=[]
    for _ in range(reps):
        t=time.perf_counter(); f(); ts.append(time.perf_counter()-t)
    print(f"{label:55} first {ts[0]*1000:7.1f} ms  min {min(ts)*1000:7.1f} ms")
for vt,kw in [("appt_027",{}),("appt_027",{"location_hint":"near Downtown"}),("appt_002",{"days":["Saturday"]}),
              ("appt_002",{"days":["Monday"],"time_of_day":"afternoon","language":"Hindi"}),
              ("appt_002",{"preferred_provider_id":"P7","days":["Saturday"],"language":"Klingon"}),
              ("appt_002",{"doctor_name_heard":"Dr. Garsha"}),("appt_002",{"doctor_name_heard":"Dr. Zzyzx"}),
              ("appt_002",{"location_hint":"the Midtown one"})]:
    tm(f"fresh Schedule {vt} {kw}", lambda: find_options(C,Schedule(C),ALLREF,vt,Preferences(**kw),NOW), 3)
S=Schedule(C)
tm("same Schedule appt_002 Saturday x3", lambda: find_options(C,S,ALLREF,"appt_002",Preferences(days=["Saturday"]),NOW),3)
tm("match_providers Garsha", lambda: C.match_providers("Dr. Garsha"),3)
tm("match_providers new uncached name", lambda: C.match_providers("Dr. Quentin Blorft"+str(random.random())),3)
tm("resolve_place near Twin Peaks", lambda: C.resolve_place("near Twin Peaks"),3)
tm("list_visit_types Family Medicine (can_book x types)", lambda: [can_book_visit_type(C,NEW,v.id) for v in C.visit_types_in("Family Medicine")],3)
tm("alternatives_for", lambda: alternatives_for(C,NEW,"appt_065"),3)
import clinic.fuzzy as F
print("cache sizes", F._normalize.cache_info(), F.similarity.cache_info())
print("pairs appt_002:", len(can_book_visit_type(C,ALLREF,"appt_002").valid_pairs))
tm("fresh appt_002 {}", lambda: find_options(C,Schedule(C),ALLREF,"appt_002",Preferences(),NOW),3)
tm("fresh appt_002 time_of_day morning", lambda: find_options(C,Schedule(C),ALLREF,"appt_002",Preferences(time_of_day="morning"),NOW),3)
tm("fresh appt_002 date beyond window", lambda: find_options(C,Schedule(C),ALLREF,"appt_002",Preferences(days=["2026-12-25"]),NOW),3)
import cProfile, pstats
cProfile.run('find_options(C,Schedule(C),ALLREF,"appt_002",Preferences(days=["Saturday"]),NOW)','/tmp/claude-0/-home-claude/7d014f89-7c13-557c-9246-c7fae4f61e23/scratchpad/r2probe/prof')
pstats.Stats('/tmp/claude-0/-home-claude/7d014f89-7c13-557c-9246-c7fae4f61e23/scratchpad/r2probe/prof').sort_stats('cumtime').print_stats(8)
