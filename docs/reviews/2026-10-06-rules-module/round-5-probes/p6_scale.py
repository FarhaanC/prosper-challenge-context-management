"""Big fake catalog built from the real one: 500 locations, 2,000 doctors, same visit types."""
import copy, json, random, time, statistics
from common import *
from clinic.catalog import DATA_DIR
raw = json.loads((DATA_DIR / "catalog.json").read_text()); ext = json.loads((DATA_DIR / "location_extras.json").read_text())
rng = random.Random(7)
big = copy.deepcopy(raw); bx = copy.deepcopy(ext)
streets = ["Oak", "Pine", "Elm", "Cedar", "Maple", "Birch", "Ash", "Spruce", "Willow", "Hazel"]
big["locations"] = []; bx["locations"] = {}
for i in range(500):
    base = raw["locations"][i % 8]
    lid = f"loc_{i:04d}"
    big["locations"].append({**base, "id": lid, "name": f"{base['name'].split()[0]} Clinic {i}",
                             "address": f"{100+i} {rng.choice(streets)} St"})
    b = ext["locations"][base["id"]]
    bx["locations"][lid] = {"also_called": [], "lat": b["lat"] + rng.uniform(-.05, .05), "lon": b["lon"] + rng.uniform(-.05, .05)}
first = ["Ana", "Ben", "Cara", "Dev", "Eli", "Fay", "Gus", "Hana", "Ivan", "Jo", "Kai", "Lea", "Mo", "Nia", "Oto", "Pia"]
big["providers"] = []
for i in range(2000):
    p = copy.deepcopy(raw["providers"][i % 50])
    p["id"] = f"prov_{i:05d}"
    p["name"] = f"Dr. {rng.choice(first)} {p['name'].split()[-1]}{'' if i < 50 else i // 50}"
    p["location_ids"] = sorted(rng.sample([l["id"] for l in big["locations"]], rng.randint(1, 4)))
    big["providers"].append(p)
t = time.perf_counter(); c = Catalog(big, bx); print(f"load big catalog: {time.perf_counter()-t:.2f}s")
def timeit(label, fn, n=3):
    ts = []
    for _ in range(n):
        t = time.perf_counter(); fn(); ts.append(time.perf_counter() - t)
    print(f"{label:55} median {statistics.median(ts)*1000:7.0f} ms  max {max(ts)*1000:7.0f} ms")
newc, retc = new(), ret()
vt = "appt_027"; gen = "appt_002"
s = Schedule(c)
down = [p.id for p in c.providers_offering(gen)][:300]
for vtid in (vt, gen):
    timeit(f"{vtid} no wishes", lambda: find_options(c, Schedule(c), retc, vtid, Preferences(), NOW))
    timeit(f"{vtid} surname wish 'Dr. Chen'", lambda: find_options(c, Schedule(c), retc, vtid, Preferences(doctor_name_heard="Dr. Chen"), NOW))
    timeit(f"{vtid} place + language + day", lambda: find_options(c, Schedule(c), retc, vtid, Preferences(location_hint="near Union Square", language="Arabic", days=["Thursday"]), NOW))
    timeit(f"{vtid} 300 turned down + name heard", lambda: find_options(c, Schedule(c), retc, vtid, Preferences(not_provider_ids=down, doctor_name_heard="Dr. Kim", language="Klingon"), NOW))
card = BookingCard(caller=retc); card.preferences.not_provider_ids = down; card.preferences.doctor_name_heard = "Dr. Ana Chen"
timeit("summary with 300 turned down + a heard name", lambda: card.summary(c), n=5)
# all doctors offering the general visit turned down -> no_other_doctor
alld = [p.id for p in c.providers_offering(gen)]
r = find_options(c, Schedule(c), retc, gen, Preferences(not_provider_ids=alld), NOW)
print("no_other_doctor note length:", len(r.notes[0].say) if r.notes else None, "chars;", r.notes[0].say[:160] if r.notes else "")
timeit("everyone turned down (no_other_doctor)", lambda: find_options(c, Schedule(c), retc, gen, Preferences(not_provider_ids=alld), NOW))
# real catalog for comparison
s0 = Schedule(cat)
timeit("REAL catalog, appt_002 no wishes", lambda: find_options(cat, Schedule(cat), retc, gen, Preferences(), NOW), n=5)
