from common import *
from datetime import datetime
SK="appt_027"
def mk():
    c = BookingCard(caller=NEW); c.choices = Choices("Dermatology", SK, "prov_001", "loc_007", datetime(2026,10,6,11)); return c
for v in ["afternoon", "Thursday afternoon", "next week", "Thursday"]:
    c = mk(); c.change_choice("time", v); r = find_options(cat, Schedule(cat), NEW, SK, c.preferences, NOW)
    print(repr(v), "-> days", c.preferences.days, "tod", repr(c.preferences.time_of_day), "|", [n.kind for n in r.notes], len(r.options))
c = mk(); first = find_options(cat, Schedule(cat), NEW, SK, Preferences(), NOW)
print("first offer:", [(o.provider_name,o.location_name,str(o.start)) for o in first.options])
c.change_choice("doctor", "")
r = find_options(cat, Schedule(cat), NEW, SK, c.preferences, NOW)
print("after 'a different doctor':", [(o.provider_name,o.location_name,str(o.start)) for o in r.options], c.preferences)
# patients
for name, dob in [("James Wilson",None),("John Doe",None),("Emily Braun","1988-01-19"),("May Wong","1995-09-25"),
                  ("Wilson James","1984-03-12"),("James Wilson Jr","1984-03-12"),("James Wilson","1984-02-30"),("James Wilson","1984-3-12"),
                  ("Jim Wilson","1984-03-12"),("Sarah Johnston","1975-07-30"),("Mr James Wilson","1984-03-12"),("Dr. Sarah Johnson","1975-07-30"),
                  ("Robert Taylor-Smith","1962-05-08"),("Mei Wang","1995-09-25"),("Ahmed Khan","1991-11-02")]:
    r = pats.lookup(name, dob); print(f"{name!r:24} {dob!s:11} -> {r.status}")
