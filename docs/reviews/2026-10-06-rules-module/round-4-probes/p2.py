from common import *
s=sched()
card=BookingCard(caller=new())
card.choices=Choices(specialty="Dermatology", visit_type_id="appt_027")
card.preferences.doctor_name_heard="Dr. Daniel Chen"
r=fo(card.caller,"appt_027",card.preferences,s); card.remember_offer(r.options); show(r)
o=r.options[0]; card.choices.provider_id,card.choices.location_id,card.choices.slot=o.provider_id,o.location_id,o.start
print("-- someone else"); card.change_choice("doctor","someone else")
r=fo(card.caller,"appt_027",card.preferences,s); card.remember_offer(r.options); show(r)
print("-- actually Dr. Daniel Chen is fine"); card.change_choice("doctor","Dr. Daniel Chen")
r=fo(card.caller,"appt_027",card.preferences,s); card.remember_offer(r.options); show(r)
o=r.options[0]; card.choices.provider_id,card.choices.location_id,card.choices.slot=o.provider_id,o.location_id,o.start
print("chosen", o.spoken)
print("-- Thursday instead"); card.change_choice("time","Thursday")
print(card.preferences)
r=fo(card.caller,"appt_027",card.preferences,s); show(r)
print(card.summary(cat))
