"""Round 2, spec changes 4 (doctor names) and 5 (day and time values), 6 (note kinds)."""

from datetime import timedelta

import pytest

from clinic import Note, OptionsResult, Preferences, find_options
from conftest import NOW, new_caller, returning
from reference import PROV, SPECIALTIES, VT, first_name, last_name, ref_bookable

GARCIAS = {pid for pid, p in PROV.items() if last_name(p["name"]) == "Garcia"}
CHENS = {pid for pid, p in PROV.items() if last_name(p["name"]) == "Chen"}
NOTE_KINDS = {"not_bookable", "bad_input", "doctor_not_found", "doctor_name_guess", "doctors_same_name",
              "place_unknown", "place_ambiguous", "wish_impossible", "wish_conflict", "no_times"}


def ids(matches):
    return {m.provider.id for m in matches}


# ---------------------------------------------------------------- doctor names
def test_grace_is_grace_rodriguez(catalog):
    m = catalog.match_providers("Dr. Grace")
    assert [PROV[x.provider.id]["name"] for x in m] == ["Dr. Grace Rodriguez"]
    assert m[0].describe() == "exact" and m[0].is_exact and m[0].first_name_matched


def test_garsha_is_the_three_garcias_sounds_alike(catalog):
    m = catalog.match_providers("Dr. Garsha")
    assert ids(m) == GARCIAS
    assert all(x.describe() == "sounds alike" and not x.is_exact for x in m)
    assert {p.id for p in catalog.find_providers_by_name("Dr. Garsha")} == GARCIAS


@pytest.mark.parametrize("heard", ["Dr. Garcia's", "Garcia's", "Dr. Garcia’s", "dr. garcia's"])
def test_possessive_ignored(catalog, heard):
    m = catalog.match_providers(heard)
    assert ids(m) == GARCIAS and all(x.describe() == "exact" for x in m), heard


def test_wrong_first_name_falls_back_to_surname(catalog):
    m = catalog.match_providers("Dr. John Garcia")
    assert ids(m) == GARCIAS and all(not x.first_name_matched and not x.is_exact for x in m)


def test_right_first_name_wins_over_surname_only(catalog):
    m = catalog.match_providers("Dr. Carlos Garcia")
    assert ids(m) == {"prov_008"} and m[0].is_exact


@pytest.mark.parametrize("heard,quality", [("Dr. Ramires", "close spelling"), ("Dr. Smyth", "close spelling"),
                                           ("Dr. Chen", "exact"), ("Dr. Chan", "sounds alike")])
def test_quality_labels(catalog, heard, quality):
    m = catalog.match_providers(heard)
    assert m and {x.describe() for x in m} == {quality}, (heard, [(x.provider.name, x.describe()) for x in m])


def test_every_full_name_is_exact_and_returns_all_namesakes(catalog):
    for p in PROV.values():
        m = catalog.match_providers(p["name"])
        same = {pid for pid, q in PROV.items() if q["name"] == p["name"]}
        assert ids(m) == same and all(x.is_exact for x in m), p["name"]


def test_every_surname_alone_returns_all_holders(catalog):
    for sur in {last_name(p["name"]) for p in PROV.values()}:
        m = catalog.match_providers(f"Dr. {sur}")
        assert ids(m) == {pid for pid, p in PROV.items() if last_name(p["name"]) == sur}, sur


def test_every_first_name_alone_returns_all_holders(catalog):
    surnames = {last_name(p["name"]).lower() for p in PROV.values()}
    for fn in {first_name(p["name"]) for p in PROV.values()}:
        if fn.lower() in surnames:
            continue
        m = catalog.match_providers(f"Dr. {fn}")
        assert ids(m) == {pid for pid, p in PROV.items() if first_name(p["name"]) == fn}, fn


def test_find_options_flags_name_guess(catalog, schedule):
    for heard in ["Dr. Garsha", "Dr. John Garcia", "Dr. Ramires"]:
        r = find_options(catalog, schedule, returning(list(SPECIALTIES)), "appt_002",
                         Preferences(doctor_name_heard=heard), NOW)
        assert "doctor_name_guess" in [n.kind for n in r.notes], (heard, [(n.kind, str(n)) for n in r.notes])


def test_exact_name_has_no_guess_note(catalog, schedule):
    r = find_options(catalog, schedule, returning(list(SPECIALTIES)), "appt_002",
                     Preferences(doctor_name_heard="Dr. Carlos Garcia"), NOW)
    assert "doctor_name_guess" not in [n.kind for n in r.notes]


def test_unknown_doctor_note(catalog, schedule):
    r = find_options(catalog, schedule, new_caller(), "appt_027", Preferences(doctor_name_heard="Dr. Zzyzx"), NOW)
    assert [n.kind for n in r.notes] == ["doctor_not_found"] and r.options


def test_same_name_note_for_two_maria_garcias(catalog, schedule):
    # Annual Physical: both Maria Garcias offer it (catalog.json) and accept new patients
    r = find_options(catalog, schedule, new_caller(), "appt_002", Preferences(doctor_name_heard="Dr. Maria Garcia"), NOW)
    same = [n for n in r.notes if n.kind == "doctors_same_name"]
    assert same and "Pediatrics" in same[0] and "Family Medicine" in same[0]


# ---------------------------------------------------------------- day and time values
GOOD_DAYS = ["Thursday", "thu", "thurs", "THURSDAY", "Thu", "today", "Today", "TOMORROW", "tomorrow",
             (NOW + timedelta(days=3)).date().isoformat(), "", "   ", "any", "ANY", "Any"]
BAD_DAYS = ["next Thursday", "Oct 13", "13/10/2026", "2026/10/13", "the 13th", "this week", "Th", "weekend"]


@pytest.mark.parametrize("day", GOOD_DAYS)
def test_accepted_days(catalog, schedule, day):
    r = find_options(catalog, schedule, returning(list(SPECIALTIES)), "appt_002", Preferences(days=[day]), NOW)
    assert "bad_input" not in [n.kind for n in r.notes] and r.options, (day, [str(n) for n in r.notes])


@pytest.mark.parametrize("day", BAD_DAYS)
def test_rejected_days(catalog, schedule, day):
    r = find_options(catalog, schedule, returning(list(SPECIALTIES)), "appt_002", Preferences(days=[day]), NOW)
    assert r.options == [] and [n.kind for n in r.notes] == ["bad_input"], (day, [str(n) for n in r.notes])


@pytest.mark.parametrize("tod", ["morning", "Morning", "AFTERNOON", "afternoon ", "", "any", "Any"])
def test_accepted_times(catalog, schedule, tod):
    r = find_options(catalog, schedule, returning(list(SPECIALTIES)), "appt_002", Preferences(time_of_day=tod), NOW)
    assert "bad_input" not in [n.kind for n in r.notes] and r.options
    t = tod.strip().lower()
    if t == "morning":
        assert all(o.start.hour < 12 for o in r.options)
    if t == "afternoon":
        assert all(o.start.hour >= 12 for o in r.options)


@pytest.mark.parametrize("tod", ["evening", "lunchtime", "noon", "early", "after 3", "am"])
def test_rejected_times(catalog, schedule, tod):
    r = find_options(catalog, schedule, returning(list(SPECIALTIES)), "appt_002", Preferences(time_of_day=tod), NOW)
    assert r.options == [] and [n.kind for n in r.notes] == ["bad_input"]
    assert "morning" in r.notes[0] and "afternoon" in r.notes[0]


def test_one_bad_day_among_good_ones_is_still_bad_input(catalog, schedule):
    r = find_options(catalog, schedule, returning(list(SPECIALTIES)), "appt_002",
                     Preferences(days=["Thursday", "next Friday"]), NOW)
    assert r.options == [] and {n.kind for n in r.notes} == {"bad_input"}


def test_weekend_day_is_impossible_not_bad_input(catalog, schedule):
    r = find_options(catalog, schedule, returning(list(SPECIALTIES)), "appt_002", Preferences(days=["Saturday"]), NOW)
    assert [n.kind for n in r.notes] == ["wish_impossible"] and r.options


def test_date_outside_window_is_impossible(catalog, schedule):
    far = (NOW + timedelta(days=15)).date().isoformat()
    r = find_options(catalog, schedule, returning(list(SPECIALTIES)), "appt_002", Preferences(days=[far]), NOW)
    assert [n.kind for n in r.notes] == ["wish_impossible"] and r.options


def test_window_is_today_plus_14_days(catalog, schedule):
    last = NOW.date() + timedelta(days=14)
    seen = set()
    for pid in PROV:
        for lid in PROV[pid]["location_ids"]:
            for s in schedule.open_slots(pid, lid, 30, NOW):
                seen.add(s.date())
    assert max(seen) == last and min(seen) >= NOW.date()


# ---------------------------------------------------------------- note kinds and shapes
def test_notes_are_strings_with_kinds_everywhere(catalog, schedule):
    combos = [Preferences(doctor_name_heard="Dr. Garsha", location_hint="the Mission", days=["Saturday"],
                          language="Klingon"),
              Preferences(location_hint="Mars", time_of_day="evening"),
              Preferences(doctor_name_heard="Dr. Zzyzx", location_hint="the one on Geary")]
    for kind_caller in [new_caller(), returning(list(SPECIALTIES))]:
        for vt in list(VT)[:40]:
            for p in combos:
                r = find_options(catalog, schedule, kind_caller, vt, p, NOW)
                d = r.to_dict()
                assert set(d) >= {"bookable", "notes", "options"}
                for n, nd in zip(r.notes, d["notes"]):
                    assert isinstance(n, str) and n.kind in NOTE_KINDS
                    assert nd == {"kind": n.kind, "say": str(n)}
                    assert " ".join(r.notes)  # can be joined
                for o in d["options"]:
                    assert set(o) >= {"option_id", "provider_id", "location_id", "start", "spoken"}


def test_not_bookable_kind(catalog, schedule):
    r = find_options(catalog, schedule, new_caller(), "appt_065", Preferences(), NOW)  # knee MRI, new patient
    assert not r.bookable and r.notes and {n.kind for n in r.notes} == {"not_bookable"}


@pytest.mark.parametrize("bad", ["appt_999", "", None, "MRI - Knee", 65, ["appt_065"]])
def test_unknown_visit_type_refused_politely(catalog, schedule, bad):
    from clinic import can_book_visit_type, check_booking
    r = find_options(catalog, schedule, new_caller(), bad, Preferences(), NOW)
    assert not r.bookable and r.notes and r.notes[0].kind == "not_bookable"
    assert not can_book_visit_type(catalog, new_caller(), bad).bookable
    assert check_booking(catalog, schedule, new_caller(), bad, "prov_001", "loc_004", NOW, NOW)


def test_language_note_grammar(catalog, schedule):
    """'A Arabic-speaking doctor isn't available...' is what the agent would read aloud."""
    r = find_options(catalog, schedule, returning(list(SPECIALTIES)), "appt_027",
                     Preferences(doctor_name_heard="Dr. Kenji Kim", language="Arabic"), NOW)
    for n in r.notes:
        assert "A Arabic" not in n, str(n)
