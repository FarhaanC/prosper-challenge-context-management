# Whole catalog: turn down a set of doctors, then add a place/day/language wish. Check every "turned down" note.
from common import *
import itertools, json
sys.path.insert(0, B+'/tests_independent')
from reference import ref_pairs, ref_bookable, VT, PROV, LOC, SPECIALTIES
from datetime import timedelta
s=sched()
bad=[]; count=0
days=[(NOW+timedelta(days=k)).date().isoformat() for k in range(0,15)]
for kind,(is_new,refs) in {"new":(True,[]),"ret":(False,list(SPECIALTIES))}.items():
    c = new() if is_new else ret(refs)
    for vt in VT:
        if not ref_bookable(is_new, refs, vt): continue
        slots=[(p,l,t) for p,l in ref_pairs(is_new,vt) for t in s.open_slots(p,l,VT[vt]["duration_min"],NOW)]
        docs=sorted({x[0] for x in slots})
        downs=[ {d} for d in docs ] + [set(docs[:2])] + [set(docs[:3])]
        for down in downs:
            others=[x for x in slots if x[0] not in down]
            if not others: continue
            wishes=[("loc",l) for l in LOC]+[("day",dd) for dd in days]+[("lang",lg) for lg in ["Spanish","Arabic","Mandarin","Hindi","Vietnamese","Portuguese"]]
            for w in wishes:
                p=Preferences(not_provider_ids=sorted(down))
                if w[0]=="loc": p.location_hint=LOC[w[1]]["name"]; f=lambda x: x[1]==w[1]
                elif w[0]=="day": p.days=[w[1]]; f=lambda x: x[2].date().isoformat()==w[1]
                else: p.language=w[1]; f=lambda x: w[1] in PROV[x[0]]["languages"]
                r=fo(c,vt,p,s); count+=1
                td=[n for n in r.notes if "turned down" in n.say]
                fits_others=any(f(x) for x in others); fits_down={x[0] for x in slots if x[0] in down and f(x)}
                if not fits_others and fits_down:
                    if len(td)!=1 or td[0].kind!="wish_conflict": bad.append(("missing", kind, VT[vt]["name"], w, [n.say for n in r.notes])); continue
                    named={pid for pid in docs if PROV[pid]["name"] in td[0].say}
                    exp_names={PROV[pid]["name"] for pid in fits_down}
                    got_names={PROV[pid]["name"] for pid in named}
                    if got_names!=exp_names: bad.append(("wrong names", kind, VT[vt]["name"], w, sorted(exp_names), td[0].say))
                elif td: bad.append(("unexpected", kind, VT[vt]["name"], w, [n.say for n in td]))
                if any(o.provider_id in down for o in r.options): bad.append(("offered turned-down", VT[vt]["name"], w))
print(count, len(bad))
import collections
print(collections.Counter(b[0] for b in bad))
for b in bad[:8]: print(b)
