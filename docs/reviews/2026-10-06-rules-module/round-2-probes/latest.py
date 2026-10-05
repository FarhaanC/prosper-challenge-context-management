from common import *
SK="appt_027"
print("-- heard doctor + location change (latest='location'), via the card:")
c = BookingCard(caller=NEW, preferences=Preferences(doctor_name_heard="Dr. Daniel Chen"))
c.choices.visit_type_id = SK
c.change_choice("location", "the Midtown one")
print(c.preferences)
show(find_options(cat, Schedule(cat), NEW, SK, c.preferences, NOW))
print("-- same but latest='place' (the name the sort key expects):")
p = Preferences(doctor_name_heard="Dr. Daniel Chen", location_hint="the Midtown one", latest="place")
show(find_options(cat, Schedule(cat), NEW, SK, p, NOW))
print("-- heard doctor + time change to a day he can't do")
c = BookingCard(caller=NEW, preferences=Preferences(doctor_name_heard="Dr. Daniel Chen", location_hint="Richmond"))
c.choices.visit_type_id = SK
c.change_choice("time", days=["Wednesday"])
print(c.preferences); show(find_options(cat, Schedule(cat), NEW, SK, c.preferences, NOW))
