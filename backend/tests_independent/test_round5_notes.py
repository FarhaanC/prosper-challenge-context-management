"""Round 5 (spec-changes-round-5.md), sections 1 and 4: the notes about turned-down
doctors, checked across the WHOLE catalog.

- "X is only possible with ..., whom you turned down." names only turned-down doctors who
  really have open times meeting that wish, starts with a capital, uses the day phrase
  without "on" ("Wednesday 7 October", "The morning"), and joins names as "A", "A and B",
  "A, B and C".
- The no_other_doctor note names only the doctors who can do the visit, with "is the only
  option." for one and "are the only options." for several.
- The doctor-wish version ("The only doctor matching 'Dr. Chen' who can do this is ...").

Callers: a new patient, a returning patient with no referrals, and a returning patient
with a referral for every specialty (so every referral-only visit type is covered).
Expected answers come from catalog.json (reference.py) and the spec; the module's fake
calendar is used only as the source of open times.
"""

import re
from collections import Counter
from datetime import timedelta

import pytest

from clinic import Preferences, Schedule, find_options
from conftest import NOW, new_caller, returning
from reference import LOC, PROV, SPECIALTIES, VT, ref_bookable, ref_pairs
from round6_reference import who_can_problems

CALLERS = {"new": (True, []), "returning-none": (False, []), "returning-all": (False, list(SPECIALTIES))}
_SLOTS = {}
ONLY = re.compile(r"^(?P<subject>.+) is only possible with (?P<names>.+), whom you turned down\.$")
NAMES = sorted({x["name"] for x in PROV.values()}, key=len, reverse=True)


def slots(schedule, kind, vt):
    if (kind, vt) not in _SLOTS:
        is_new, _ = CALLERS[kind]
        _SLOTS[(kind, vt)] = [(p, l, t) for p, l in sorted(ref_pairs(is_new, vt))
                              for t in schedule.open_slots(p, l, VT[vt]["duration_min"], NOW)]
    return _SLOTS[(kind, vt)]


def caller(kind):
    is_new, refs = CALLERS[kind]
    return new_caller() if is_new else returning(refs)


def bookable(kind):
    is_new, refs = CALLERS[kind]
    return [vt for vt in VT if ref_bookable(is_new, refs, vt)]


def joined(names):
    """The spec's list form: 'A', 'A and B', 'A, B and C'."""
    names = list(names)
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def names_in(text):
    """Doctor names written in a piece of text (longest first, so no name hides inside another)."""
    found = set()
    for n in NAMES:
        if n in text:
            found.add(n)
            text = text.replace(n, "#")
    return found


def list_problems(names_text, want):
    """Problems with a joined list of names: wrong people, or not written 'A', 'A and B', 'A, B and C'."""
    out = []
    if names_in(names_text) != want:
        out.append(f"names {sorted(names_in(names_text))} != {sorted(want)}")
    parts = re.split(r", | and ", names_text)
    if sorted(parts) != sorted(want) or (len(want) > 1 and not re.fullmatch(r"(.+, )*.+ and .+", names_text)):
        out.append(f"list not written as 'A, B and C': {names_text!r}")
    return out


def down_cases(able):
    """Which doctors to turn down: each one alone, the first two, the first three, all but the last."""
    able = sorted(able)
    cases = [{d} for d in able]
    if len(able) > 2:
        cases += [set(able[:2]), set(able[:3])]
    if len(able) > 1:
        cases.append(set(able[:-1]))
    return cases


def check_only_possible(catalog, schedule, kind, vt, down, prefs, fits, subject):
    """One case: `fits(slot)` says whether a valid open slot meets the wish on its own."""
    all_slots = slots(schedule, kind, vt)
    others = [s for s in all_slots if s[0] not in down]
    if not others:
        return []  # nobody else can do it at all: that's the no_other_doctor case, tested below
    prefs.not_provider_ids = sorted(down)
    r = find_options(catalog, schedule, caller(kind), vt, prefs, NOW)
    where = (kind, VT[vt]["name"], subject, sorted(PROV[d]["name"] for d in down))
    notes = [n for n in r.notes if "turned down" in n.say]
    able_down = {PROV[s[0]]["name"] for s in all_slots if s[0] in down and fits(s)}
    problems = []
    if any(o.provider_id in down for o in r.options):
        problems.append((where, "offered a turned-down doctor"))
    if any(fits(s) for s in others):
        if notes:
            problems.append((where, "turned-down note although others meet the wish", [n.say for n in notes]))
        if any(not fits((o.provider_id, o.location_id, o.start)) for o in r.options):
            problems.append((where, "option ignores a wish that others can meet"))
        return problems
    if not able_down:
        if notes:
            problems.append((where, "turned-down note although no turned-down doctor meets the wish",
                             [n.say for n in notes]))
        return problems
    if len(notes) != 1 or notes[0].kind != "wish_conflict":
        return problems + [(where, "expected one wish_conflict note", [n.say for n in r.notes])]
    m = ONLY.match(notes[0].say)
    if not m:
        return problems + [(where, "wording", notes[0].say)]
    if m.group("subject") != subject:
        problems.append((where, f"subject {m.group('subject')!r} != {subject!r}", notes[0].say))
    if not notes[0].say[0].isupper():
        problems.append((where, "starts with a small letter", notes[0].say))
    problems += [(where, p, notes[0].say) for p in list_problems(m.group("names"), able_down)]
    return problems


def run_wishes(catalog, schedule, kind, wishes):
    """wishes: list of (make_prefs, fits, subject)."""
    problems = []
    for vt in bookable(kind):
        able = {s[0] for s in slots(schedule, kind, vt)}
        for down in down_cases(able):
            for make, fits, subject in wishes:
                problems += check_only_possible(catalog, schedule, kind, vt, down, make(), fits, subject)
    return problems


# ---------------------------------------------------------------- "only possible with ...", every kind of wish
@pytest.mark.parametrize("kind", list(CALLERS))
def test_only_possible_note_for_places_whole_catalog(catalog, schedule, kind):
    wishes = [(lambda n=l["name"]: Preferences(location_hint=n), lambda s, lid=lid: s[1] == lid, l["name"])
              for lid, l in LOC.items()]
    problems = run_wishes(catalog, schedule, kind, wishes)
    assert not problems, (len(problems), problems[:4])


@pytest.mark.parametrize("kind", list(CALLERS))
def test_only_possible_note_for_languages_whole_catalog(catalog, schedule, kind):
    langs = sorted({lang for x in PROV.values() for lang in x["languages"]})
    wishes = [(lambda g=g: Preferences(language=g), lambda s, g=g: g in PROV[s[0]]["languages"], g) for g in langs]
    problems = run_wishes(catalog, schedule, kind, wishes)
    assert not problems, (len(problems), problems[:4])


@pytest.mark.parametrize("kind", list(CALLERS))
def test_only_possible_note_for_every_date_in_the_window_whole_catalog(catalog, schedule, kind):
    days = [(NOW + timedelta(days=k)).date() for k in range(15)]
    wishes = [(lambda d=d: Preferences(days=[d.isoformat()]), lambda s, d=d: s[2].date() == d,
               f"{d:%A} {d.day} {d:%B}") for d in days]
    problems = run_wishes(catalog, schedule, kind, wishes)
    assert not problems, (len(problems), problems[:4])


@pytest.mark.parametrize("kind", list(CALLERS))
def test_only_possible_note_for_weekday_names_whole_catalog(catalog, schedule, kind):
    wishes = [(lambda w=w: Preferences(days=[w]), lambda s, w=w: s[2].strftime("%A") == w, w)
              for w in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]]
    problems = run_wishes(catalog, schedule, kind, wishes)
    assert not problems, (len(problems), problems[:4])


@pytest.mark.parametrize("kind", list(CALLERS))
def test_only_possible_note_for_morning_and_afternoon_whole_catalog(catalog, schedule, kind):
    wishes = [(lambda: Preferences(time_of_day="morning"), lambda s: s[2].hour < 12, "The morning"),
              (lambda: Preferences(time_of_day="afternoon"), lambda s: s[2].hour >= 12, "The afternoon")]
    problems = run_wishes(catalog, schedule, kind, wishes)
    assert not problems, (len(problems), problems[:4])


# ---------------------------------------------------------------- the doctor-wish version
SURNAMES = Counter(x["name"].split()[-1] for x in PROV.values())


@pytest.mark.parametrize("kind", list(CALLERS))
def test_only_doctor_matching_note_whole_catalog(catalog, schedule, kind):
    """A surname shared by several doctors, every doctor with it who can do the visit turned
    down: the note names exactly those doctors, in the right grammar for one or several."""
    problems, tried = [], 0
    for vt in bookable(kind):
        able = {s[0] for s in slots(schedule, kind, vt)}
        for surname, count in SURNAMES.items():
            if count < 2:
                continue
            with_name = sorted(p for p in able if PROV[p]["name"].split()[-1] == surname)
            if not with_name or not able - set(with_name):
                continue
            tried += 1
            r = find_options(catalog, schedule, caller(kind), vt,
                             Preferences(doctor_name_heard=f"Dr. {surname}", not_provider_ids=with_name), NOW)
            where = (kind, VT[vt]["name"], surname)
            want = {PROV[p]["name"] for p in with_name}
            notes = [n for n in r.notes if "turned down" in n.say]
            if any(o.provider_id in with_name for o in r.options):
                problems.append((where, "offered a turned-down doctor"))
            if len(notes) != 1 or notes[0].kind != "wish_conflict":
                problems.append((where, "expected one wish_conflict note", [n.say for n in r.notes]))
                continue
            say = notes[0].say
            one = (f"The only doctor matching 'Dr. {surname}' who can do this is {joined(sorted(want))}, whom you "
                   "turned down. Check whether the caller wants that doctor after all.")
            if len(want) == 1:
                if say != one:
                    problems.append((where, "wording", say))
                continue
            if names_in(say) != want:
                problems.append((where, "names", sorted(want), say))
            if re.search(r"The only doctor matching .* is [^,]+ and ", say) or "doctor matching" in say:
                problems.append((where, "singular grammar for several doctors", say))
    assert tried
    assert not problems, (len(problems), problems[:3])


# ---------------------------------------------------------------- no_other_doctor, whole catalog
NO_OTHER = re.compile(r"^No other doctor can do (?P<vt>.+) for you; (?P<names>.+?) "
                      r"(?P<verb>is the only option|are the only options)\.$")


@pytest.mark.parametrize("kind", list(CALLERS))
def test_no_other_doctor_note_whole_catalog(catalog, schedule, kind):
    problems = []
    for vt in bookable(kind):
        able = sorted({s[0] for s in slots(schedule, kind, vt)})
        if not able:
            continue
        offering = sorted(p for p, x in PROV.items() if vt in x["appointment_type_ids"])
        for label, down in [("everyone who can", able), ("plus unrelated doctors", sorted(PROV)),
                            ("every doctor offering it", offering)]:
            r = find_options(catalog, schedule, caller(kind), vt, Preferences(not_provider_ids=down), NOW)
            where = (kind, VT[vt]["name"], label)
            nod = [n.say for n in r.notes if n.kind == "no_other_doctor"]
            if len(nod) != 1 or not r.options:
                problems.append((where, "expected one no_other_doctor note and options", [n.say for n in r.notes]))
                continue
            m = NO_OTHER.match(nod[0])
            if not m or m.group("vt") != VT[vt]["name"]:
                problems.append((where, "wording", nod[0]))
                continue
            problems += [(where, p, nod[0]) for p in who_can_problems(m.group("names"), able)]
            if (m.group("verb") == "is the only option") != (len(able) == 1):
                problems.append((where, "singular/plural", nod[0]))
            if not {o.provider_id for o in r.options} <= set(able):
                problems.append((where, "offered someone who can't"))
        if len(able) > 1:  # all but one turned down: no note, only the one left
            r = find_options(catalog, schedule, caller(kind), vt, Preferences(not_provider_ids=able[:-1]), NOW)
            if [n for n in r.notes if n.kind == "no_other_doctor"] or \
                    {o.provider_id for o in r.options} != {able[-1]}:
                problems.append(((kind, VT[vt]["name"], "all but one"), [n.say for n in r.notes]))
    assert not problems, (len(problems), problems[:4])


# ---------------------------------------------------------------- nothing open at all
def _fully_booked(catalog, vt):
    s = Schedule(catalog)
    minutes = VT[vt]["duration_min"]
    for p in catalog.providers_offering(vt):
        for lid in p.location_ids:
            for t in s.open_slots(p.id, lid, minutes, NOW):
                s.book(p.id, t, minutes)
    return s


@pytest.mark.parametrize("down", [["prov_001"], ["prov_049"], sorted(PROV)])
def test_a_fully_booked_fortnight_with_a_turned_down_doctor_does_not_crash(catalog, down):
    vt = "appt_027"
    s = _fully_booked(catalog, vt)
    r = find_options(catalog, s, new_caller(), vt, Preferences(not_provider_ids=down), NOW)
    assert not r.options and [n.kind for n in r.notes] == ["no_times"], [n.say for n in r.notes]


def test_a_fully_booked_fortnight_gives_no_empty_sentences(catalog):
    vt = "appt_027"
    s = _fully_booked(catalog, vt)
    r = find_options(catalog, s, new_caller(), vt, Preferences(doctor_name_heard="Dr. Garcia"), NOW)
    assert not r.options and "no_times" in [n.kind for n in r.notes]
    assert not [n.say for n in r.notes if re.search(r":\s*\.", n.say)], [n.say for n in r.notes]
