import sys
sys.path.insert(0, '/tmp/claude-0/-home-claude/7d014f89-7c13-557c-9246-c7fae4f61e23/scratchpad/round2/reviewer/backend')
from datetime import datetime
from clinic import *
from clinic.options import *
cat = Catalog.load(); pats = PatientDirectory.load()
NOW = datetime(2026,10,6,9,0)
NEW = Caller("New")
RET = Caller("R","pat_x",False,[])
ALLREF = Caller("A","pat_y",False,cat.specialties())
def fo(caller, vt, **kw):
    r = find_options(cat, Schedule(cat), caller, vt, Preferences(**kw), NOW)
    return r
def show(r):
    for n in r.notes: print("   NOTE", n.kind, "|", n)
    for o in r.options: print("   OPT", o.option_id, o.spoken)
