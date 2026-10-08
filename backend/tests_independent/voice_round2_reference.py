"""Helpers for the round-2 voice tests (build 25c3f91, decisions 50-55).

Expected answers come from round-2-spec-changes.md, INTERFACE.md, the decisions, the raw
data (reference.py / voice_reference.py) and the rules module's own fake calendar
(clinic.Schedule), which decides which times exist. Nothing is copied from the output of
backend/call/ or backend/agent_builder/.
"""

from __future__ import annotations

import re

from clinic import Schedule
from voice_reference import NOW, VT, interface_tools, snapshot, step

# One line of {visit_types}: "- appt_068: Mammogram (30 min): can book" or
# "- appt_065: MRI - Knee: can't book (reason)". Learned by calling the code (the spec
# gives the content, not the punctuation); the length is optional.
VT_LINE = re.compile(r"^- (appt_\d+): (.+?)(?: \((\d+) min\))?: (can book|can't book)(?: \((.+)\))?\s*$")


def visit_type_lines(text):
    """{visit type id: (name, minutes or None, can_book, reason)} for every visit-type line."""
    rows = {}
    for line in text.splitlines():
        m = VT_LINE.match(line.strip())
        if m:
            vid, name, minutes, mark, reason = m.groups()
            rows[vid] = (name, int(minutes) if minutes else None, mark == "can book", reason or "")
    return rows


def visit_types_of(specialty):
    return {vid for vid, v in VT.items() if v["specialty"] == specialty}


def open_starts(catalog, pairs, minutes, day_ok=None, time_ok=None, now=NOW):
    """Every open start time for these (doctor, place) pairs, from a fresh fake calendar."""
    sched = Schedule(catalog)
    out = []
    for pid, lid in pairs:
        for st in sched.open_slots(pid, lid, minutes, now):
            if (day_ok is None or day_ok(st)) and (time_ok is None or time_ok(st)):
                out.append((st, pid, lid))
    return sorted(out)


def fields_of(tool):
    """The field names INTERFACE.md shows for a tool."""
    return set(interface_tools()[tool][3])


def refused_unchanged(s, tool, args):
    """The tool refuses (ok false, with a message) and changes nothing at all."""
    before = snapshot(s)
    out = step(s, tool, args)
    assert out.result.get("ok") is False, (tool, args, out.result)
    assert out.next_stage is None, (tool, args, out.next_stage)
    # answer_question's own refusals say why under "message" (the rules module's facts lookup);
    # the spec doesn't name the key, so any of the three counts.
    msg = out.result.get("error") or out.result.get("say") or out.result.get("message") or ""
    assert msg.strip(), f"a refusal must say why: {out.result}"
    assert snapshot(s) == before, f"a refused {tool} changed the call: {args}"
    return msg
