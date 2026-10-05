from common import *
import random, itertools
random.seed(7)
from clinic.rules import valid_pairs
langs = ['Arabic','English','Hindi','Mandarin','Portuguese','Spanish','Vietnamese']
places = ["the Midtown one","Downtown","the Richmond one","Mission","near Downtown","the Sunset one","North Beach","Hayes Valley"]
days = [["Monday"],["Wednesday"],["Friday"],["Saturday"],["tomorrow"],["2026-10-14"]]
callers = [NEW, RET, ALLREF]
vts = [v for v in cat.visit_types]
issues = {}
def add(k, msg):
    issues.setdefault(k, []).append(msg)
N=0
for _ in range(3000):
    caller = random.choice(callers); vt = random.choice(vts)
    if not can_book_visit_type(cat, caller, vt).bookable: continue
    kw = {}
    pids = [p.id for p in cat.providers_offering(vt)]
    if random.random()<.5: kw["doctor_name_heard"] = random.choice(list(cat.providers.values())).name.split()[-1] if random.random()<.5 else random.choice(list(cat.providers.values())).name
    elif random.random()<.4: kw["preferred_provider_id"] = random.choice(pids)
    if random.random()<.5: kw["location_hint"] = random.choice(places)
    elif random.random()<.4: kw["preferred_location_id"] = random.choice(list(cat.locations))
    if random.random()<.5: kw["days"] = random.choice(days)
    if random.random()<.4: kw["time_of_day"] = random.choice(["morning","afternoon"])
    if random.random()<.3: kw["language"] = random.choice(langs)
    kw["latest"] = random.choice(["","doctor","location","time","language"])
    N+=1
    sch = Schedule(cat)
    r = find_options(cat, sch, caller, vt, Preferences(**kw), NOW)
    for o in r.options:
        if check_booking(cat, sch, caller, vt, o.provider_id, o.location_id, o.start, NOW):
            add("invalid option", (vt, kw))
    noted = " ".join(r.notes)
    # language satisfied or noted
    if kw.get("language") and r.options:
        bad = [o for o in r.options if kw["language"] not in cat.providers[o.provider_id].languages]
        if bad and kw["language"] not in noted and "speaking" not in noted:
            add("language dropped silently", (vt, kw, noted))
    if (kw.get("days") or kw.get("time_of_day")) and r.options and not any(n.kind==BAD_INPUT for n in r.notes):
        dt, lbl, tt, _ = check_time_wishes(kw.get("days"), kw.get("time_of_day"), NOW)
        def ok(t): return (not dt or any(f(t) for f in dt)) and (not tt or tt(t))
        bad = [o for o in r.options if not ok(o.start)]
        if bad and lbl not in noted:
            add("time dropped silently", (vt, kw, noted))
    if kw.get("preferred_provider_id") and r.options:
        p = cat.providers[kw["preferred_provider_id"]]
        if any(o.provider_id != p.id for o in r.options) and p.name not in noted:
            add("carried doctor dropped silently", (vt, kw, noted))
    if kw.get("preferred_location_id") and r.options:
        l = cat.locations[kw["preferred_location_id"]]
        if any(o.location_id != l.id for o in r.options) and l.name not in noted:
            add("carried place dropped silently", (vt, kw, noted))
    if kw.get("location_hint") and r.options:
        m = cat.resolve_place(kw["location_hint"])
        if m.kind in ("location","ambiguous") and not m.near:
            if any(o.location_id not in m.location_ids for o in r.options) and not any(cat.locations[i].name in noted for i in m.location_ids):
                add("named place dropped silently", (vt, kw, noted))
    if kw.get("doctor_name_heard") and r.options:
        ms = cat.match_providers(kw["doctor_name_heard"])
        ids = {m.provider.id for m in ms}
        if ms and any(o.provider_id not in ids for o in r.options) and not r.notes:
            add("heard doctor dropped silently", (vt, kw, noted))
    # conflict notes: verify truth roughly - wish label not satisfiable with something
print("searches", N)
for k,v in issues.items():
    print(k, len(v)); 
    for x in v[:3]: print("   ", x)
