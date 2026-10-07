"""Speed and note length on a big generated catalog: 500 locations, 2,000 doctors,
the real 82 visit types. Also counts how many doctor names any one note reads out."""
import copy, json, random, re, time
from common import BACKEND, NOW, NEW
from clinic import Catalog, Schedule, Caller, Preferences, BookingCard, find_options, answer_question

RAW = json.loads((BACKEND / "data" / "catalog.json").read_text())
EXTRAS = json.loads((BACKEND / "data" / "location_extras.json").read_text())
rng = random.Random(7)
raw, extras = copy.deepcopy(RAW), copy.deepcopy(EXTRAS)
caps = ["imaging", "lab", "physical_therapy", "dental", "surgery"]
first = ["Ana", "Ben", "Carla", "Dev", "Eli", "Fay", "Gus", "Hana", "Ivan", "Jo", "Kai", "Lena", "Mo", "Nia", "Oz"]
last = ["Chen", "Garcia", "Kim", "Patel", "Nguyen", "Smith", "Lopez", "Okafor", "Silva", "Haddad", "Ito", "Novak"]
raw["locations"], extras["locations"] = [], {}
for i in range(500):
    lid = f"loc_{i:03d}"
    raw["locations"].append({"id": lid, "name": f"Clinic {i} Health Center", "address": f"{100 + i} Street{i % 40} St",
                             "city": "San Francisco", "phone": "(415) 555-0000", "hours": "Mon-Fri 8:00-17:00",
                             "capabilities": rng.sample(caps, rng.randint(0, 3))})
    extras["locations"][lid] = {"neighbourhood": f"Hood{i}", "also_called": [], "lat": 37.7 + rng.random() / 10,
                                "lon": -122.5 + rng.random() / 10}
by_spec = {}
for a in raw["appointment_types"]:
    by_spec.setdefault(a["specialty"], []).append(a["id"])
specs = sorted(by_spec)
raw["providers"] = []
for i in range(2000):
    s = rng.choice(specs)
    raw["providers"].append({"id": f"prov_{i:04d}", "name": f"Dr. {rng.choice(first)} {rng.choice(last)}", "title": "MD",
                             "specialty": s, "location_ids": rng.sample([l["id"] for l in raw["locations"]], rng.randint(1, 4)),
                             "accepting_new_patients": rng.random() < 0.7,
                             "languages": ["English"] + rng.sample(["Spanish", "Mandarin", "Hindi"], 1),
                             "appointment_type_ids": by_spec[s] + (by_spec.get("General", []) if rng.random() < 0.3 else [])})
t = time.perf_counter(); cat = Catalog(raw, extras); load = time.perf_counter() - t
ret = Caller("x", "p", False, cat.specialties())
offer = {vt: len(cat.providers_offering(vt)) for vt in cat.visit_types}
big = max(offer, key=offer.get)
print(f"load {load:.3f}s; biggest visit type {cat.visit_types[big].name} offered by {offer[big]} doctors")
longest = {}


def timeit(label, fn, n=5):
    times = []
    for _ in range(n):
        t = time.perf_counter(); r = fn(); times.append(time.perf_counter() - t)
    for x in getattr(r, "notes", []):
        longest[x.kind] = max(longest.get(x.kind, (0, 0)), (len(x.say), x.say.count("Dr. ")))
    print(f"{label:58} {min(times)*1000:6.0f}-{max(times)*1000:5.0f} ms  notes={[x.kind for x in getattr(r, 'notes', [])]}")
    return r


B = cat.visit_types[big].name
timeit("skin check, no wishes", lambda: find_options(cat, Schedule(cat), NEW, "appt_027", Preferences(), NOW))
timeit(f"{B}, no wishes", lambda: find_options(cat, Schedule(cat), ret, big, Preferences(), NOW))
timeit(f"{B}, Thursday morning + Spanish", lambda: find_options(
    cat, Schedule(cat), ret, big, Preferences(days=["Thursday"], time_of_day="morning", language="Spanish"), NOW))
timeit(f"{B}, 'Dr. Chen'", lambda: find_options(cat, Schedule(cat), ret, big, Preferences(doctor_name_heard="Dr. Chen"), NOW))
timeit(f"{B}, 'Dr. Chenn' (close spelling)", lambda: find_options(cat, Schedule(cat), ret, big, Preferences(doctor_name_heard="Dr. Chenn"), NOW))
timeit(f"{B}, Hood3 near=True", lambda: find_options(cat, Schedule(cat), ret, big, Preferences(location_hint="Hood3", near=True), NOW))
timeit(f"{B}, Hood3 near=False", lambda: find_options(cat, Schedule(cat), ret, big, Preferences(location_hint="Hood3"), NOW))
timeit(f"{B}, 'Street7 Street' (shared street, near)", lambda: find_options(
    cat, Schedule(cat), ret, big, Preferences(location_hint="Street7 Street", near=True), NOW))
everyone = [p.id for p in cat.providers_offering(big)]
timeit(f"{B}, everyone turned down", lambda: find_options(cat, Schedule(cat), ret, big, Preferences(not_provider_ids=everyone), NOW))
chens = [p.id for p in cat.providers.values() if p.name.endswith(" Chen")]
timeit(f"{B}, all Chens turned down, 'Dr. Chen'", lambda: find_options(
    cat, Schedule(cat), ret, big, Preferences(doctor_name_heard="Dr. Chen", not_provider_ids=chens), NOW))
timeit(f"{B}, Klingon", lambda: find_options(cat, Schedule(cat), ret, big, Preferences(language="Klingon"), NOW))
timeit(f"{B}, 2026-10-10 (Saturday)", lambda: find_options(cat, Schedule(cat), ret, big, Preferences(days=["2026-10-10"]), NOW))
# a doctor wish nobody can meet: "Dr. Chen" for a visit no Chen offers -> the "can't do this" reasons
small = min((vt for vt in cat.visit_types if cat.providers_offering(vt)), key=lambda v: len(cat.providers_offering(v)))
timeit(f"'Dr. Chen' for {cat.visit_types[small].name}", lambda: find_options(
    cat, Schedule(cat), ret, small, Preferences(doctor_name_heard="Dr. Chen"), NOW))
timeit("answer_question doctor 'Dr. Chen'", lambda: answer_question(cat, "doctor", "Dr. Chen"))
timeit("answer_question location 'Hood42'", lambda: answer_question(cat, "location", "Hood42"))
card = BookingCard(caller=ret); card.preferences.not_provider_ids = everyone[:300]
timeit("card summary with 300 doctors turned down", lambda: card.summary(cat))
print("\nLongest note of each kind (characters, doctor names read):")
for k, v in sorted(longest.items()):
    print(f"  {k:20} {v[0]:5} chars, {v[1]} 'Dr.'")
