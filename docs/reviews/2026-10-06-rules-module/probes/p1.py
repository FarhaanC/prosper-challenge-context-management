import sys; sys.path.insert(0,'../reviewer/backend')
from datetime import datetime
from clinic import *
from clinic.fuzzy import soundex
cat=Catalog.load(); pts=PatientDirectory.load()
NOW=datetime(2026,10,6,9,0)
print("--- names that should NOT match (or should flag fuzzy)")
for h in ["Dr. Cohen","Dr. Kahn","Dr. Smyth","Dr. Lee","Dr. Lin","Dr. Patil","Dr. Sanchez","Dr. Shen","Dr. Nixon","Dr. Kemp","Dr. Saito","Dr. Garcia's","Dr. Rodriguez","Dr. Martin","Dr. Johnston","Dr. Jensen","Dr. Kenji","Dr. Wei","Dr. Win","Dr. Hannah Win","Dr. Mario Garcia","Dr. Singer","Dr. Simmons","Dr. Sing"]:
    r=cat.find_providers_by_name(h); print(f"{h!r:22} -> {len(r)}: {sorted({p.name for p in r})[:4]}")
print("--- patients")
for n in ["Mr Wilson","Mr. Wilson","Dr Wilson","Robert Tyler","Jim Wilson","Mei Wong","May Wang","James Wilson","Sarah Johnston","Emily Browne","Amed Khan","Emily Bryant"]:
    r=pts.lookup(n); print(f"{n!r:18} {r.status} {r.caller.name if r.caller else ''}")
print(pts.lookup("James Wilson","1984-03-13").status, "(DOB off by one day -> treated as new patient)")
print("--- places")
for h in ["Richmond District","the Richmond","Inner Richmond","Castro District","the Marina District","Marina","North Gate","the Mission","in the Mission","Mission Bae","mid town","the midtown one","Hayes Valley","near Hayes Valley","near the Ferry Building","Sunset District","the Sunset","near Sunset","by the Presidio","Geary","Market Street","near Mission Street","Union Square one","Twin Peaks","downtown please","SF General","Nob Hill area","near Stanford"]:
    m=cat.resolve_place(h); print(f"{h!r:26} {m.kind:9} {m.label!r} {m.location_ids} near={m.near}")
print("--- specialty")
for s in ["cardio","derm","heart","Orthopaedics","pediatric","Physical therapist","ear nose throat","GI","eye doctor","Allergy","Immunology","psych","lab work","general practice","Internal"]:
    print(s, "->", cat.match_specialty(s))
