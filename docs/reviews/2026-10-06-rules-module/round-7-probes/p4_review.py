"""Review evidence: R6-14 still as agreed; same-name labels missing in two lists; the
'not far from' spec gap; generic words in none of our names; an uncapped ambiguous-place note."""
import copy, json
from common import catalog, BACKEND, NOW, NEW, SKIN, show
from clinic import Catalog, Schedule, Preferences, find_options, answer_question
from clinic.catalog import GENERIC_PLACE_WORDS, _distinct_words
from clinic.fuzzy import normalize, NO_PREFERENCE
sched = Schedule(catalog)
RAW = json.loads((BACKEND / "data" / "catalog.json").read_text())
EXTRAS = json.loads((BACKEND / "data" / "location_extras.json").read_text())

print("--- R6-14: 'Dr. Garcia', all three Garcias turned down (Annual Physical, new caller)")
r = find_options(catalog, sched, NEW, "appt_002", Preferences(doctor_name_heard="Dr. Garcia",
                 not_provider_ids=["prov_002", "prov_003", "prov_008"]), NOW)
print(show(r)[0])

print("--- generic place words that appear in none of our location names or landmarks")
names = [l.name for l in catalog.locations.values()] + list(catalog.landmarks) + \
        [l.neighbourhood for l in catalog.locations.values()] + [a for l in catalog.locations.values() for a in l.also_called]
used = {w for n in names for w in normalize(n).split()}
print(sorted(GENERIC_PLACE_WORDS - used))

print("--- 'not far from Union Square': resolve_place vs find_options")
print(catalog.resolve_place("not far from Union Square").kind,
      show(find_options(catalog, sched, NEW, SKIN, Preferences(location_hint="not far from Union Square"), NOW))[0])

print("--- same name + same specialty, neither taking new patients: the 'can't do this' reason")
raw = copy.deepcopy(RAW)
chen = next(p for p in raw["providers"] if p["id"] == "prov_001")
twin = dict(copy.deepcopy(chen), id="prov_twin", location_ids=["loc_006"])
raw["providers"].append(twin)
for p in raw["providers"]:
    if p["id"] in ("prov_001", "prov_twin"):
        p["accepting_new_patients"] = False
cat2 = Catalog(raw, EXTRAS)
r = find_options(cat2, Schedule(cat2), NEW, SKIN, Preferences(doctor_name_heard="Dr. Daniel Chen"), NOW)
print(show(r)[0])
r = find_options(cat2, Schedule(cat2), NEW, SKIN, Preferences(doctor_name_heard="Dr. Zebulon Chen"), NOW)
print(show(r)[0][0])

print("--- an ambiguous place on a big network: 40 clinics in neighbourhoods called 'Mission <something>'")
raw = copy.deepcopy(RAW); ex = copy.deepcopy(EXTRAS)
for i in range(40):
    lid = f"loc_m{i:02d}"
    raw["locations"].append(dict(copy.deepcopy(raw["locations"][0]), id=lid, name=f"Clinic {i} Health Center",
                                 address=f"{i+1} Pine St"))
    ex["locations"][lid] = {"neighbourhood": f"Mission {['Terrace','Dolores','Heights','Park','Hill','View','Gardens','Point'][i % 8]} {i}",
                            "also_called": [], "lat": 37.75, "lon": -122.42}
cat3 = Catalog(raw, ex)
r = find_options(cat3, Schedule(cat3), NEW, SKIN, Preferences(location_hint="Mission", near=True), NOW)
n = [x for x in r.notes if x.kind == "place_ambiguous"][0]
print(len(n.say), "characters;", n.say.count(" Health Center") + n.say.count(" Clinic"), "places named;", n.say[:160], "...")

print("--- 'no preference' list: entries that are phrases, not single words")
print(sorted(w for w in NO_PREFERENCE if len(w) > 9))
print("--- languages: a non-language word with an unknown name is kept as a language")
for lang in ["French only", "ideally Tagalog", "Klingon preferably"]:
    print(repr(lang), show(find_options(catalog, sched, NEW, "appt_002", Preferences(language=lang), NOW))[0])
