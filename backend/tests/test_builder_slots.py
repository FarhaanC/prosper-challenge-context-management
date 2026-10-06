"""The fake calendar's own rules, tested directly (round-2 review, T4)."""

from datetime import datetime, time, timedelta

from catalog_ids import DOWNTOWN, LINDA_RAMIREZ_RADIOLOGY, NOW
from clinic import Schedule


def _all(schedule, catalog, duration, now=NOW):
    for p in catalog.providers.values():
        for lid in p.location_ids:
            for s in schedule.open_slots(p.id, lid, duration, now):
                yield p, lid, s


def test_no_slot_breaks_hours_lunch_notice_or_window(catalog, schedule):
    for _, _, s in _all(schedule, catalog, 45):
        end = s + timedelta(minutes=45)
        assert s.weekday() < 5 and time(8) <= s.time() and end.time() <= time(17)
        assert not (s.time() < time(13) and end.time() > time(12))           # lunch
        assert s >= NOW + timedelta(hours=2)                                  # notice
        assert s.date() <= NOW.date() + timedelta(days=14)                    # window


def test_late_in_the_day_nothing_is_offered_today(catalog, schedule):
    four_thirty = datetime(2026, 10, 6, 16, 30)
    assert all(s.date() > four_thirty.date() for _, _, s in _all(schedule, catalog, 15, four_thirty))


def test_a_doctor_is_at_one_place_per_day_and_every_site_gets_days(catalog, schedule):
    for p in catalog.providers.values():
        days_at = {lid: {s.date() for s in schedule.open_slots(p.id, lid, 15, NOW)} for lid in p.location_ids}
        assert all(days_at.values()), p.id
        for a in p.location_ids:
            for b in p.location_ids:
                assert a == b or not (days_at[a] & days_at[b]), p.id


def test_many_sites_all_get_working_days(catalog):  # R2-11
    import copy
    import json
    from clinic import Catalog
    from clinic.catalog import DATA_DIR
    raw = json.loads((DATA_DIR / "catalog.json").read_text(encoding="utf-8"))
    extras = json.loads((DATA_DIR / "location_extras.json").read_text(encoding="utf-8"))
    raw = copy.deepcopy(raw)
    raw["providers"][0]["location_ids"] = [l["id"] for l in raw["locations"]]  # all 8 sites
    big = Catalog(raw, extras)
    sched = Schedule(big)
    pid = raw["providers"][0]["id"]
    worked = {sched.location_on(pid, NOW.date() + timedelta(days=d)) for d in range(15)} - {None}
    assert worked == set(raw["providers"][0]["location_ids"])


def test_bookings_block_the_right_blocks(catalog):
    sched = Schedule(catalog)
    start = sched.open_slots(LINDA_RAMIREZ_RADIOLOGY, DOWNTOWN, 60, NOW)[0]
    sched.book(LINDA_RAMIREZ_RADIOLOGY, start, 45)
    left = sched.open_slots(LINDA_RAMIREZ_RADIOLOGY, DOWNTOWN, 15, NOW)
    assert start not in left and start + timedelta(minutes=30) not in left
