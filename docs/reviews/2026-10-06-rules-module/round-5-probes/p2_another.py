from common import *
s = Schedule(cat)
andre = [p for p in cat.providers.values() if p.name == "Dr. Andre Patel"][0]
print(andre.id, andre.specialty, andre.accepting_new_patients, andre.appointment_type_ids)
vt = andre.appointment_type_ids[0]
print(cat.visit_types[vt])
card = card_for(new(), vt)
r = search(s, card); show(r)
o = next(o for o in r.options if o.provider_id != andre.id)
choose(card, o)
print("chose", o.provider_name, "; AI wrongly passes 'another doctor'")
card.change_choice("doctor", "another doctor")
r = search(s, card); show(r)
# what other phrases match someone, across many everyday words?
words = ["another", "other", "someone", "somebody", "anyone", "different", "else", "new", "next", "him", "her", "them",
         "that", "one", "male", "female", "lady", "woman", "man", "nobody", "please", "thanks", "okay", "first", "second",
         "earlier", "later", "same", "previous", "original", "senior", "younger", "older", "best", "nicer", "kind"]
for w in words:
    m = cat.match_providers(w)
    if m: print(f"{w!r:12} -> {[x.provider.name for x in m][:5]} {m[0].describe()}")
