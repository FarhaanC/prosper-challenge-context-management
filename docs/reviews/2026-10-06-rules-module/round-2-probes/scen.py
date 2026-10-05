from common import *
from datetime import datetime
SK="appt_027"; KNEE="appt_065"; PHYS="appt_002"; ECHO="appt_021"
def card(caller, vt, pid, lid):
    c = BookingCard(caller=caller); c.choices = Choices("Dermatology", vt, pid, lid, datetime(2026,10,8,10)); return c
def run(title, caller, vt, prefs):
    print("==", title, {k:v for k,v in prefs.__dict__.items() if v})
    show(find_options(cat, Schedule(cat), caller, vt, prefs, NOW))
c = card(NEW, SK, "prov_001", "loc_007"); c.change_choice("location","the Midtown one"); run("R1 loc change", NEW, SK, c.preferences)
c = card(NEW, SK, "prov_001", "loc_007"); c.change_choice("time", days=["Wednesday"]); run("R2 time change Wed", NEW, SK, c.preferences)
c = card(NEW, SK, "prov_001", "loc_007"); c.change_choice("location","the Mission one"); run("loc change Mission", NEW, SK, c.preferences)
c = card(NEW, SK, "prov_001", "loc_007"); c.change_choice("doctor","Dr. Kim"); run("doctor change Kim", NEW, SK, c.preferences)
c = card(NEW, SK, "prov_001", "loc_007"); c.change_choice("time", time_of_day="afternoon"); run("time change afternoon only", NEW, SK, c.preferences)
# days lost bug
c = card(NEW, SK, "prov_001", "loc_007"); c.change_choice("time", days=["Thursday"]); c.change_choice("time", time_of_day="afternoon")
print("days after 'Thursday' then 'afternoon':", c.preferences.days, c.preferences.time_of_day)
run("today", NEW, SK, Preferences(days=["today"]))
run("Sat", NEW, SK, Preferences(days=["Saturday"]))
run("morning only impossible?", ALLREF, KNEE, Preferences(days=["2026-10-10"], time_of_day="morning"))
run("past date", NEW, SK, Preferences(days=["2026-10-01"]))
run("far date", NEW, SK, Preferences(days=["2026-12-25"]))
run("ECHO prov_000 Monday", ALLREF, ECHO, Preferences(preferred_provider_id="prov_000", days=["Monday"]))
run("Cohen", NEW, SK, Preferences(doctor_name_heard="Dr. Cohen"))
run("Garcia skin", NEW, SK, Preferences(doctor_name_heard="Dr. Garcia"))
run("Garsha phys", NEW, PHYS, Preferences(doctor_name_heard="Dr. Garsha"))
run("main one", NEW, PHYS, Preferences(location_hint="the main one"))
run("bay area", NEW, PHYS, Preferences(location_hint="anywhere in the bay area"))
run("none", NEW, PHYS, Preferences(location_hint="none"))
run("any doctor", NEW, PHYS, Preferences(doctor_name_heard="any doctor", location_hint="any"))
run("knee near downtown soonest", ALLREF, KNEE, Preferences(location_hint="near downtown", soonest=True))
run("chen + spanish (no latest)", NEW, SK, Preferences(doctor_name_heard="Dr. Daniel Chen", language="Spanish"))
run("mission + doctor chen", NEW, SK, Preferences(doctor_name_heard="Dr. Daniel Chen", location_hint="Mission"))
run("near market street", NEW, PHYS, Preferences(location_hint="near Market Street"))
