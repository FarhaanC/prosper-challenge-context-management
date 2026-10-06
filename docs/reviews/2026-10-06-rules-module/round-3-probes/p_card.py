from common import *
for t in ["Thursday afternoon please", "don't mind", "dont mind", "any time on Thursday", "Thursday or Friday", "morning please", "Thursday, any time", "this afternoon", "tomorrow morning", "Anytime", "no preference"]:
    print(repr(t), split_time_words(t))
# someone else before choosing
skin = vt("Skin Cancer Screening")
card = BookingCard(caller=NEW); card.choices.visit_type_id = skin
card.preferences.doctor_name_heard = "Dr. Daniel Chen"
r = find_options(cat, sch, NEW, skin, card.preferences, NOW); print("first:"); show(r)
card.remember_offer(r.options)
card.change_choice("doctor", "")   # "someone else please" - before choosing an option
r = find_options(cat, sch, NEW, skin, card.preferences, NOW); print("after someone else (not chosen):"); show(r)
# chosen, then someone else, then back to Chen
card = BookingCard(caller=NEW); card.choices.visit_type_id = skin
card.choices.provider_id = r.options[0].provider_id if False else "";
