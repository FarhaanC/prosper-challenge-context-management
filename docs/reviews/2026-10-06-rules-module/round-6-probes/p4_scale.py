"""Speed on a big generated catalog: 500 locations, 2,000 doctors, the real 82 visit types."""
import random, statistics, time
from common import *
from clinic import answer_question
rng = random.Random(7)
raw = copy.deepcopy(RAW)
extras = copy.deepcopy(EXTRAS)
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
vts = raw["appointment_types"]
by_spec = {}
for a in vts:
    by_spec.setdefault(a["specialty"], []).append(a["id"])
specs = sorted(by_spec)
raw["providers"] = []
for i in range(2000):
    s = rng.choice(specs)
    raw["providers"].append({"id": f"prov_{i:04d}", "name": f"Dr. {rng.choice(first)} {rng.choice(last)}", "title": "MD",
                             "specialty": s, "location_ids": rng.sample([l["id"] for l in raw["locations"]], rng.randint(1, 4)),
                             "accepting_new_patients": rng.random() < 0.7, "languages": ["English"] + rng.sample(["Spanish", "Mandarin", "Hindi"], 1),
                             "appointment_type_ids": by_spec[s] + (by_spec.get("General", []) if rng.random() < 0.3 else [])})
t = time.perf_counter(); cat = Catalog(raw, extras); load = time.perf_counter() - t
sch = Schedule(cat)
ret = Caller("x", "p", False, cat.specialties())
offer = {vt: len(cat.providers_offering(vt)) for vt in cat.visit_types}
big = max(offer, key=offer.get)
print(f"load {load:.3f}s; biggest visit type {cat.visit_types[big].name} offered by {offer[big]} doctors")

def timeit(label, fn, n=5):
    times = []
    for _ in range(n):
        t = time.perf_counter(); r = fn(); times.append(time.perf_counter() - t)
    print(f"{label:60} {min(times)*1000:7.0f}-{max(times)*1000:5.0f} ms   notes={[x.kind for x in getattr(r, 'notes', [])]}")
    return r

skin = "appt_027"
timeit("skin check, no wishes (fresh schedule each run)", lambda: find_options(cat, Schedule(cat), NEW, skin, Preferences(), NOW))
timeit(f"{cat.visit_types[big].name}, no wishes", lambda: find_options(cat, Schedule(cat), ret, big, Preferences(), NOW))
timeit(f"{cat.visit_types[big].name}, Thursday morning + Spanish", lambda: find_options(
    cat, Schedule(cat), ret, big, Preferences(days=["Thursday"], time_of_day="morning", language="Spanish"), NOW))
timeit(f"{cat.visit_types[big].name}, 'Dr. Chen' (many matches)", lambda: find_options(
    cat, Schedule(cat), ret, big, Preferences(doctor_name_heard="Dr. Chen"), NOW))
timeit(f"{cat.visit_types[big].name}, near Hood3", lambda: find_options(
    cat, Schedule(cat), ret, big, Preferences(location_hint="near Hood3"), NOW))
everyone = [p.id for p in cat.providers_offering(big)]
r = timeit(f"{cat.visit_types[big].name}, everyone turned down", lambda: find_options(
    cat, Schedule(cat), ret, big, Preferences(not_provider_ids=everyone), NOW))
print("   no_other_doctor note length:", max((len(n.say) for n in r.notes), default=0), "chars")
timeit(f"{cat.visit_types[big].name}, unknown language Klingon", lambda: find_options(
    cat, Schedule(cat), ret, big, Preferences(language="Klingon"), NOW))
timeit(f"{cat.visit_types[big].name}, 2026-10-10 (a Saturday)", lambda: find_options(
    cat, Schedule(cat), ret, big, Preferences(days=["2026-10-10"]), NOW))
card = BookingCard(caller=ret); card.preferences.not_provider_ids = everyone[:300]
timeit("card summary with 300 doctors turned down", lambda: card.summary(cat))
timeit("answer_question doctor 'Dr. Chen'", lambda: answer_question(cat, "doctor", "Dr. Chen"))
t = time.perf_counter(); r = find_options(catalog, schedule, ret, "appt_002", Preferences(), NOW)
print(f"real catalog, Annual Physical: {(time.perf_counter() - t)*1000:.0f} ms")

r = find_options(cat, Schedule(cat), ret, big, Preferences(doctor_name_heard="Dr. Chen"), NOW)
n = r.notes[0]
print(f"\n'Dr. Chen' same-name note on the big catalog: {len(n.say)} chars, {n.say.count('; ') + 1} doctors listed")
print("   starts:", n.say[:230], "...")
worst = 0
for vt in catalog.visit_types:
    for name in ["Dr. Chen", "Dr. Garcia", "Dr. Kim", "Dr. Patel", "Dr. Nguyen"]:
        rr = find_options(catalog, schedule, ret, vt, Preferences(doctor_name_heard=name), NOW)
        for x in rr.notes:
            if x.kind == "doctors_same_name":
                worst = max(worst, x.say.count("; ") + 1)
print("real catalog: most doctors read out in one same-name note:", worst)

chens = [p.id for p in cat.providers.values() if p.name.endswith(" Chen")]
r = find_options(cat, Schedule(cat), ret, big, Preferences(doctor_name_heard="Dr. Chen", not_provider_ids=chens), NOW)
print("\nall Chens turned down, 'Dr. Chen':", [(x.kind, len(x.say), x.say.count("Dr. ")) for x in r.notes])
small = min((vt for vt in cat.visit_types if cat.providers_offering(vt)), key=lambda v: len(cat.providers_offering(v)))
r = find_options(cat, Schedule(cat), ret, small, Preferences(doctor_name_heard="Dr. Chen"), NOW)
print(f"'Dr. Chen' for {cat.visit_types[small].name} (few doctors):", [(x.kind, len(x.say), x.say.count("Dr. ")) for x in r.notes])
