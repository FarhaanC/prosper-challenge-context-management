"""Fake open times (build decisions, 'Fake data'): Mon-Fri 8:00-17:00, lunch 12-13
blocked, 30-minute blocks, ~14 days ahead, >= 2 h notice, visit must fit in
consecutive free blocks and end by closing, repeatable, no double booking, a doctor
at exactly one location per weekday."""

import os
import subprocess
import sys
from datetime import datetime, time, timedelta
from pathlib import Path

import pytest

from clinic import Schedule
from conftest import NOW
from reference import LOC, PROV, VT

DURATIONS = sorted({v["duration_min"] for v in VT.values()})
PAIRS = [(pid, lid) for pid, p in PROV.items() for lid in p["location_ids"]]


def overlaps_lunch(start, dur):
    end = start + timedelta(minutes=dur)
    lunch_s = start.replace(hour=12, minute=0)
    lunch_e = start.replace(hour=13, minute=0)
    return start < lunch_e and end > lunch_s


def test_every_slot_obeys_hours_lunch_notice_horizon(schedule):
    bad = []
    for pid, lid in PAIRS:
        for dur in DURATIONS:
            for s in schedule.open_slots(pid, lid, dur, NOW):
                end = s + timedelta(minutes=dur)
                if (s.weekday() >= 5 or s.time() < time(8) or end.time() > time(17) or end.date() != s.date()
                        or overlaps_lunch(s, dur) or s < NOW + timedelta(hours=2)
                        or s.date() > (NOW + timedelta(days=14)).date() or s.minute not in (0, 30)
                        or s.second or s.microsecond):
                    bad.append((pid, lid, dur, s))
    assert not bad, bad[:5]


def test_slots_sorted_and_unique(schedule):
    for pid, lid in PAIRS[:20]:
        s = schedule.open_slots(pid, lid, 30, NOW)
        assert s == sorted(set(s))


def test_doctor_at_one_location_per_day(schedule):
    bad = []
    for pid, p in PROV.items():
        for off in range(15):
            day = (NOW + timedelta(days=off)).date()
            at = {lid for lid in p["location_ids"]
                  if any(s.date() == day for s in schedule.open_slots(pid, lid, 10, NOW))}
            if len(at) > 1:
                bad.append((pid, day, at))
    assert not bad


def test_every_doctor_location_pair_gets_some_working_day(schedule):
    """Otherwise a valid pair could never be offered."""
    missing = [(pid, lid) for pid, lid in PAIRS
               if not schedule.open_slots(pid, lid, 10, NOW)]
    assert not missing


def test_longer_visit_needs_consecutive_blocks(schedule):
    """A 60-minute start must also be a valid 30-minute start, and the block after it too."""
    for pid, lid in PAIRS[:30]:
        thirty = set(schedule.open_slots(pid, lid, 30, NOW))
        for s in schedule.open_slots(pid, lid, 60, NOW):
            assert s in thirty and s + timedelta(minutes=30) in thirty
        for s in schedule.open_slots(pid, lid, 45, NOW):
            assert s in thirty and s + timedelta(minutes=30) in thirty
        for s in schedule.open_slots(pid, lid, 10, NOW):
            assert s in thirty  # 10 min still occupies one whole block


def test_last_start_respects_visit_length(schedule):
    for pid, lid in PAIRS:
        for s in schedule.open_slots(pid, lid, 60, NOW):
            assert s.time() <= time(16, 0)
        for s in schedule.open_slots(pid, lid, 45, NOW):
            assert s.time() <= time(16, 0)  # 16:30 + 45 = 17:15, too late


def test_repeatable_in_same_process(catalog):
    a, b = Schedule(catalog), Schedule(catalog)
    for pid, lid in PAIRS[:15]:
        assert a.open_slots(pid, lid, 30, NOW) == b.open_slots(pid, lid, 30, NOW)


def test_repeatable_across_processes():
    backend = Path(__file__).resolve().parent.parent
    code = ("import sys; sys.path.insert(0, %r); from datetime import datetime; from clinic import *;"
            "c=Catalog.load(); s=Schedule(c);"
            "print([str(x) for x in s.open_slots('prov_014','loc_004',45,datetime(2026,10,6,9))])") % str(backend)
    outs = set()
    for seed in ("1", "2", "random"):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        outs.add(subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env).stdout)
    assert len(outs) == 1 and "2026" in outs.pop()


def test_roughly_half_taken(schedule):
    """Not a hard rule, but a near-empty or near-full calendar would make the demo meaningless."""
    total = free = 0
    for pid, lid in PAIRS:
        free += len(schedule.open_slots(pid, lid, 10, NOW))
    # blocks a doctor works in 2 weeks: ~11 weekdays x 16 blocks
    total = len(PROV) * 11 * 16
    assert 0.2 < free / total < 0.8


def test_weekend_now(schedule):
    sat = datetime(2026, 10, 10, 10, 0)
    for pid, lid in PAIRS[:20]:
        for s in schedule.open_slots(pid, lid, 30, sat):
            assert s.date() >= datetime(2026, 10, 12).date()


def test_notice_period_edge(schedule):
    now = datetime(2026, 10, 6, 9, 10)
    for pid, lid in PAIRS:
        for s in schedule.open_slots(pid, lid, 30, now):
            assert s >= datetime(2026, 10, 6, 11, 30) or s.date() > now.date()


def test_late_in_day_nothing_today(schedule):
    now = datetime(2026, 10, 6, 15, 30)
    for pid, lid in PAIRS:
        for s in schedule.open_slots(pid, lid, 10, now):
            assert s.date() > now.date()


def test_booking_removes_slot_and_overlaps(catalog):
    sch = Schedule(catalog)
    pid, lid = "prov_014", "loc_004"
    s60 = sch.open_slots(pid, lid, 60, NOW)
    assert s60
    start = s60[0]
    sch.book(pid, start, 60)
    after30 = sch.open_slots(pid, lid, 30, NOW)
    assert start not in after30 and start + timedelta(minutes=30) not in after30
    # a 60-minute visit starting 30 minutes earlier would overlap
    assert start - timedelta(minutes=30) not in sch.open_slots(pid, lid, 60, NOW)


def test_booking_45_blocks_two_blocks(catalog):
    sch = Schedule(catalog)
    pid, lid = "prov_015", "loc_005"
    s = sch.open_slots(pid, lid, 45, NOW)[0]
    sch.book(pid, s, 45)
    assert s + timedelta(minutes=30) not in sch.open_slots(pid, lid, 15, NOW)


def test_short_booking_blocks_longer_visit_containing_it(catalog):
    sch = Schedule(catalog)
    pid, lid = "prov_015", "loc_005"
    s = sch.open_slots(pid, lid, 60, NOW)[0]
    sch.book(pid, s + timedelta(minutes=30), 15)
    assert s not in sch.open_slots(pid, lid, 60, NOW)


def test_booking_one_doctor_does_not_affect_another(catalog):
    sch = Schedule(catalog)
    before = sch.open_slots("prov_015", "loc_005", 30, NOW)
    s = sch.open_slots("prov_014", "loc_004", 30, NOW)[0]
    sch.book("prov_014", s, 30)
    assert sch.open_slots("prov_015", "loc_005", 30, NOW) == before


def test_double_booking_refused_by_final_check(catalog):
    from clinic import check_booking
    from conftest import returning
    sch = Schedule(catalog)
    james = returning(["Radiology"])
    s = sch.open_slots("prov_014", "loc_004", 45, NOW)[0]
    assert check_booking(catalog, sch, james, "appt_065", "prov_014", "loc_004", s, NOW) == []
    sch.book("prov_014", s, 45)
    assert check_booking(catalog, sch, james, "appt_065", "prov_014", "loc_004", s, NOW)


def test_spoken_time():
    from clinic import spoken_time
    assert spoken_time(datetime(2026, 10, 13, 9, 30)) == "Tuesday 13 October at 9:30 AM"
    assert spoken_time(datetime(2026, 10, 13, 14, 0)) == "Tuesday 13 October at 2 PM"
    assert spoken_time(datetime(2026, 10, 13, 12, 0)) == "Tuesday 13 October at 12 PM"
