from common import *
from clinic.rules import valid_pairs
langs = sorted({l for p in cat.providers.values() for l in p.languages})
print(langs)
cnt=0
for vt in cat.visit_types.values():
    if not can_book_visit_type(cat, NEW, vt.id).bookable: continue
    for lang in langs:
        offering_speakers = [p for p in cat.providers_offering(vt.id) if lang in p.languages]
        r = fo(NEW, vt.id, language=lang)
        imp = [n for n in r.notes if n.kind==WISH_IMPOSSIBLE]
        if imp and offering_speakers:
            cnt+=1
            if cnt<=4:
                print(vt.name, lang, "|", imp[0], "| but offered by:", [(p.name, p.accepting_new_patients) for p in offering_speakers])
print("false 'none speaks' notes for new patients:", cnt)
