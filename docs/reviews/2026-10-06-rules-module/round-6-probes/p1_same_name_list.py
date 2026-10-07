"""Two doctors with the same name AND specialty: does the "no other doctor" / "Doctors who can"
list tell them apart? (Spec round 6 s5: same-name doctors get their locations added.)"""
from common import *
raw = copy.deepcopy(RAW)
twin = copy.deepcopy(next(p for p in raw["providers"] if p["id"] == "prov_001"))  # Dr. Daniel Chen, Dermatology
print("original:", twin["name"], twin["specialty"], twin["location_ids"])
twin["id"], twin["location_ids"] = "prov_twin", ["loc_006"]
i = next(i for i, p in enumerate(raw["providers"]) if p["id"] == "prov_001")
raw["providers"].insert(i + 1, twin)  # listed right after the original
cat = Catalog(raw, EXTRAS)
sch = Schedule(cat)
skin = "appt_027"
everyone = [p.id for p in cat.providers_offering(skin)]
r = find_options(cat, sch, NEW, skin, Preferences(not_provider_ids=everyone), NOW)
for k, s in says(r): print(k, "|", s)
r = find_options(cat, sch, NEW, skin, Preferences(not_provider_ids=["prov_001", "prov_twin"]), NOW)
print([o.provider_id for o in r.options])
for k, s in says(r): print(k, "|", s)

# The same list in the "Doctors who can" sentence (a doctor wish nobody can meet):
r = find_options(cat, sch, NEW, skin, Preferences(doctor_name_heard="Dr. Linda Nguyen"), NOW)
for k, s in says(r): print(k, "|", s)
