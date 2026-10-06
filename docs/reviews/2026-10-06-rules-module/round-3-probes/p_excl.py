from common import *
skin = vt("Skin Cancer Screening")
p = Preferences(not_provider_ids=["prov_027"], location_hint="the Midtown one")
print("Kim turned down, then Midtown:"); show(find_options(cat, sch, NEW, skin, p, NOW))
p = Preferences(not_provider_ids=["prov_027"], language="Spanish", latest="language")
print("Kim turned down, then Spanish:"); show(find_options(cat, sch, NEW, skin, p, NOW))
# check data types
import json, copy
from clinic.catalog import DATA_DIR
raw = json.load(open(DATA_DIR/"catalog.json")); ex = json.load(open(DATA_DIR/"location_extras.json"))
for label, mut in [("duration 'abc'", lambda r: r["appointment_types"][0].__setitem__("duration_min","abc")),
                   ("languages None", lambda r: r["providers"][0].__setitem__("languages", None)),
                   ("location_ids string", lambda r: r["providers"][0].__setitem__("location_ids", "loc_001")),
                   ("record not a dict", lambda r: r["providers"].append("oops")),
                   ("capabilities None", lambda r: r["locations"][0].__setitem__("capabilities", None))]:
    r = copy.deepcopy(raw); mut(r)
    try: Catalog(r, ex); print(label, "-> loaded OK")
    except CatalogError as e: print(label, "-> CatalogError", str(e).splitlines()[1][:80])
    except Exception as e: print(label, "->", type(e).__name__, e)
