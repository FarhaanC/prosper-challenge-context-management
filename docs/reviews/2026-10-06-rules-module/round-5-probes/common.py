import sys
from datetime import datetime
from pathlib import Path
BACKEND = Path(__file__).resolve().parent.parent / "work" / "backend"
sys.path.insert(0, str(BACKEND))
from clinic import *  # noqa
from clinic import Catalog, Schedule, Caller, BookingCard, Choices, Preferences, find_options
NOW = datetime(2026, 10, 6, 9, 0)
cat = Catalog.load()
def new(): return Caller(name="A B", is_new_patient=True)
def ret(refs=None): return Caller(name="A B", patient_id="x", is_new_patient=False, referrals_on_file=list(refs if refs is not None else cat.specialties()))
def card_for(caller, vt):
    c = BookingCard(caller=caller); c.choices = Choices(specialty=cat.visit_types[vt].specialty, visit_type_id=vt); return c
def search(sched, card):
    r = find_options(cat, sched, card.caller, card.choices.visit_type_id, card.preferences, NOW, first_option_number=card.next_option_number)
    card.remember_offer(r.options); return r
def choose(card, o):
    card.choices.provider_id, card.choices.location_id, card.choices.slot = o.provider_id, o.location_id, o.start
def show(r):
    for n in r.notes: print("   NOTE", n.kind, "|", n.say)
    for o in r.options: print("   OPT", o.option_id, o.spoken)
