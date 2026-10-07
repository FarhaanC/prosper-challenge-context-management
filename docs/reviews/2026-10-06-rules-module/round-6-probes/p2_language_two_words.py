"""Language values of two words where one is a language we have: the code keeps that one
and silently drops the other word. Spec round 6 s6: "two language names ('English Spanish')
are refused like other non-names"; round 5 s5: a value "that isn't one or two words naming
a language" is refused."""
from common import *
PHYSICAL = "appt_002"
for value in ["English Spanish", "Spanish French", "French Spanish", "Cantonese Mandarin", "Spanish Klingon",
              "Spanish only", "only Spanish", "Spanish ideally", "Spanish preferred", "Mandarin Chinese",
              "Haitian Creole", "Brazilian Portuguese", "no", "none", "No Spanish"]:
    r = find_options(catalog, schedule, NEW, PHYSICAL, Preferences(language=value), NOW)
    langs = {l for o in r.options for l in catalog.providers[o.provider_id].languages}
    print(f"{value!r:24} options={len(r.options)} notes={says(r)} every option speaks: "
          f"{sorted(set.intersection(*[set(catalog.providers[o.provider_id].languages) for o in r.options])) if r.options else '-'}")
