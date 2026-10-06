from common import *
skin = vt("Skin Cancer Screening")
def fresh():
    c = BookingCard(caller=NEW); c.choices.visit_type_id = skin; return c
c = fresh()
c.change_choice("time", days=["Thursday"]); c.change_choice("time", time_of_day="afternoon"); print("R2-2a", c.preferences.days, c.preferences.time_of_day)
c = fresh(); c.change_choice("time", "Thursday morning"); print("R2-2b", c.preferences.days, c.preferences.time_of_day)
c.change_choice("time", "afternoon"); print("R2-2c", c.preferences.days, c.preferences.time_of_day)
c.change_choice("time", "any time"); print("R2-2d", c.preferences.days, repr(c.preferences.time_of_day))
c = fresh(); c.change_choice("time", time_of_day="morning"); c.change_choice("time", days=["any time"]); print("R2-2e days=['any time']", c.preferences.days, repr(c.preferences.time_of_day))
c = fresh(); c.change_choice("time", "Thursday morning"); c.change_choice("time", days=["Friday"]); print("days only:", c.preferences.days, c.preferences.time_of_day)
c = fresh(); c.change_choice("time", "Thursday", time_of_day="any"); print("tod any:", c.preferences.days, repr(c.preferences.time_of_day))

# chosen doctor, someone else, then back
c = fresh()
r = find_options(cat, sch, NEW, skin, c.preferences, NOW); o = r.options[0]
c.choices.provider_id, c.choices.location_id, c.choices.slot = o.provider_id, o.location_id, o.start
print("chosen", o.spoken)
c.change_choice("doctor", "")
print("excluded:", c.preferences.not_provider_ids)
r = find_options(cat, sch, NEW, skin, c.preferences, NOW); show(r)
c.change_choice("doctor", o.provider_name)   # "actually, go back to Dr. Kim"
print("back to", o.provider_name, "excluded still:", c.preferences.not_provider_ids)
r = find_options(cat, sch, NEW, skin, c.preferences, NOW); show(r)
