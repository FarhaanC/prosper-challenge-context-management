from common import *
# someone else phrases
for phrase in ["someone else please","Someone else, please","can I see someone else","the other doctor","a different one",
               "anybody else","somebody different","not him","not her","not that doctor","no, not Dr. Chen","anyone but Dr. Chen",
               "different doctor please","another one please","I'd like a different doctor", "not Dr Chen", "NOT DR. CHEN", "not  Dr. Chen", "not"]:
    card=BookingCard(caller=new())
    card.choices=Choices(specialty="Dermatology", visit_type_id="appt_027")
    card.preferences.doctor_name_heard="Dr. Daniel Chen"
    r=fo(card.caller,"appt_027",card.preferences); card.remember_offer(r.options)
    card.change_choice("doctor", phrase)
    p=card.preferences
    r2=fo(card.caller,"appt_027",p)
    print(repr(phrase), "heard=",repr(p.doctor_name_heard), "not_ids=",p.not_provider_ids, "not_names=",p.not_doctor_names)
    print("   ", [n.kind+":"+n.say[:90] for n in r2.notes], {o.provider_name for o in r2.options})
