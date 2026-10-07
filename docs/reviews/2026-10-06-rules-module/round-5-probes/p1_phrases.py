from common import *
s = Schedule(cat)
for phrase in ["someone else", "somebody else", "another doctor", "a different doctor", "other doctor", "anyone else",
               "Someone else, please", "the other one", "not him", "not Dr. Chen", "No, not Dr. Chen", "anyone but Dr. Chen",
               "not Dr. Daniel Chen", "someone other than Dr. Kim", "different one", "next doctor", "a new doctor", "no one"]:
    card = card_for(new(), "appt_027")
    r = search(s, card); choose(card, r.options[0])
    card.change_choice("doctor", phrase)
    r = search(s, card)
    print(repr(phrase), "turned down:", card.preferences.not_provider_ids, "matches:", [p.name for p in cat.find_providers_by_name(phrase)][:8])
    show(r)
