from common import *
import json, copy, traceback
raw=json.load(open(B+'/data/catalog.json')); ex=json.load(open(B+'/data/location_extras.json'))
def t(label, mut_raw=None, mut_ex=None):
    r=copy.deepcopy(raw); e=copy.deepcopy(ex)
    if mut_raw: mut_raw(r)
    if mut_ex: mut_ex(e)
    try:
        c=Catalog(r,e); print(f"{label:45} LOADED OK", end="")
        return c
    except CatalogError as x: print(f"{label:45} CatalogError: {str(x)[:150]!r}")
    except Exception as x: print(f"{label:45} CRASH {type(x).__name__}: {x}")
def s(path_fn): return path_fn
t("loc id is a list", lambda r: r["locations"][0].__setitem__("id",["x"]))
t("prov id is a dict", lambda r: r["providers"][0].__setitem__("id",{"a":1}))
c=t("capabilities is a string", lambda r: r["locations"][1].__setitem__("capabilities","imaging")); print(" ->", c and c.locations["loc_001"].capabilities)
c=t("capabilities has a number", lambda r: r["locations"][1].__setitem__("capabilities",[1,2])); print()
c=t("required_capability is a list", lambda r: r["appointment_types"][0].__setitem__("required_capability",["imaging"])); print(" ->", c and c.visit_types[raw["appointment_types"][0]["id"]].required_capability)
c=t("required_capability unknown 'imagng'", lambda r: [a.__setitem__("required_capability","imagng") for a in r["appointment_types"] if a.get("required_capability")=="imaging"]); print()
t("lat is text", mut_ex=lambda e: e["locations"]["loc_000"].__setitem__("lat","abc"))
c=t("lat is '37.7'", mut_ex=lambda e: e["locations"]["loc_000"].__setitem__("lat","37.7")); print()
c=t("lat is 999", mut_ex=lambda e: e["locations"]["loc_000"].__setitem__("lat",999)); print()
t("lat is None", mut_ex=lambda e: e["locations"]["loc_000"].__setitem__("lat",None))
t("extras locations is a list", mut_ex=lambda e: e.__setitem__("locations",[]))
t("extras is a list", mut_ex=lambda e: (e.clear()))
t("landmark point bad", mut_ex=lambda e: e["landmarks"].__setitem__("X",["a"]))
c=t("landmark point 1 number", mut_ex=lambda e: e["landmarks"].__setitem__("Twin Peaks",[37.7])); print()
t("neighbourhood is a number", mut_ex=lambda e: e["locations"]["loc_000"].__setitem__("neighbourhood",5))
t("also_called is a string", mut_ex=lambda e: e["locations"]["loc_000"].__setitem__("also_called","Bay")); print()
t("extra location for unknown id", mut_ex=lambda e: e["locations"].__setitem__("loc_999",{"lat":1,"lon":2})); print()
t("location_ids empty", lambda r: r["providers"][0].__setitem__("location_ids",[]))
t("duration 0", lambda r: r["appointment_types"][0].__setitem__("duration_min",0))
t("duration 30.0", lambda r: r["appointment_types"][0].__setitem__("duration_min",30.0))
c=t("duration 600 (longer than a day)", lambda r: r["appointment_types"][0].__setitem__("duration_min",600)); print()
t("hours 'Mon-Fri 8:00-25:00'", lambda r: r["locations"][0].__setitem__("hours","Mon-Fri 8:00-25:00"))
t("hours 'Mon-Fri 8:60-17:00'", lambda r: r["locations"][0].__setitem__("hours","Mon-Fri 8:60-17:00"))
t("raw is a list", lambda r: None) 
try: Catalog([], ex); print("ok")
except Exception as x: print("raw list:", type(x).__name__, str(x)[:80])
t("provider specialty unknown", lambda r: r["providers"][0].__setitem__("specialty","Astrology")); print()
t("empty languages list", lambda r: r["providers"][0].__setitem__("languages",[])); print()
t("name whitespace", lambda r: r["providers"][0].__setitem__("name","  ")); 
t("duplicate location_ids in a provider", lambda r: r["providers"][0].__setitem__("location_ids",r["providers"][0]["location_ids"]*2)); print()
t("new_patients 'yes'", lambda r: r["appointment_types"][0].__setitem__("new_patients_allowed","yes"))
# patients
for rec in [[{"id":"p","name":"A B"}], ["notadict"], [{"id":"p","name":"A B","date_of_birth":"1990-13-45"}], [{"id":"p","name":"A","date_of_birth":"1990-01-01"}],[{"id":"p","name":"A B","date_of_birth":"1990-01-01","referrals_on_file":"Radiology"}], [{"id":"p","name":5,"date_of_birth":"1990-01-01"}]]:
    try:
        dd=PatientDirectory(rec); print("patients", rec, "LOADED");
        print("   lookup:", dd.lookup("A B","1990-01-01").to_dict() if isinstance(rec[0],dict) else None)
    except CatalogError as x: print("patients CatalogError", x)
    except Exception as x: print("patients CRASH", type(x).__name__, x)
