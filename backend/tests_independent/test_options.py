"""find_options: up to 3 valid options, spread across pairs, honest notes."""

import json
import math
from datetime import timedelta

import pytest

from clinic import Preferences, check_booking, find_options
from conftest import NOW, new_caller, returning
from reference import DATA, PROV, SPECIALTIES, VT, ref_bookable, ref_pairs

EXTRAS = json.loads((DATA / "location_extras.json").read_text())
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]

CALLERS = {
    "new": (True, []),
    "returning-none": (False, []),
    "returning-all": (False, list(SPECIALTIES)),
}


def mk(kind):
    is_new, refs = CALLERS[kind]
    return new_caller() if is_new else returning(refs)


def run(catalog, schedule, caller, vt, **prefs):
    return find_options(catalog, schedule, caller, vt, Preferences(**prefs), NOW)


def ref_slots(schedule, is_new, vt):
    """All valid (pid, lid, start) for this caller, using the module's fake calendar
    only as the source of open times (its rules are checked separately)."""
    out = []
    for pid, lid in ref_pairs(is_new, vt):
        for s in schedule.open_slots(pid, lid, VT[vt]["duration_min"], NOW):
            out.append((pid, lid, s))
    return out


def miles(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 3958.8 * 2 * math.asin(math.sqrt(h))


def loc_pt(lid):
    x = EXTRAS["locations"][lid]
    return (x["lat"], x["lon"])


# ---------------------------------------------------------------- whole-catalog properties
@pytest.mark.parametrize("kind", list(CALLERS))
def test_no_wishes_every_visit_type(catalog, schedule, kind):
    is_new, refs = CALLERS[kind]
    caller = mk(kind)
    problems = []
    for vt in VT:
        r = run(catalog, schedule, caller, vt)
        if not ref_bookable(is_new, refs, vt):
            if r.bookable or r.options or not r.notes:
                problems.append((vt, "should be refused with a note"))
            continue
        slots = ref_slots(schedule, is_new, vt)
        if not r.bookable:
            problems.append((vt, "wrongly refused", r.notes))
            continue
        if len(r.options) > 3:
            problems.append((vt, "more than 3"))
        if slots and not r.options:
            problems.append((vt, "no options although slots exist"))
        for o in r.options:
            if (o.provider_id, o.location_id) not in ref_pairs(is_new, vt):
                problems.append((vt, "invalid pair", o.provider_id, o.location_id))
            if check_booking(catalog, schedule, caller, vt, o.provider_id, o.location_id, o.start, NOW):
                problems.append((vt, "option fails final check", o.spoken))
        pairs_with_slots = {(p, l) for p, l, _ in slots}
        distinct = {(o.provider_id, o.location_id) for o in r.options}
        if len(distinct) != min(3, len(pairs_with_slots)):
            problems.append((vt, "not spread", len(distinct), len(pairs_with_slots)))
        if slots and r.options and min(o.start for o in r.options) != min(s for _, _, s in slots):
            problems.append((vt, "soonest time not offered"))
        if len({o.option_id for o in r.options}) != len(r.options):
            problems.append((vt, "duplicate option ids"))
        if len({(o.provider_id, o.location_id, o.start) for o in r.options}) != len(r.options):
            problems.append((vt, "same option twice"))
    assert not problems, problems[:10]


@pytest.mark.parametrize("day", WEEKDAYS + ["today", "tomorrow", "2026-10-13", "thursday", "THU"])
def test_day_wish_whole_catalog(catalog, schedule, day):
    caller = mk("returning-all")
    problems = []
    for vt in VT:
        if not ref_bookable(False, list(SPECIALTIES), vt):
            continue
        r = run(catalog, schedule, caller, vt, days=[day])
        slots = ref_slots(schedule, False, vt)

        def ok(s):
            d = day.lower()
            if d == "today":
                return s.date() == NOW.date()
            if d == "tomorrow":
                return s.date() == (NOW + timedelta(days=1)).date()
            if d[0].isdigit():
                return s.date().isoformat() == d
            return s.strftime("%A").lower().startswith(d[:3])
        matching = [x for x in slots if ok(x[2])]
        if matching:
            bad = [o.spoken for o in r.options if not ok(o.start)]
            if bad or not r.options:
                problems.append((vt, "day wish not honoured", bad))
        else:
            if not any("nothing is open" in n.say.lower() or day.lower() in n.say.lower() for n in r.notes):
                problems.append((vt, "no note for unmet day wish"))
    assert not problems, problems[:10]


@pytest.mark.parametrize("tod", ["morning", "afternoon"])
def test_time_of_day_whole_catalog(catalog, schedule, tod):
    caller = mk("returning-all")
    problems = []
    for vt in VT:
        if not ref_bookable(False, list(SPECIALTIES), vt):
            continue
        r = run(catalog, schedule, caller, vt, time_of_day=tod)
        ok = (lambda s: s.hour < 12) if tod == "morning" else (lambda s: s.hour >= 12)
        if any(ok(s) for _, _, s in ref_slots(schedule, False, vt)):
            if not r.options or any(not ok(o.start) for o in r.options):
                problems.append(vt)
    assert not problems


@pytest.mark.parametrize("lang", ["Spanish", "spanish", "Arabic", "Vietnamese", "Mandarin", "Hindi", "Portuguese"])
def test_language_wish_whole_catalog(catalog, schedule, lang):
    caller = mk("returning-all")
    problems = []
    for vt in VT:
        if not ref_bookable(False, list(SPECIALTIES), vt):
            continue
        r = run(catalog, schedule, caller, vt, language=lang)
        slots = ref_slots(schedule, False, vt)
        speakers = [x for x in slots if lang.lower() in [l.lower() for l in PROV[x[0]]["languages"]]]
        if speakers:
            if not r.options or any(lang.lower() not in [l.lower() for l in PROV[o.provider_id]["languages"]]
                                    for o in r.options):
                problems.append((vt, "language not honoured"))
        elif slots:
            if not any(lang.lower() in n.say.lower() for n in r.notes):
                problems.append((vt, "no note for unmet language"))
            if not r.options:
                problems.append((vt, "language wish wiped out all options"))
    assert not problems, problems[:10]


def test_preferred_doctor_whole_catalog(catalog, schedule):
    """For each visit type and each doctor who can do it: options are only with that doctor."""
    caller = mk("returning-all")
    problems = []
    for vt in VT:
        if not ref_bookable(False, list(SPECIALTIES), vt):
            continue
        slots = ref_slots(schedule, False, vt)
        for pid in {p for p, _, _ in slots}:
            r = run(catalog, schedule, caller, vt, preferred_provider_id=pid)
            if not r.options or any(o.provider_id != pid for o in r.options):
                problems.append((vt, pid))
    assert not problems, problems[:10]


# ---------------------------------------------------------------- honest notes when wishes conflict
def test_nothing_open_note_is_true_when_doctor_wish_also_set(catalog, schedule):
    """A note saying 'Nothing is open for <day>' must be true. If another valid doctor
    has that day free, saying nothing is open misleads the caller."""
    caller = mk("returning-all")
    false_claims = []
    for vt in VT:
        if not ref_bookable(False, list(SPECIALTIES), vt):
            continue
        slots = ref_slots(schedule, False, vt)
        for pid in {p for p, _, _ in slots}:
            for day in WEEKDAYS:
                r = run(catalog, schedule, caller, vt, preferred_provider_id=pid, days=[day])
                if any(n.say.lower().startswith("nothing is open") for n in r.notes):
                    others = [x for x in slots if x[2].strftime("%A") == day]
                    if others:
                        false_claims.append((VT[vt]["name"], PROV[pid]["name"], day, r.notes))
    assert not false_claims, (len(false_claims), false_claims[:3])


def test_language_note_is_true_when_doctor_wish_also_set(catalog, schedule):
    # Skin Cancer Screening; Dr. Daniel Chen speaks English + Arabic. Other valid doctors with
    # open times speak Spanish (checked from catalog.json below). The said doctor is stronger
    # than the language (spec r2 s1), so the language is set aside as a CLASH, not "impossible".
    # Round 3: rewritten to check behaviour instead of searching for an old sentence.
    slots = ref_slots(schedule, True, "appt_027")
    spanish = {p for p, _, _ in slots if "Spanish" in PROV[p]["languages"]}
    assert spanish and "prov_001" not in spanish
    r = run(catalog, schedule, new_caller(), "appt_027", doctor_name_heard="Dr. Daniel Chen", language="Spanish")
    assert r.options and all(o.provider_id == "prov_001" for o in r.options)
    kinds = [n.kind for n in r.notes]
    assert "wish_impossible" not in kinds, [str(n) for n in r.notes]
    clash = [n.say for n in r.notes if n.kind == "wish_conflict"]
    assert clash == ["No Spanish-speaking doctor is available with Dr. Daniel Chen."], clash


def test_named_place_note_is_true_when_doctor_wish_also_set(catalog, schedule):
    # Dr. Daniel Chen (Downtown, Richmond) + "the Midtown one": another valid doctor does skin
    # screening at Midtown, so the place is set aside as a CLASH with the stronger said doctor.
    # Round 3: rewritten to check behaviour instead of searching for an old sentence.
    slots = ref_slots(schedule, True, "appt_027")
    assert any(l == "loc_005" for _, l, _ in slots) and "loc_005" not in PROV["prov_001"]["location_ids"]
    r = run(catalog, schedule, new_caller(), "appt_027", doctor_name_heard="Dr. Daniel Chen",
            location_hint="the Midtown one")
    assert r.options and all(o.provider_id == "prov_001" for o in r.options)
    assert "wish_impossible" not in [n.kind for n in r.notes], [str(n) for n in r.notes]
    clash = [n.say for n in r.notes if n.kind == "wish_conflict"]
    assert clash == ["Midtown Medical Group isn't available with Dr. Daniel Chen."], clash


# ---------------------------------------------------------------- baseline-call cases
def test_skin_check_with_dr_garcia(catalog, schedule):
    r = run(catalog, schedule, new_caller(), "appt_027", doctor_name_heard="Dr. Garcia")
    assert r.bookable and r.options
    assert all(PROV[o.provider_id]["specialty"] == "Dermatology" for o in r.options)
    assert not any("Garcia" in o.provider_name for o in r.options)
    text = " ".join(n.say for n in r.notes)
    assert "Garcia" in text
    # dermatologists open to a new patient
    for name in ["Daniel Chen", "Kenji Kim", "Daniel Smith"]:
        assert name in text
    assert "Wei Sato" not in text  # not taking new patients


def test_skin_check_with_dr_garsha_misheard(catalog, schedule):
    r = run(catalog, schedule, new_caller(), "appt_028", doctor_name_heard="Dr. Garsha")
    assert r.options and all(PROV[o.provider_id]["specialty"] == "Dermatology" for o in r.options)
    assert any("Garsha" in n.say or "Garcia" in n.say for n in r.notes)


def test_two_maria_garcias_note(catalog, schedule):
    # Annual Physical is offered by both Maria Garcias (Pediatrics at Mission Bay, Family Medicine at 3 sites)
    r = run(catalog, schedule, new_caller(), "appt_002", doctor_name_heard="Dr. Maria Garcia")
    text = " ".join(n.say for n in r.notes)
    assert "2" in text and "Pediatrics" in text and "Family Medicine" in text
    assert "Mission Bay Health Center" in text
    assert {o.provider_id for o in r.options} <= {"prov_002", "prov_003"}


def test_doctor_name_not_found(catalog, schedule):
    r = run(catalog, schedule, new_caller(), "appt_027", doctor_name_heard="Dr. Zhivago")
    assert r.options and any("Zhivago" in n.say for n in r.notes)


def test_knee_mri_returning_with_referral(catalog, schedule, directory):
    james = directory.lookup("James Wilson", "1984-03-12").caller
    r = run(catalog, schedule, james, "appt_065")
    assert {(o.provider_id, o.location_id) for o in r.options} == {("prov_014", "loc_004"), ("prov_015", "loc_005")}
    assert len(r.options) == 3


def test_knee_mri_new_patient(catalog, schedule):
    r = run(catalog, schedule, new_caller(), "appt_065")
    assert not r.bookable and not r.options and r.notes


def test_knee_mri_with_old_garcia_wish(catalog, schedule, directory):
    james = directory.lookup("James Wilson", "1984-03-12").caller
    r = run(catalog, schedule, james, "appt_065", doctor_name_heard="Dr. Garcia")
    assert r.options and all(o.provider_id in ("prov_014", "prov_015") for o in r.options)
    assert any("Garcia" in n.say for n in r.notes)


def test_knee_mri_near_downtown(catalog, schedule, directory):
    james = directory.lookup("James Wilson", "1984-03-12").caller
    r = run(catalog, schedule, james, "appt_065", location_hint="near Downtown")
    assert r.options[0].location_id == "loc_004"
    assert {o.location_id for o in r.options} == {"loc_004", "loc_005"}  # near ranks, does not exclude
    assert not any("recognise" in n.say for n in r.notes)


def test_knee_mri_closer_to_downtown_baseline_phrase(catalog, schedule, directory):
    james = directory.lookup("James Wilson", "1984-03-12").caller
    r = run(catalog, schedule, james, "appt_065", location_hint="closer to downtown")
    assert r.options[0].location_id == "loc_004"
    assert not any("recognise" in n.say for n in r.notes), r.notes


def test_knee_mri_the_midtown_one(catalog, schedule, directory):
    james = directory.lookup("James Wilson", "1984-03-12").caller
    r = run(catalog, schedule, james, "appt_065", location_hint="the Midtown one")
    assert r.options and all((o.provider_id, o.location_id) == ("prov_015", "loc_005") for o in r.options)


def test_knee_mri_the_sunset_one_not_possible(catalog, schedule, directory):
    james = directory.lookup("James Wilson", "1984-03-12").caller
    r = run(catalog, schedule, james, "appt_065", location_hint="the Sunset one")
    assert r.options  # closest alternatives
    assert any("Sunset" in n.say for n in r.notes)


def test_ambiguous_place_note(catalog, schedule):
    r = run(catalog, schedule, new_caller(), "appt_027", location_hint="the Mission one")
    text = " ".join(n.say for n in r.notes)
    assert "Mission Bay" in text and "Mission District" in text


def test_unknown_place_note(catalog, schedule):
    r = run(catalog, schedule, new_caller(), "appt_027", location_hint="Narnia")
    assert r.options and any("Narnia" in n.say for n in r.notes)


def test_blank_place_hint_is_no_wish(catalog, schedule):
    r = run(catalog, schedule, new_caller(), "appt_027", location_hint="   ")
    assert not r.notes, r.notes


def test_near_landmark_ranks_by_distance(catalog, schedule):
    caller = new_caller()
    r = run(catalog, schedule, caller, "appt_027", location_hint="near Chinatown")
    pt = tuple(EXTRAS["landmarks"]["Chinatown"])
    d = [miles(pt, loc_pt(o.location_id)) for o in r.options]
    assert d == sorted(d)
    slots = ref_slots(schedule, True, "appt_027")
    closest = min(miles(pt, loc_pt(l)) for _, l, _ in slots)
    assert abs(d[0] - closest) < 0.05


def test_unmet_language_keeps_options(catalog, schedule):
    r = run(catalog, schedule, new_caller(), "appt_027", language="Klingon")
    assert r.options and any("Klingon" in n.say for n in r.notes)


def test_saturday_wish_noted_and_alternatives(catalog, schedule):
    r = run(catalog, schedule, new_caller(), "appt_027", days=["Saturday"])
    assert r.options and r.notes


def test_day_and_time_together(catalog, schedule):
    r = run(catalog, schedule, returning(list(SPECIALTIES)), "appt_002", days=["Thursday"], time_of_day="afternoon")
    for o in r.options:
        assert o.start.strftime("%A") == "Thursday" and o.start.hour >= 12


def test_limit(catalog, schedule):
    r = find_options(catalog, schedule, new_caller(), "appt_002", Preferences(), NOW, limit=1)
    assert len(r.options) == 1


def test_options_disappear_after_booking(catalog, directory):
    from clinic import Schedule
    sch = Schedule(catalog)
    james = directory.lookup("James Wilson", "1984-03-12").caller
    first = run(catalog, sch, james, "appt_065").options[0]
    sch.book(first.provider_id, first.start, 45)
    again = run(catalog, sch, james, "appt_065").options
    assert all(not (o.provider_id == first.provider_id and o.start == first.start) for o in again)


def test_spoken_option_names_doctor_place_time(catalog, schedule):
    from clinic import spoken_time
    for o in run(catalog, schedule, new_caller(), "appt_027").options:
        assert o.provider_name in o.spoken and o.location_name in o.spoken and spoken_time(o.start) in o.spoken


def test_alternatives_list_does_not_repeat_a_name_unexplained(catalog, schedule):
    """'... who can: Dr. Maria Garcia, Dr. Maria Garcia, ...' read aloud is confusing.
    Duplicate names in a spoken list should be told apart (specialty or place) or merged."""
    r = run(catalog, schedule, new_caller(), "appt_002", doctor_name_heard="Dr. Linda Ramirez")
    note = next(n.say for n in r.notes if "who can" in n.say)
    listed = note.split("who can:")[1]
    names = [x.strip(" .") for x in listed.replace(" and ", ",").split(",") if x.strip().startswith("Dr.")]
    assert len(names) == len(set(names)), note
