"""Round 6 (spec-changes-round-6.md), section 5: notes, checked across the WHOLE catalog.

- "No other doctor": reuses the "Doctors who can" list (three names with specialty, then
  "and N more"; same-name doctors get their locations), "is the only option." / "are the
  only options.", only when someone has open times, never a crash.
- The plural "The only doctors matching 'Dr. X' who can do this are A and B, whom you
  turned down. Check whether the caller wants one of them after all."
- A language not in our records: "None of our doctors is listed as speaking X. Our doctors
  speak ...", kind wish_impossible, options still offered, the caller's capitals kept.
- A doctor wish nobody can meet, with nothing open: no empty "Doctors who can" sentence.
- No empty or broken sentence anywhere.

Callers: a new patient, a returning patient with no referrals, and one with a referral for
every specialty. Expected answers come from catalog.json (reference.py) and the spec; the
module's fake calendar is used only as the source of open times.
"""

import copy
import json
import re

import pytest

from clinic import Catalog, Preferences, Schedule, SlotTaken, find_options
from conftest import NOW, new_caller, returning
from reference import DATA, PROV, SPECIALTIES, VT, ref_bookable, ref_pairs
from round6_reference import capped_names_problems, who_can_problems

RAW = json.loads((DATA / "catalog.json").read_text())
EXTRAS = json.loads((DATA / "location_extras.json").read_text())
CALLERS = {"new": (True, []), "returning-none": (False, []), "returning-all": (False, list(SPECIALTIES))}
LANGS = sorted({l for x in PROV.values() for l in x["languages"]})
OUR_LANGS = ", ".join(LANGS[:-1]) + " and " + LANGS[-1]
_SLOTS = {}


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


def key(r):
    return [(o.provider_id, o.location_id, o.start) for o in r.options]


# ---------------------------------------------------------------- sentence quality
def sentence_problems(say):
    """Things no sentence the agent reads out should contain."""
    checks = [("double space", "  " in say), ("space before a full stop", " ." in say or " ," in say),
              ("empty list", bool(re.search(r":\s*[.;]|\(\s*\)|''|, ,|,\s*\.|\band and\b", say))),
              ("leftover placeholder", bool(re.search(r"[{}]|(?<!^)\bNone\b|\[|\]", say))),
              ("doesn't start with a capital", not re.match(r"[A-Z'\"0-9]", say)),
              ("doesn't end a sentence", not re.search(r"[.?!]$", say)),
              ("ends a list with 'and'", bool(re.search(r"\band$|\band\.$", say)))]
    return [name for name, bad in checks if bad]


BATTERY = [
    Preferences(), Preferences(doctor_name_heard="Dr. Chen"), Preferences(doctor_name_heard="Dr. Garsha"),
    Preferences(doctor_name_heard="Dr. John Garcia"), Preferences(doctor_name_heard="Dr. Linda Nguyen"),
    Preferences(doctor_name_heard="Dr. Zzyzx"), Preferences(location_hint="Mission"),
    Preferences(location_hint="Geary Street", near=True), Preferences(location_hint="Mars"),   # round 7: name + near
    Preferences(location_hint="Midtown"), Preferences(days=["Saturday"]), Preferences(days=["2026-10-10"]),
    Preferences(location_hint="Downtown", near=True), Preferences(location_hint="the Midtown one"),
    Preferences(days=["today"], time_of_day="afternoon"), Preferences(language="Hindi"),
    Preferences(language="Klingon"), Preferences(language="Vietnamese", location_hint="Mission Bay"),
    Preferences(doctor_name_heard="Dr. Kenji Kim", location_hint="Richmond Care Center", days=["Monday"],
                language="Arabic", latest="language"),
    Preferences(not_provider_ids=sorted(PROV)), Preferences(not_provider_ids=sorted(PROV), doctor_name_heard="Dr. Chen"),
    Preferences(days=["Thursday morning"]), Preferences(doctor_name_heard="not Dr. Chen"),
]


@pytest.mark.parametrize("kind", list(CALLERS))
def test_no_empty_or_broken_sentence_anywhere(catalog, schedule, kind):
    problems = []
    for vt in VT:   # every visit type, bookable or not
        for prefs in BATTERY:
            r = find_options(catalog, schedule, caller(kind), vt, copy.deepcopy(prefs), NOW)
            for n in r.notes:
                for p in sentence_problems(n.say):
                    problems.append((VT[vt]["name"], p, n.say))
    assert not problems, (len(problems), problems[:5])


# ---------------------------------------------------------------- a fully booked fortnight
def _fully_booked(catalog, vt):
    s = Schedule(catalog)
    minutes = VT[vt]["duration_min"]
    for p in catalog.providers_offering(vt):
        for lid in p.location_ids:
            for t in s.open_slots(p.id, lid, minutes, NOW):
                try:
                    s.book(p.id, t, minutes)
                except SlotTaken:   # overlaps a visit just booked: already gone
                    pass
            assert not s.open_slots(p.id, lid, minutes, NOW)
    return s


@pytest.mark.parametrize("vt", ["appt_027", "appt_002", "appt_000"])
def test_a_fully_booked_fortnight_never_crashes_and_says_so_plainly(catalog, vt):
    s = _fully_booked(catalog, vt)
    who = returning(list(SPECIALTIES))
    for prefs in BATTERY:
        r = find_options(catalog, s, who, vt, copy.deepcopy(prefs), NOW)
        if "bad_input" in [n.kind for n in r.notes]:
            continue
        assert not r.options
        assert r.notes and r.notes[-1].kind == "no_times", [n.say for n in r.notes]
        assert r.notes[-1].say == f"There are no open times for {VT[vt]['name']} in the next 14 days."
        assert "no_other_doctor" not in [n.kind for n in r.notes]
        assert not any("Doctors who can" in n.say for n in r.notes), [n.say for n in r.notes]
        for n in r.notes:
            assert not sentence_problems(n.say), n.say


# ---------------------------------------------------------------- "no other doctor": same-name doctors
@pytest.fixture(scope="module")
def twins():
    """A test catalog where two doctors share a name AND a specialty (the real catalog's
    same-name doctors all differ by specialty): a second Dr. Daniel Chen in Dermatology,
    listed right after the first, working only at Sunset Community Clinic."""
    raw = copy.deepcopy(RAW)
    i = next(i for i, p in enumerate(raw["providers"]) if p["name"] == "Dr. Daniel Chen" and p["specialty"] == "Dermatology")
    twin = copy.deepcopy(raw["providers"][i])
    twin["id"], twin["location_ids"] = "prov_twin", ["loc_006"]
    raw["providers"].insert(i + 1, twin)
    cat = Catalog(raw, EXTRAS)
    return cat, Schedule(cat), {p["id"]: p for p in raw["providers"]}


def test_same_name_same_specialty_doctors_both_get_their_locations(twins):
    cat, sch, prov = twins
    skin = "appt_027"
    able = sorted({p.id for p in cat.providers_offering(skin) for lid in p.location_ids
                   if sch.open_slots(p.id, lid, 30, NOW) and p.accepting_new_patients})
    assert "prov_twin" in able
    r = find_options(cat, sch, new_caller(), skin, Preferences(not_provider_ids=able), NOW)
    note = next(n.say for n in r.notes if n.kind == "no_other_doctor")
    names = re.match(r"No other doctor can do Skin Cancer Screening for you; (.+) are the only options\.$", note)
    assert names, note
    assert not who_can_problems(names.group(1), able, prov), (who_can_problems(names.group(1), able, prov), note)


def test_same_name_same_specialty_doctors_in_the_doctors_who_can_list(twins):
    cat, sch, prov = twins
    r = find_options(cat, sch, new_caller(), "appt_027", Preferences(doctor_name_heard="Dr. Linda Nguyen"), NOW)
    note = next(n.say for n in r.notes if "Doctors who can: " in n.say)
    listed = note.split("Doctors who can: ", 1)[1].rstrip(".")
    able = sorted({p.id for p in cat.providers_offering("appt_027") for lid in p.location_ids
                   if sch.open_slots(p.id, lid, 30, NOW) and p.accepting_new_patients})
    assert not who_can_problems(listed, able, prov), (who_can_problems(listed, able, prov), note)


# ---------------------------------------------------------------- "Doctors who can" across the catalog
@pytest.mark.parametrize("kind", list(CALLERS))
def test_doctors_who_can_list_whole_catalog(catalog, schedule, kind):
    """A doctor wish nobody can meet (a doctor who doesn't offer the visit): the list names
    only doctors who can, three at most, and the count adds up."""
    problems = []
    for vt in bookable(kind):
        able = sorted({s[0] for s in slots(schedule, kind, vt)})
        outsider = next((p for p in sorted(PROV) if vt not in PROV[p]["appointment_type_ids"]
                         and len([q for q in PROV.values() if q["name"] == PROV[p]["name"]]) == 1), None)
        if not outsider:
            continue
        r = find_options(catalog, schedule, caller(kind), vt, Preferences(doctor_name_heard=PROV[outsider]["name"]), NOW)
        note = [n.say for n in r.notes if n.kind == "wish_impossible"]
        if not able:
            if any("Doctors who can" in s for s in note):
                problems.append((VT[vt]["name"], "list with nobody open", note))
            continue
        if len(note) != 1 or "Doctors who can: " not in note[0]:
            problems.append((VT[vt]["name"], "no 'Doctors who can' note", [n.say for n in r.notes]))
            continue
        listed = note[0].split("Doctors who can: ", 1)[1].rstrip(".")
        problems += [(VT[vt]["name"], p, note[0]) for p in who_can_problems(listed, able)]
    assert not problems, (len(problems), problems[:4])


# ---------------------------------------------------------------- "The only doctors matching ..."
SURNAMES = sorted({x["name"].split()[-1] for x in PROV.values()
                   if sum(1 for y in PROV.values() if y["name"].split()[-1] == x["name"].split()[-1]) > 1})
ONLY_ONE = re.compile(r"^The only doctor matching '(?P<said>[^']+)' who can do this is (?P<names>.+), whom you turned "
                      r"down\. Check whether the caller wants that doctor after all\.$")
ONLY_MANY = re.compile(r"^The only doctors matching '(?P<said>[^']+)' who can do this are (?P<names>.+), whom you "
                       r"turned down\. Check whether the caller wants one of them after all\.$")


@pytest.mark.parametrize("kind", list(CALLERS))
def test_only_doctors_matching_note_whole_catalog(catalog, schedule, kind):
    problems, seen_plural = [], 0
    for surname in SURNAMES:
        family = sorted(p for p, x in PROV.items() if x["name"].split()[-1] == surname)
        for vt in bookable(kind):
            all_slots = slots(schedule, kind, vt)
            able = {s[0] for s in all_slots if s[0] in family}
            others = {s[0] for s in all_slots if s[0] not in family}
            if not able or not others:
                continue
            said = f"Dr. {surname}"
            r = find_options(catalog, schedule, caller(kind), vt,
                             Preferences(doctor_name_heard=said, not_provider_ids=family), NOW)
            where = (kind, VT[vt]["name"], said)
            want = sorted({PROV[p]["name"] for p in able})
            conflicts = [n.say for n in r.notes if n.kind == "wish_conflict"]
            if len(conflicts) != 1 or len(r.notes) != 1:
                problems.append((where, "expected exactly one wish_conflict note", [n.say for n in r.notes]))
                continue
            m = (ONLY_ONE if len(want) == 1 else ONLY_MANY).match(conflicts[0])
            if not m or m.group("said") != said:
                problems.append((where, "wording / singular-plural", conflicts[0]))
                continue
            # round 7 s5: three names, then "and N more"; the count must add up
            problems += [(where, p, conflicts[0]) for p in capped_names_problems(m.group("names"), set(want))]
            if not r.options or {o.provider_id for o in r.options} & set(family):
                problems.append((where, "turned-down doctor offered, or no options"))
            seen_plural += len(want) > 1
    assert not problems, (len(problems), problems[:4])
    assert seen_plural, "fixture: some visit type should have two or more such doctors"


# ---------------------------------------------------------------- languages not in our records
UNKNOWN = ["Klingon", "Chinese", "español", "ASL", "Cantonese", "Haitian Creole", "French", "Tagalog"]


@pytest.mark.parametrize("language", UNKNOWN)
@pytest.mark.parametrize("kind", list(CALLERS))
def test_a_language_not_in_our_records_gets_the_always_true_note_everywhere(catalog, schedule, language, kind):
    problems = []
    # "keeps the caller's capitals": "ASL" stays "ASL"; a first capital may be added ("español" -> "Español")
    shown = {language, language[:1].upper() + language[1:]}
    wants = {f"None of our doctors is listed as speaking {x}. Our doctors speak {OUR_LANGS}." for x in shown}
    for vt in bookable(kind):
        if not slots(schedule, kind, vt):
            continue
        base = find_options(catalog, schedule, caller(kind), vt, Preferences(), NOW)
        r = find_options(catalog, schedule, caller(kind), vt, Preferences(language=language), NOW)
        if [n.kind for n in r.notes] != ["wish_impossible"] or r.notes[0].say not in wants:
            problems.append((VT[vt]["name"], [(n.kind, n.say) for n in r.notes]))
        elif key(r) != key(base):   # options still offered: the same as with no language wish
            problems.append((VT[vt]["name"], "options differ from no language wish"))
    assert not problems, (len(problems), problems[:3])


@pytest.mark.parametrize("language", LANGS + [l.lower() for l in LANGS] + [l.upper() for l in LANGS])
def test_a_language_we_have_never_gets_the_not_in_our_records_note(catalog, schedule, language):
    for kind in CALLERS:
        for vt in bookable(kind)[:30]:
            r = find_options(catalog, schedule, caller(kind), vt, Preferences(language=language), NOW)
            assert not [n for n in r.notes if "is listed as speaking" in n.say], (language, [n.say for n in r.notes])
            for n in r.notes:
                if n.kind == "wish_impossible":   # the old sentence, with our spelling of the name
                    proper = next(l for l in LANGS if l.lower() == language.lower())
                    assert n.say == f"None of the doctors available to you for {VT[vt]['name']} speaks {proper}.", n.say


def test_two_language_names_are_refused(catalog, schedule):
    # Round 6 s6: "two language names ('English Spanish') are refused like other non-names".
    for value in ["English Spanish", "Spanish English", "Spanish French", "French Spanish", "Cantonese Mandarin",
                  "Spanish Portuguese"]:
        r = find_options(catalog, schedule, new_caller(), "appt_002", Preferences(language=value), NOW)
        assert not r.options and [n.kind for n in r.notes] == ["bad_input"], (value, [n.say for n in r.notes])


def test_mandarin_chinese_still_means_mandarin(catalog, schedule):
    r = find_options(catalog, schedule, new_caller(), "appt_002", Preferences(language="Mandarin Chinese"), NOW)
    speakers = {p for p, x in PROV.items() if "Mandarin" in x["languages"]}
    assert r.options and not r.notes and {o.provider_id for o in r.options} <= speakers
