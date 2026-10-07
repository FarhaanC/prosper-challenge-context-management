"""Smaller round-7 checks: exact 'about' names, near as a non-bool, near with an empty
name, language edge cases, the street-name corner cases."""
from common import catalog, BookingCard, Preferences, Choices, answer_question, find_options, NEW, NOW, SKIN, show
from clinic import Schedule

print("--- answer_question about names (spec: case and spaces ignored)")
for about in ["location", "Location", " doctor ", "visit_type", "Visit_Type", "visit type", "Visit Type", "visit-type", "provider"]:
    print(repr(about), answer_question(catalog, about, "Midtown" if "loc" in about.lower() else "Dr. Chen")["found"],
          answer_question(catalog, about, "Midtown")["message"][:60])

print("--- change_choice what names")
for what in ["Visit Type", "visit  type", "VISIT_TYPE", " doctor", "Location"]:
    card = BookingCard(caller=NEW)
    try:
        card.change_choice(what, "x"); print(repr(what), "accepted")
    except ValueError as e:
        print(repr(what), "refused", e)

print("--- near passed as a string")
card = BookingCard(caller=NEW)
card.change_choice("location", "Downtown", near="false")
print("near='false' ->", card.preferences.near, card.summary(catalog))

print("--- near=True with an empty or no-preference name")
for v in ["", "anywhere"]:
    card = BookingCard(caller=NEW)
    card.change_choice("location", v, near=True)
    print(repr(v), card.preferences.location_hint, card.preferences.near)

print("--- languages")
sched = Schedule(catalog)
for lang in ["Spanish", "spanish", "SPANISH", " Spanish ", "Mandarin Chinese", "chinese mandarin", "Chinese", "Klingon",
             "Haitian Creole", "ASL", "French only", "Klingon only", "ideally French", "Spanish only", "only Spanish",
             "Spanish French", "Cantonese Mandarin", "Spanish Klingon", "a b c", "Spanish-speaking", "Spansh",
             "English", "español", "no", "none", "any", "either", "Mandarin  Chinese", "Mandarin-Chinese"]:
    r = find_options(catalog, sched, NEW, "appt_002", Preferences(language=lang), NOW)
    print(f"{lang!r:22}", len(r.options), [(n.kind, n.say[:90]) for n in r.notes])
