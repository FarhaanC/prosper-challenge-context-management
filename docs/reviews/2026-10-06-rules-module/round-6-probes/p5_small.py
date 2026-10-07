"""Small checks: one id on its own, lenient weekday words, an empty neighbourhood,
the builder test's dead branch, and the stale docstring example."""
from common import *
import clinic.options as options
card = BookingCard(caller=NEW); card.choices = Choices(specialty="Dermatology", visit_type_id="appt_027")
card.turn_down_doctors(catalog, provider_ids="prov_001"); print("one id on its own:", card.preferences.not_provider_ids)
for d in ["thus", "thursdays", "wednes", "frid", "satu", "Thu."]:
    r = find_options(catalog, schedule, NEW, "appt_027", Preferences(days=[d]), NOW)
    print(f"day {d!r}: accepted={not any(n.kind == 'bad_input' for n in r.notes)} weekdays={sorted({o.start.strftime('%a') for o in r.options})}")
x = copy.deepcopy(EXTRAS); x["locations"]["loc_005"]["neighbourhood"] = ""; Catalog(RAW, x); print("empty neighbourhood: loads")
print("appt_001 exists (builder test's 'else' branch is dead):", "appt_001" in catalog.visit_types)
print("options.py docstring example:", [l.strip() for l in options.__doc__.splitlines() if "Klingon" in l])
r = find_options(catalog, schedule, NEW, "appt_027", Preferences(language="Klingon"), NOW); print("actual:", says(r))
print("BAD_INPUT comment vs use:", [n.kind for n in find_options(catalog, schedule, NEW, "appt_027", Preferences(doctor_name_heard="not Dr. Chen"), NOW).notes])
