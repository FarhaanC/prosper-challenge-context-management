"""Smaller round-6 checks: the card summary with no-preference words, same-name doctors in
the 'only doctor(s) matching' note, 'not far from', answer_question, repeated ids."""
from common import *
from clinic import PatientDirectory, CatalogError, answer_question
SKIN, CONSULT = "appt_027", "appt_000"

print("== A. no-preference words are stored on the card and shown in the summary")
card = BookingCard(caller=NEW)
card.choices = Choices(specialty="Dermatology", visit_type_id=SKIN)
card.change_choice("doctor", "I don't mind")
card.change_choice("location", "anywhere")
card.change_choice("language", "whatever")
card.change_choice("time", days=["any day"], time_of_day="whenever")
print(card.preferences)
print(card.summary(catalog))

print("\n== B. same-name doctors in the 'only doctor(s) matching' note")
garcias = sorted(p.id for p in catalog.providers.values() if p.name.endswith(" Garcia"))
print([(g, catalog.providers[g].name, catalog.providers[g].specialty) for g in garcias])
for name in ["Dr. Garcia", "Dr. Maria Garcia"]:
    r = find_options(catalog, schedule, NEW, CONSULT, Preferences(doctor_name_heard=name, not_provider_ids=garcias), NOW)
    print(name, "->", says(r), sorted({o.provider_name for o in r.options}))
marias = [g for g in garcias if catalog.providers[g].name == "Dr. Maria Garcia"]
r = find_options(catalog, schedule, NEW, CONSULT, Preferences(doctor_name_heard="Dr. Garcia", not_provider_ids=marias), NOW)
print("Marias down, 'Dr. Garcia' ->", says(r), sorted({o.provider_name for o in r.options}))
chens = sorted(p.id for p in catalog.providers.values() if p.name.endswith(" Chen"))
for vt in catalog.visit_types:
    r = find_options(catalog, schedule, Caller("x", "p", False, catalog.specialties()), vt,
                     Preferences(doctor_name_heard="Dr. Chen", not_provider_ids=chens), NOW)
    for n in r.notes:
        if "The only doctors matching" in n.say and n.say.count("Dr. ") > 4:
            print("long:", n.say); break

print("\n== C. 'not far from' (decision 24's near-phrase) vs the round-6 sentence words")
for hint in ["not far from Union Square", "near Union Square", "the Midtown one please"]:
    r = find_options(catalog, schedule, NEW, SKIN, Preferences(location_hint=hint), NOW)
    print(f"{hint!r}: search ->", [n.kind for n in r.notes], len(r.options), "| resolve_place ->",
          catalog.resolve_place(hint).kind, "| answer_question ->", answer_question(catalog, "location", hint)["found"])
for name in ["not Dr. Chen", "another doctor", "Dr. Chen please"]:
    a = answer_question(catalog, "doctor", name)
    print(f"answer_question doctor {name!r}:", a["message"], [x["name"] for x in a.get("results", [])][:3])

print("\n== D. repeated ids")
recs = [{"id": "p1", "name": "Ann Lee", "date_of_birth": "1984-03-12"}] * 3
try:
    PatientDirectory([dict(r) for r in recs])
except CatalogError as e:
    print(e)
raw = copy.deepcopy(RAW)
raw["locations"] += [copy.deepcopy(raw["locations"][0]), copy.deepcopy(raw["locations"][0])]
try:
    Catalog(raw, EXTRAS)
except CatalogError as e:
    print(e)
try:
    PatientDirectory([{"id": "p1", "name": "Ann Lee", "date_of_birth": "1984-03-12"},
                      {"id": "p1 ", "name": "Bo Lee", "date_of_birth": "1985-03-12"}])
    print("'p1' and 'p1 ' both accepted")
except CatalogError as e:
    print(e)
