"""Voice stages, area 8: the call log and the bookings file.

45: each call writes one file: one line for every stage move (with the instructions the
AI was given) and every tool call (what was sent, what came back, the booking card).
48: bookings are saved one per line and reloaded at start-up, so a saved time is never
offered again; a damaged line stops start-up with a message naming the line.
INTERFACE: Clinic(..., bookings_file=path_or_None, log_dir=path_or_None).
slots.py (rules module): all times are clinic time; code needing "now" must not use the
computer's own clock, because the computer may be anywhere (e.g. Dubai).
"""

import json
from datetime import datetime

import pytest

from call import BookingsFileError, Clinic, read_bookings
from voice_reference import (BACKEND, BOOKING, END, IDENTIFY, JAMES, KNEE_MRI, NEW, NOW, SKIN_CHECK, VISIT_TYPE,
                             make_clinic, new_call, step, to_booking)


def book(clinic, who=JAMES, vt=KNEE_MRI, pick=0):
    s = to_booking(clinic, vt, who)
    o = s.card.offered_options[pick]
    step(s, "choose_option", {"option_id": o.option_id})
    out = step(s, "confirm_booking", {})
    assert out.result["ok"] is True
    return s, o


def lines(path):
    return path.read_text(encoding="utf-8").splitlines()


# ------------------------------------------------------------------ call log
def test_one_log_file_per_call(catalog, directory, tmp_path):
    clinic = make_clinic(catalog, directory, log_dir=tmp_path / "logs")
    a, b = new_call(clinic), new_call(clinic)
    assert a.log_path != b.log_path
    for s in (a, b):
        assert s.log_path.parent == tmp_path / "logs"
        assert s.log_path.exists()


def test_log_lines_record_every_stage_move_and_tool_call_in_order(catalog, directory, tmp_path):
    clinic = make_clinic(catalog, directory, log_dir=tmp_path / "logs")
    s = new_call(clinic)
    calls = [("start_booking", dict(NEW)), ("list_visit_types", {"specialty": "Dermatology"}),
             ("choose_visit_type", {"visit_type_id": SKIN_CHECK}), ("choose_option", {"option_id": "1"}),
             ("choose_option", {"option_id": "99"})]
    outs = [step(s, t, a) for t, a in calls]
    events = [json.loads(x) for x in lines(s.log_path)]
    assert all(isinstance(e, dict) for e in events)
    assert {e["event"] for e in events} <= {"stage", "tool"}
    shape = [(e["event"], e.get("stage") if e["event"] == "stage" else e["tool"]) for e in events]
    assert shape == [("stage", IDENTIFY), ("tool", "start_booking"), ("stage", VISIT_TYPE),
                     ("tool", "list_visit_types"), ("tool", "choose_visit_type"), ("stage", BOOKING),
                     ("tool", "choose_option"), ("tool", "choose_option")]
    tools = [e for e in events if e["event"] == "tool"]
    for e, (tool, args), out in zip(tools, calls, outs):
        assert e["args"] == args, "what was sent"
        assert e["result"] == json.loads(json.dumps(out.result, default=str)), "what came back"
        assert e["next_stage"] == out.next_stage
        assert "card" in e
    # The card logged with a tool call is the card after it.
    assert tools[0]["card"]["caller"]["name"] == "Farhan Jida"
    assert tools[3]["card"]["choices"]["slot"] == s.card.offered_options[0].start.isoformat()
    assert all("instructions" in e for e in events if e["event"] == "stage")


def test_refused_tool_call_is_logged_too(catalog, directory, tmp_path):
    clinic = make_clinic(catalog, directory, log_dir=tmp_path / "logs")
    s = new_call(clinic)
    step(s, "start_booking", {"full_name": "Farhan Jida", "returning": "no"})
    last = json.loads(lines(s.log_path)[-1])
    assert last["event"] == "tool" and last["result"]["ok"] is False


def test_no_log_when_log_dir_is_none(catalog, directory, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    before = sorted(p.name for p in BACKEND.iterdir())
    clinic = make_clinic(catalog, directory, bookings_file=None, log_dir=None)
    s = new_call(clinic)
    step(s, "start_booking", dict(NEW))
    assert s.log_path is None
    assert list(tmp_path.iterdir()) == []
    assert sorted(p.name for p in BACKEND.iterdir()) == before, "nothing written next to the code"


# ------------------------------------------------------------------ bookings file
def test_no_saving_when_bookings_file_is_none(catalog, directory, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    before = sorted(p.name for p in BACKEND.iterdir())
    clinic = make_clinic(catalog, directory, bookings_file=None, log_dir=None)
    s, o = book(clinic)
    assert s.stage == END and s.card.status == "booked"
    assert list(tmp_path.iterdir()) == []
    assert sorted(p.name for p in BACKEND.iterdir()) == before
    # Still remembered in memory for this run.
    assert not clinic.schedule.is_open(o.provider_id, o.location_id, 45, o.start, NOW)


def test_bookings_append_one_well_formed_line_each(catalog, directory, tmp_path):
    f = tmp_path / "b.jsonl"
    clinic = make_clinic(catalog, directory, bookings_file=f)
    book(clinic, JAMES, KNEE_MRI)
    first = lines(f)
    book(clinic, NEW, SKIN_CHECK)
    now = lines(f)
    assert len(now) == 2 and now[0] == first[0], "appending can't change earlier bookings"
    for line in now:
        d = json.loads(line)
        assert isinstance(d, dict)
        datetime.fromisoformat(d["start"])
    assert f.read_text(encoding="utf-8").endswith("\n")


def test_new_patient_booking_line(catalog, directory, tmp_path):
    f = tmp_path / "b.jsonl"
    clinic = make_clinic(catalog, directory, bookings_file=f)
    _, o = book(clinic, NEW, SKIN_CHECK)
    d = json.loads(lines(f)[0])
    assert d["patient_id"] is None and d["new_patient"] is True and d["caller"] == "Farhan Jida"
    assert (d["provider_id"], d["location_id"], d["start"], d["duration_min"]) == \
           (o.provider_id, o.location_id, o.start.isoformat(), 30)


def test_booked_at_is_clinic_time_from_the_call_clock(catalog, directory, tmp_path):
    # The call's clock is clinic time (INTERFACE: "NOW: a fixed datetime in clinic time").
    # A record that mixes the computer's own clock (Dubai, UTC...) with clinic-time
    # appointment times can't be read correctly later.
    f = tmp_path / "b.jsonl"
    clinic = make_clinic(catalog, directory, bookings_file=f)
    book(clinic)
    d = json.loads(lines(f)[0])
    booked_at = datetime.fromisoformat(d["booked_at"])
    assert booked_at.replace(second=0, microsecond=0) == NOW, d["booked_at"]


def test_reload_round_trip(catalog, directory, tmp_path):
    f = tmp_path / "b.jsonl"
    clinic = make_clinic(catalog, directory, bookings_file=f)
    _, o1 = book(clinic, JAMES, KNEE_MRI)
    _, o2 = book(clinic, NEW, SKIN_CHECK)
    again = Clinic.load(bookings_file=f, log_dir=None)
    assert again.bookings_file == f
    assert not again.schedule.is_open(o1.provider_id, o1.location_id, 45, o1.start, NOW)
    assert not again.schedule.is_open(o2.provider_id, o2.location_id, 30, o2.start, NOW)
    got = read_bookings(f, catalog)
    assert len(got) == 2


def test_missing_bookings_file_means_no_bookings_yet(catalog, tmp_path):
    assert read_bookings(tmp_path / "none.jsonl", catalog) == []
    clinic = Clinic.load(bookings_file=tmp_path / "none.jsonl", log_dir=None)
    assert clinic.schedule.is_open("prov_014", "loc_004", 45, datetime(2026, 10, 7, 9, 30), NOW)


GOOD = {"booked_at": "2026-10-06T09:00:00", "caller": "James Wilson", "patient_id": "pat_001",
        "new_patient": False, "visit_type_id": "appt_065", "visit_type": "MRI - Knee",
        "provider_id": "prov_014", "provider": "Dr. Linda Ramirez", "location_id": "loc_004",
        "location": "Downtown Health Center", "start": "2026-10-07T09:30:00", "duration_min": 45,
        "read_back": "MRI - Knee with Dr. Linda Ramirez ..."}


def _without(key):
    return json.dumps({k: v for k, v in GOOD.items() if k != key})


DAMAGED = {
    "not JSON on line 2": ([json.dumps(GOOD), "{not json"], 2),
    "cut-off line": ([json.dumps(GOOD), json.dumps(GOOD)[:40]], 2),
    "unknown doctor": ([json.dumps({**GOOD, "provider_id": "prov_999"})], 1),
    "start not a date": ([json.dumps(GOOD), json.dumps({**GOOD, "start": "tomorrow"})], 2),
    "no start": ([_without("start")], 1),
    "no doctor": ([json.dumps(GOOD), json.dumps(GOOD), _without("provider_id")], 3),
    "a list, not a booking": (["[1, 2]"], 1),
    "duration not a number": ([json.dumps({**GOOD, "duration_min": "forty-five"})], 1),
}


@pytest.mark.parametrize("label", sorted(DAMAGED))
def test_damaged_bookings_file_is_refused_naming_the_line(catalog, tmp_path, label):
    content, bad_line = DAMAGED[label]
    f = tmp_path / "bookings.jsonl"
    f.write_text("\n".join(content) + "\n", encoding="utf-8")
    with pytest.raises(BookingsFileError) as e:
        read_bookings(f, catalog)
    assert f"line {bad_line}" in str(e.value), str(e.value)
    with pytest.raises(BookingsFileError):
        Clinic.load(bookings_file=f, log_dir=None)


def test_good_bookings_file_with_reloaded_line_is_accepted(catalog, tmp_path):
    f = tmp_path / "bookings.jsonl"
    f.write_text(json.dumps(GOOD) + "\n", encoding="utf-8")
    assert len(read_bookings(f, catalog)) == 1
