import sys
sys.path.insert(0, "/tmp/claude-0/-home-claude/7d014f89-7c13-557c-9246-c7fae4f61e23/scratchpad/round3/reviewer/backend")
from datetime import datetime
from clinic import *
from clinic.card import split_time_words
cat = Catalog.load(); sch = Schedule(cat); pats = PatientDirectory.load()
NOW = datetime(2026, 10, 6, 9, 0)  # Tuesday
NEW = Caller("New Person")
JW = pats.lookup("James Wilson", "1984-03-12").caller
def vt(name): return next(v.id for v in cat.visit_types.values() if v.name == name)
def show(r):
    for n in r.notes: print("   NOTE", n.kind, "|", n.say)
    for o in r.options: print("   OPT", o.option_id, o.spoken)
