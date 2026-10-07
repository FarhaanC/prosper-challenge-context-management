"""Which place phrases does resolve_place still read? Spec round 7 s1 says each listed
phrase form is now 'not recognised' (kind none)."""
from common import catalog

forms = ["near Downtown", "closer to Downtown", "close to Downtown", "next to Downtown", "around Downtown",
         "by Downtown", "on the way to Downtown", "not far from Downtown", "the Downtown one", "the one on Geary",
         "on Geary", "somewhere downtown", "Downtown area", "Downtown side", "Downtown neighbourhood",
         "Downtown location", "Downtown clinic", "Downtown office", "in Downtown", "at Downtown", "to Downtown",
         "from Downtown", "a Downtown", "Downtown one", "Downtown place",
         # leftovers in GENERIC_PLACE_WORDS that are in none of our names
         "Downtown hospital", "Downtown branch", "Downtown site", "Downtown centre", "the Downtown",
         "Downtown of", "Downtown and", "Midtown office", "the Richmond location", "Sunset clinic",
         "Mission Bay clinic", "the clinic", "the office", "the hospital", "office", "location",
         "Downtown and Midtown", "Midtown and Richmond", "Downtown or Midtown"]
for f in forms:
    m = catalog.resolve_place(f)
    print(f"{f!r:32} -> {m.kind:10} {m.location_ids} near={m.near}")
