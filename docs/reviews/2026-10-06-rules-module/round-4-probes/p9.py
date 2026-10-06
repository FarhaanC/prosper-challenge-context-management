from common import *
sys.path.insert(0, B+'/tests_independent')
from reference import ref_pairs, ref_bookable, VT, PROV, LOC, SPECIALTIES
s=sched()
# find visit types where exactly one doctor can do it; turn down by surname shared with others
bad=0
for kind,(is_new,refs) in {"new":(True,[]),"ret":(False,list(SPECIALTIES))}.items():
    c=new() if is_new else ret(refs)
    for vt in VT:
        if not ref_bookable(is_new,refs,vt): continue
        docs=sorted({p for p,l in ref_pairs(is_new,vt) if s.open_slots(p,l,VT[vt]["duration_min"],NOW)})
        if len(docs)!=1: continue
        sur=PROV[docs[0]]["name"].split()[-1]
        same=[q["name"] for q in PROV.values() if q["name"].split()[-1]==sur]
        if len(same)<2: continue
        card=BookingCard(caller=c); card.choices=Choices(visit_type_id=vt)
        card.change_choice("doctor", f"not Dr. {sur}")
        r=fo(c,vt,card.preferences,s)
        nod=[n.say for n in r.notes if n.kind=="no_other_doctor"]
        print(kind, VT[vt]["name"], "| only:", PROV[docs[0]]["name"], "|", nod)
        bad+=1
        if bad>4: raise SystemExit
