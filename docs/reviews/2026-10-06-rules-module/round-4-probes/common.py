import sys
from datetime import datetime
B='/tmp/claude-0/-home-claude/7d014f89-7c13-557c-9246-c7fae4f61e23/scratchpad/round4/work/backend'
sys.path.insert(0,B)
from clinic import *
from clinic.card import parse_time_phrase
cat=Catalog.load(); d=PatientDirectory.load()
NOW=datetime(2026,10,6,9,0)
def sched(): return Schedule(cat)
def new(): return Caller(name="X Y")
def ret(refs=()): return Caller(name="R T", patient_id="p", is_new_patient=False, referrals_on_file=list(refs))
def fo(c, vt, p, s=None, **k): return find_options(cat, s or sched(), c, vt, p, NOW, **k)
def show(r):
    for n in r.notes: print("  NOTE", n.kind, "|", n.say)
    for o in r.options: print("  OPT", o.option_id, o.spoken)
