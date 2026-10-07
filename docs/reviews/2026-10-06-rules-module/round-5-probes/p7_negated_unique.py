from common import *
s = Schedule(cat)
smith = [p for p in cat.providers.values() if p.name == "Dr. Daniel Smith"][0]
print("Smiths in catalog:", [p.name for p in cat.providers.values() if p.name.endswith("Smith")])
card = card_for(new(), "appt_027")
card.turn_down_doctors(cat, provider_ids=[smith.id])          # the AI did the right thing first
print("turned down:", card.preferences.not_provider_ids)
card.change_choice("doctor", "not Dr. Daniel Smith")          # ...then passed the caller's words by mistake
r = search(s, card); show(r)
print(" summary:", card.summary(cat).split("\n")[-2:])
print("== patient data: odd date of birth and a repeated id load silently?")
from clinic import PatientDirectory
d = PatientDirectory([{"id": "p1", "name": "Ann Lee", "date_of_birth": "12/03/1984"},
                      {"id": "p1", "name": "Bo Chan", "date_of_birth": "1990-01-01"}])
print("  loaded", len(d.records), "records; lookup Ann Lee 1984-12-03 ->", d.lookup("Ann Lee", "1984-12-03").status)
