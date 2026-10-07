"""Round 7 (spec-changes-round-7.md), section 5: every list of doctors in a note reads at
most three, then "and N more", with true names and a count that adds up.

Covered here: the same-name note, the "Doctors with that surname" note, the "can't do this"
reasons, and same-name labels (places joined with " / ") in a test catalog where two doctors
share a name AND a specialty. ("Doctors who can", "no other doctor" and both "whom you
turned down" notes are checked across the whole catalog in test_round5_notes.py and
test_round6_notes.py, updated for round 7.)

Expected answers come from catalog.json (read here directly) and the spec; the module's
fake calendar is used only as the source of open times.
"""

import copy
import json
import re
from collections import Counter

import pytest

from clinic import Catalog, Preferences, Schedule, find_options
from conftest import NOW, new_caller, returning
from reference import DATA, LOC, SPECIALTIES, VT, ref_bookable

RAW = json.loads((DATA / "catalog.json").read_text())
EXTRAS = json.loads((DATA / "location_extras.json").read_text())
CALLERS = {"new": (True, []), "returning-none": (False, []), "returning-all": (False, list(SPECIALTIES))}
SAME_NAME = re.compile(r"^There are (?P<n>\d+) doctors matching '(?P<heard>[^']+)' who offer (?P<vt>.+?): "
                       r"(?P<items>.+)\. Ask the caller which one they mean\.$")
GUESS = re.compile(r"^There's no doctor called (?P<heard>.+?)\. Doctors with that surname: (?P<items>.+)\. "
                   r"Check with the caller\.$")
CANT = re.compile(r"^No doctor matching '(?P<heard>[^']+)' can do this: (?P<parts>.+?)\."
                  r"(?: Doctors who can: (?P<who>.+)\.)?$")
REASONS = {
    "offer": re.compile(r"^(?P<names>.+) (?:doesn't|don't) offer (?P<vt>.+)$"),
    "new": re.compile(r"^(?P<names>.+) (?:isn't|aren't) taking new patients$"),
    "equipment": re.compile(r"^(?P<names>.+) (?:doesn't|don't) work at a location with the (?P<cap>\S+) equipment$"),
    "times": re.compile(r"^(?P<names>.+) (?:has|have) no open times for (?P<vt>.+) in the next 14 days$"),
}
LABEL = re.compile(r"^(?P<name>Dr\. [^(,]+?)(?: \((?P<spec>[^,()]+)(?:, (?P<places>[^()]+))?\))?$")


def world(raw):
    prov = {p["id"]: p for p in raw["providers"]}
    loc = {l["id"]: l for l in raw["locations"]}
    return prov, loc


PROV, _ = world(RAW)


def pairs_ok(prov, loc, is_new, vt):
    """(doctor, location) pairs passing rules 1, 2, 3 and 5 (doctor half), from the raw data."""
    cap = VT[vt].get("required_capability")
    return {(p, l) for p, x in prov.items() if vt in x["appointment_type_ids"]
            and not (is_new and not x["accepting_new_patients"])
            for l in x["location_ids"] if not cap or cap in loc[l]["capabilities"]}


def open_pairs(schedule, prov, loc, is_new, vt):
    return {(p, l) for p, l in pairs_ok(prov, loc, is_new, vt)
            if schedule.open_slots(p, l, VT[vt]["duration_min"], NOW)}


def caller(kind):
    is_new, refs = CALLERS[kind]
    return new_caller() if is_new else returning(refs)


def split_more(text, sep):
    """'A, B, C and 4 more' / 'A; B; C; and 4 more' -> (['A', 'B', 'C'], 4). Without 'more':
    'A, B and C' / 'A; B' -> (items, 0)."""
    if sep == "; ":
        items = text.split("; ")
        m = re.fullmatch(r"and (\d+) more", items[-1])
        return (items[:-1], int(m.group(1))) if m else (items, 0)
    m = re.fullmatch(r"(?P<shown>.+) and (?P<n>\d+) more", text)
    if m:
        return m.group("shown").split(", "), int(m.group("n"))
    parts = re.split(r", | and (?=Dr\. )", text)
    return parts, 0


def label_problems(items, prov, loc, candidates, want_places=None):
    """Each item names a candidate doctor; no two items read the same; a label with places
    names only that doctor's places (joined ' / ')."""
    out = []
    if len(set(items)) != len(items):
        out.append(f"two items read the same: {items}")
    for it in items:
        m = LABEL.match(it)
        if not m:
            out.append(f"unreadable item {it!r}")
            continue
        fits = [p for p in candidates if prov[p]["name"] == m.group("name")
                and (not m.group("spec") or prov[p]["specialty"] == m.group("spec"))]
        if m.group("places"):
            places = set(m.group("places").split(" / "))
            fits = [p for p in fits if places <= {loc[l]["name"] for l in prov[p]["location_ids"]}]
        if not fits:
            out.append(f"{it!r} is not one of the doctors it should be")
    return out


# =============================================================== the same-name note, whole catalog
SURNAMES = sorted(s for s, n in Counter(x["name"].split()[-1] for x in PROV.values()).items() if n > 1)
SHARED_FULL = sorted(n for n, c in Counter(x["name"] for x in PROV.values()).items() if c > 1)
HEARD = [f"Dr. {s}" for s in SURNAMES] + SHARED_FULL


@pytest.mark.parametrize("kind", list(CALLERS))
def test_same_name_note_whole_catalog(catalog, schedule, kind):
    is_new, refs = CALLERS[kind]
    _, loc = world(RAW)
    problems, seen_cut = [], 0
    for vt in VT:
        if not ref_bookable(is_new, refs, vt):
            continue
        pairs = open_pairs(schedule, PROV, loc, is_new, vt)
        for heard in HEARD:
            bare = heard.replace("Dr. ", "")
            fits = sorted({p for p, _ in pairs if (PROV[p]["name"].split()[-1] == bare if " " not in bare
                                                   else PROV[p]["name"] == heard)})
            r = find_options(catalog, schedule, caller(kind), vt, Preferences(doctor_name_heard=heard), NOW)
            notes = [n.say for n in r.notes if n.kind == "doctors_same_name"]
            where = (kind, VT[vt]["name"], heard)
            if len(fits) < 2:
                if notes:
                    problems.append((where, "same-name note with fewer than two such doctors", notes))
                continue
            if len(notes) != 1:
                problems.append((where, f"expected one same-name note for {len(fits)} doctors", [n.say for n in r.notes]))
                continue
            m = SAME_NAME.match(notes[0])
            if not m or m.group("heard") != heard or m.group("vt") != VT[vt]["name"]:
                problems.append((where, "wording", notes[0]))
                continue
            items, more = split_more(m.group("items"), "; ")
            seen_cut += more > 0
            if int(m.group("n")) != len(fits) or len(items) + more != len(fits):
                problems.append((where, f"count: says {m.group('n')}, lists {len(items)} + {more}, really {len(fits)}",
                                 notes[0]))
            if len(items) > 3 or (more and len(items) != 3):
                problems.append((where, f"{len(items)} doctors read out", notes[0]))
            for it in items:
                d = re.fullmatch(r"(?P<name>Dr\. .+?), (?P<title>\w+) \((?P<spec>[^()]+)\) at (?P<places>.+)", it)
                ok = d and any(PROV[p]["name"] == d.group("name") and PROV[p]["title"] == d.group("title")
                               and PROV[p]["specialty"] == d.group("spec")
                               and set(d.group("places").split(" / ")) == {loc[l]["name"] for q, l in pairs if q == p}
                               for p in fits)
                if not ok:
                    problems.append((where, f"item not true: {it!r}", notes[0]))
            if len(set(items)) != len(items):
                problems.append((where, "two items read the same", notes[0]))
    assert not problems, (len(problems), problems[:4])
    assert seen_cut, "fixture: some same-name note should be cut short (7 Dr. Chens)"


# =============================================================== "Doctors with that surname"
@pytest.mark.parametrize("surname", sorted({x["name"].split()[-1] for x in PROV.values()}))
def test_doctors_with_that_surname_note(catalog, schedule, surname):
    heard = f"Dr. Zebulon {surname}"
    family = [p for p, x in PROV.items() if x["name"].split()[-1] == surname]
    r = find_options(catalog, schedule, new_caller(), "appt_002", Preferences(doctor_name_heard=heard), NOW)
    notes = [n.say for n in r.notes if n.kind == "doctor_name_guess"]
    assert len(notes) == 1, [n.say for n in r.notes]
    m = GUESS.match(notes[0])
    assert m and m.group("heard") == heard, notes[0]
    items, more = split_more(m.group("items"), ", ")
    assert len(items) + more == len(family), (notes[0], len(family))
    assert len(items) == min(3, len(family)), notes[0]
    assert not label_problems(items, PROV, {l["id"]: l for l in RAW["locations"]}, family), \
        label_problems(items, PROV, {l["id"]: l for l in RAW["locations"]}, family)


# =============================================================== the "can't do this" reasons
def reason_true(code, p, prov, loc, is_new, vt, pairs):
    x, cap = prov[p], VT[vt].get("required_capability")
    if code == "offer":
        return vt not in x["appointment_type_ids"]
    if code == "new":
        return is_new and not x["accepting_new_patients"]
    if code == "equipment":
        return bool(cap) and not any(cap in loc[l]["capabilities"] for l in x["location_ids"])
    return not any(q == p for q, _ in pairs)   # times: nothing open


def cant_note_problems(note, heard, family, prov, loc, is_new, vt, pairs):
    """The whole "No doctor matching ... can do this: ..." note: every group capped at three
    names, each name's reason true, every matching doctor counted exactly once."""
    m = CANT.match(note)
    if not m or m.group("heard") != heard:
        return [f"wording: {note}"]
    out, total = [], 0
    for part in m.group("parts").split("; "):
        code = next((c for c, rx in REASONS.items() if rx.match(part)), None)
        if code is None:
            out.append(f"unknown reason in {part!r}")
            continue
        items, more = split_more(REASONS[code].match(part).group("names"), ", ")
        total += len(items) + more
        if len(items) > 3 or (more and len(items) != 3):
            out.append(f"{len(items)} names read in {part!r}")
        able = [p for p in family if reason_true(code, p, prov, loc, is_new, vt, pairs)]
        out += label_problems(items, prov, loc, able)
        group_size = len(items) + more
        if group_size > len(able):
            out.append(f"{group_size} doctors said to have reason {code}, only {len(able)} do")
    if total != len(family):
        out.append(f"count {total} != {len(family)} matching doctors")
    return out


@pytest.mark.parametrize("kind", list(CALLERS))
def test_cant_do_this_reasons_whole_catalog(catalog, schedule, kind):
    is_new, refs = CALLERS[kind]
    _, loc = world(RAW)
    problems, cut = [], 0
    for vt in VT:
        if not ref_bookable(is_new, refs, vt):
            continue
        pairs = open_pairs(schedule, PROV, loc, is_new, vt)
        for surname in SURNAMES:
            family = [p for p, x in PROV.items() if x["name"].split()[-1] == surname]
            if any(p in family for p, _ in pairs):
                continue      # someone with that name can: no "can't do this" note
            heard = f"Dr. {surname}"
            r = find_options(catalog, schedule, caller(kind), vt, Preferences(doctor_name_heard=heard), NOW)
            notes = [n.say for n in r.notes if n.say.startswith("No doctor matching")]
            if len(notes) != 1:
                problems.append(((kind, vt, heard), "expected one note", [n.say for n in r.notes]))
                continue
            cut += " more " in notes[0]
            problems += [((kind, VT[vt]["name"], heard), p, notes[0])
                         for p in cant_note_problems(notes[0], heard, family, PROV, loc, is_new, vt, pairs)]
    assert not problems, (len(problems), problems[:4])
    assert cut, "fixture: some group should be cut short (7 Dr. Chens)"


# =============================================================== same name AND same specialty
def _twin_catalog(change_both=None):
    """Two Dr. Daniel Chens in Dermatology: the real one (Downtown, Richmond) and a twin at
    Sunset. `change_both` edits both records (e.g. neither takes new patients)."""
    raw = copy.deepcopy(RAW)
    i = next(i for i, p in enumerate(raw["providers"]) if p["id"] == "prov_001")
    twin = copy.deepcopy(raw["providers"][i])
    twin.update(id="prov_twin", location_ids=["loc_006"])
    raw["providers"].insert(i + 1, twin)
    for p in raw["providers"]:
        if p["id"] in ("prov_001", "prov_twin") and change_both:
            p.update(change_both)
    cat = Catalog(raw, EXTRAS)
    prov, loc = world(raw)
    return cat, Schedule(cat), prov, loc


def test_same_name_same_specialty_in_the_cant_do_this_reasons():
    """Neither Dr. Daniel Chen takes new patients: the reason must not read
    "Dr. Daniel Chen and Dr. Daniel Chen aren't taking new patients" (s5: same-name
    doctors get their places added, every one of them, even sharing a specialty)."""
    cat, sch, prov, loc = _twin_catalog({"accepting_new_patients": False})
    r = find_options(cat, sch, new_caller(), "appt_027", Preferences(doctor_name_heard="Dr. Daniel Chen"), NOW)
    note = next(n.say for n in r.notes if n.say.startswith("No doctor matching"))
    pairs = open_pairs(sch, prov, loc, True, "appt_027")
    assert not cant_note_problems(note, "Dr. Daniel Chen", ["prov_001", "prov_twin"], prov, loc, True, "appt_027",
                                  pairs), (cant_note_problems(note, "Dr. Daniel Chen", ["prov_001", "prov_twin"], prov,
                                                              loc, True, "appt_027", pairs), note)


def test_same_name_same_specialty_in_the_surname_note():
    """A misheard first name: the "Doctors with that surname" list must tell the twins apart."""
    cat, sch, prov, loc = _twin_catalog()
    r = find_options(cat, sch, new_caller(), "appt_027", Preferences(doctor_name_heard="Dr. Zebulon Chen"), NOW)
    note = next(n.say for n in r.notes if n.kind == "doctor_name_guess")
    items, more = split_more(GUESS.match(note).group("items"), ", ")
    family = [p for p, x in prov.items() if x["name"].endswith(" Chen")]
    assert len(items) + more == len(family)
    shown_twins = [it for it in items if it.startswith("Dr. Daniel Chen")]
    if len(shown_twins) > 1:
        assert len(set(shown_twins)) == len(shown_twins), note


def test_same_name_same_specialty_in_the_same_name_note():
    cat, sch, prov, loc = _twin_catalog()
    r = find_options(cat, sch, new_caller(), "appt_027", Preferences(doctor_name_heard="Dr. Daniel Chen"), NOW)
    note = next(n.say for n in r.notes if n.kind == "doctors_same_name")
    items, more = split_more(SAME_NAME.match(note).group("items"), "; ")
    assert len(items) == 2 and len(set(items)) == 2 and more == 0, note
    assert any(it.endswith("at Downtown Health Center / Richmond Care Center") for it in items), note
    assert any(it.endswith("at Sunset Community Clinic") for it in items), note


@pytest.mark.parametrize("where", ["no_other_doctor", "doctors_who_can"])
def test_same_name_same_specialty_labels_use_a_slash(where):
    cat, sch, prov, loc = _twin_catalog()
    if where == "no_other_doctor":
        able = sorted({p for p, _ in open_pairs(sch, prov, loc, True, "appt_027")})
        r = find_options(cat, sch, new_caller(), "appt_027", Preferences(not_provider_ids=able), NOW)
        text = next(n.say for n in r.notes if n.kind == "no_other_doctor")
    else:
        r = find_options(cat, sch, new_caller(), "appt_027", Preferences(doctor_name_heard="Dr. Linda Nguyen"), NOW)
        text = next(n.say for n in r.notes if "Doctors who can: " in n.say)
    chens = re.findall(r"Dr\. Daniel Chen \(Dermatology[^)]*\)", text)
    for c in chens:
        assert c in ("Dr. Daniel Chen (Dermatology, Downtown Health Center / Richmond Care Center)",
                     "Dr. Daniel Chen (Dermatology, Sunset Community Clinic)"), text
    assert len(set(chens)) == len(chens), text
    assert " and Richmond" not in text, text


# =============================================================== a big test catalog: every list capped
@pytest.fixture(scope="module")
def crowd():
    """The real catalog plus 20 Dr. Okafors in Dermatology (12 not taking new patients),
    spread over our 8 locations."""
    raw = copy.deepcopy(RAW)
    derm = next(p for p in raw["providers"] if p["id"] == "prov_001")
    firsts = ["Ada", "Bola", "Chidi", "Dayo", "Ebere", "Femi", "Gozie", "Ike", "Jide", "Kemi", "Lola", "Musa",
              "Ngozi", "Obi", "Pelu", "Remi", "Sade", "Tunde", "Uche", "Wale"]
    for i, f in enumerate(firsts):
        d = copy.deepcopy(derm)
        d.update(id=f"prov_ok{i:02d}", name=f"Dr. {f} Okafor", accepting_new_patients=i >= 12,
                 location_ids=[sorted(LOC)[i % 8]])
        raw["providers"].append(d)
    cat = Catalog(raw, EXTRAS)
    prov, loc = world(raw)
    return cat, Schedule(cat), prov, loc


def _names_read(say, heard=""):
    return say.replace(heard, "").count("Dr. ")


@pytest.mark.parametrize("prefs", [
    {"doctor_name_heard": "Dr. Okafor"},                        # same-name note
    {"doctor_name_heard": "Dr. Zebulon Okafor"},                # "Doctors with that surname"
    {"doctor_name_heard": "Dr. Okafr"},                         # a close spelling
    {"doctor_name_heard": "Dr. Wei Lee"},                       # "Doctors who can"
    {"not_provider_ids": "ALL"},                                # no other doctor
    {"doctor_name_heard": "Dr. Okafor", "not_provider_ids": "OKAFORS"},   # whom you turned down (doctor)
    {"location_hint": "Sunset", "not_provider_ids": "AT_SUNSET"},         # whom you turned down (place)
])
def test_every_doctor_list_reads_at_most_three_on_a_big_catalog(crowd, prefs):
    cat, sch, prov, loc = crowd
    prefs = dict(prefs)
    able = sorted({p for p, _ in open_pairs(sch, prov, loc, True, "appt_027")})
    okafors = [p for p in able if prov[p]["name"].endswith("Okafor")]
    at_sunset = sorted({p for p, l in open_pairs(sch, prov, loc, True, "appt_027") if l == "loc_006"})
    prefs["not_provider_ids"] = {"ALL": able, "OKAFORS": okafors, "AT_SUNSET": at_sunset}.get(
        prefs.get("not_provider_ids"), [])
    r = find_options(cat, sch, new_caller(), "appt_027", Preferences(**prefs), NOW)
    assert r.notes, "fixture: a note with a list was expected"
    for n in r.notes:
        assert _names_read(n.say, prefs.get("doctor_name_heard", "")) <= 3, (n.kind, n.say)


def test_the_cant_do_this_reasons_on_a_big_catalog(crowd):
    """Dr. Okafor (20 doctors, all Dermatology) for an Annual Physical, which none of them
    offers: one "don't offer" group, read three then "and 17 more", every reason true."""
    cat, sch, prov, loc = crowd
    okafors = [p for p, x in prov.items() if x["name"].endswith("Okafor")]
    r = find_options(cat, sch, new_caller(), "appt_002", Preferences(doctor_name_heard="Dr. Okafor"), NOW)
    note = next(n.say for n in r.notes if n.say.startswith("No doctor matching"))
    pairs = open_pairs(sch, prov, loc, True, "appt_002")
    assert not cant_note_problems(note, "Dr. Okafor", okafors, prov, loc, True, "appt_002", pairs), \
        (cant_note_problems(note, "Dr. Okafor", okafors, prov, loc, True, "appt_002", pairs), note)
    assert "and 17 more" in note and _names_read(note, "Dr. Okafor") <= 6, note   # 3 + up to 3 "Doctors who can"
