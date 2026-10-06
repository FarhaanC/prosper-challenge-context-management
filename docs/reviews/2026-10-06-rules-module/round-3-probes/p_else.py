from common import *
skin = vt("Skin Cancer Screening")
for v in ["someone else", "a different doctor", "another doctor", "not Dr. Chen", "anyone", "any doctor", "whoever"]:
    c = BookingCard(caller=NEW); c.choices.visit_type_id = skin
    c.choices.provider_id, c.choices.location_id = "prov_001", "loc_004"
    c.change_choice("doctor", v)
    r = find_options(cat, sch, NEW, skin, c.preferences, NOW)
    print(repr(v), "excluded:", c.preferences.not_provider_ids, "| notes:", [(n.kind, n.say[:70]) for n in r.notes], "| docs:", sorted({o.provider_name for o in r.options}))
