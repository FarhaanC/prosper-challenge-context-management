from common import *
from clinic.options import _known_language
for l in ["Mandarin Chinese","mandarin","Chinese","not Spanish","no Spanish please","Spanish or English","English is fine","any language","doesn't matter","I don't mind","Cantonese","Brazilian Portuguese","spanish","ESPAÑOL","Español","Arabic speaker","someone who speaks Hindi"]:
    print(repr(l), "->", repr(_known_language(cat,l)))
card=BookingCard(caller=new()); card.choices=Choices(visit_type_id="appt_027")
card.change_choice("language","any language"); print("card lang", repr(card.preferences.language))
r=fo(card.caller,"appt_027",card.preferences); show(r)
