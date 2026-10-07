"""Round 2, spec change 1: newest wish wins, wishes are applied strongest first,
and every note is true. Differential checks against round2_reference.py."""

import random
from datetime import timedelta

import pytest

from clinic import BOOKING, BookingCard, Choices, Preferences, find_options
from conftest import NOW, new_caller, returning
from reference import LOC, PROV, SPECIALTIES, VT, ref_bookable, ref_pairs
from round2_reference import RESTRICT_PHRASES, check, interpret, universe

CALLERS = {"new": (True, []), "returning-all": (False, list(SPECIALTIES)), "returning-none": (False, [])}
KNOWN_LANGS = sorted({l for p in PROV.values() for l in p["languages"]})
LANGS = KNOWN_LANGS + ["Klingon", "spanish"]
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "today", "tomorrow", "thu",
        (NOW + timedelta(days=7)).date().isoformat(), (NOW + timedelta(days=20)).date().isoformat()]
FULL_NAMES = sorted({p["name"] for p in PROV.values()})
SURNAMES = sorted({"Dr. " + p["name"].split()[-1] for p in PROV.values()})
PLACES = sorted(RESTRICT_PHRASES)

_UNIVERSE = {}


def slots_for(schedule, kind, vt):
    key = (kind, vt)
    if key not in _UNIVERSE:
        is_new, refs = CALLERS[kind]
        _UNIVERSE[key] = universe(schedule, is_new, refs, vt)
    return _UNIVERSE[key]


def caller_for(kind):
    is_new, refs = CALLERS[kind]
    return new_caller() if is_new else returning(refs)


def random_prefs(rng):
    p = Preferences()
    doctor = rng.choice(["none", "heard", "heard", "carried"])
    if doctor == "heard":
        p.doctor_name_heard = rng.choice(FULL_NAMES + SURNAMES)
    elif doctor == "carried":
        p.preferred_provider_id = rng.choice(sorted(PROV))
    place = rng.choice(["none", "hint", "carried"])
    if place == "hint":
        p.location_hint = rng.choice(PLACES)
    elif place == "carried":
        p.preferred_location_id = rng.choice(sorted(LOC))
    if rng.random() < 0.6:
        p.days = rng.sample(DAYS, rng.choice([1, 1, 2]))
    if rng.random() < 0.4:
        p.time_of_day = rng.choice(["morning", "afternoon"])
    if rng.random() < 0.4:
        p.language = rng.choice(LANGS)
    said = [k for k, on in (("doctor", bool(p.doctor_name_heard)), ("location", bool(p.location_hint)),
                            ("time", bool(p.days or p.time_of_day)), ("language", bool(p.language))) if on]
    p.latest = rng.choice([""] + said)
    return p


def _latest_kind(p):
    return {"location": "place"}.get(p.latest, p.latest)


@pytest.mark.parametrize("seed", range(12))
def test_random_wish_combinations_agree_with_spec_model(catalog, schedule, seed):
    rng = random.Random(seed)
    kind = rng.choice(list(CALLERS))
    is_new, refs = CALLERS[kind]
    vts = [vt for vt in VT if ref_bookable(is_new, refs, vt)]
    problems = []
    for _ in range(120):
        vt = rng.choice(vts)
        p = random_prefs(rng)
        model_prefs = Preferences(**{**p.__dict__, "latest": _latest_kind(p)})
        r = find_options(catalog, schedule, caller_for(kind), vt, p, NOW)
        slots = slots_for(schedule, kind, vt)
        for prob in check(r, slots, interpret(model_prefs)):
            problems.append((kind, VT[vt]["name"], {k: v for k, v in p.__dict__.items() if v}, prob))
    assert not problems, (len(problems), problems[:4])


@pytest.mark.parametrize("latest", ["", "doctor", "location", "time", "language"])
def test_four_way_clash_each_latest(catalog, schedule, latest):
    """Doctor + place + day + language all said at once, latest set to each value,
    across every bookable visit type for a returning patient with all referrals."""
    caller = caller_for("returning-all")
    problems = []
    for vt in VT:
        if not ref_bookable(False, list(SPECIALTIES), vt):
            continue
        pairs = sorted(ref_pairs(False, vt))
        pid = pairs[0][0]
        other_loc = next((lid for lid in sorted(LOC) if lid not in PROV[pid]["location_ids"]), None)
        p = Preferences(doctor_name_heard=PROV[pid]["name"], location_hint=LOC[other_loc]["name"] if other_loc else "",
                        days=["Monday"], language="Vietnamese", latest=latest)
        r = find_options(catalog, schedule, caller, vt, p, NOW)
        model = Preferences(**{**p.__dict__, "latest": _latest_kind(p)})
        for prob in check(r, slots_for(schedule, "returning-all", vt), interpret(model)):
            problems.append((VT[vt]["name"], prob))
    assert not problems, (len(problems), problems[:4])


@pytest.mark.parametrize("day", ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"])
def test_carried_doctor_and_place_after_time_change_whole_catalog(catalog, schedule, day):
    """The change table end to end: a booked-looking card, then change_choice('time', day).
    The day is the newest wish; carried doctor and place give way and notes stay true."""
    caller = caller_for("returning-all")
    problems = []
    for vt in VT:
        if not ref_bookable(False, list(SPECIALTIES), vt):
            continue
        slots = slots_for(schedule, "returning-all", vt)
        for pid, lid in sorted({(s[0], s[1]) for s in slots})[:4]:
            card = BookingCard(caller=caller)
            card.choices = Choices(specialty=VT[vt]["specialty"], visit_type_id=vt, provider_id=pid,
                                   location_id=lid, slot=NOW + timedelta(days=2))
            assert card.change_choice("time", day) == BOOKING
            p = card.preferences
            assert (p.preferred_provider_id, p.preferred_location_id, p.days, p.latest) == (pid, lid, [day], "time")
            r = find_options(catalog, schedule, caller, vt, p, NOW)
            for prob in check(r, slots, interpret(p)):
                problems.append((VT[vt]["name"], PROV[pid]["name"], LOC[lid]["name"], prob))
    assert not problems, (len(problems), problems[:4])


@pytest.mark.parametrize("what,value", [("location", "the Midtown one"), ("doctor", "Dr. Kenji Kim"),
                                        ("location", "Richmond Care Center"), ("doctor", "Dr. Daniel Smith"),
                                        ("doctor", "Dr. Garcia"), ("location", "Mission Bay")])
@pytest.mark.parametrize("kind", ["new", "returning-all"])
def test_change_doctor_or_location_end_to_end(catalog, schedule, what, value, kind):
    """Skin Cancer Screening with Dr. Daniel Chen at Downtown, then one change."""
    caller = caller_for(kind)
    card = BookingCard(caller=caller)
    card.choices = Choices(specialty="Dermatology", visit_type_id="appt_027", provider_id="prov_001",
                           location_id="loc_004", slot=NOW + timedelta(days=2))
    card.change_choice(what, value)
    r = find_options(catalog, schedule, caller, "appt_027", card.preferences, NOW)
    model = Preferences(**{**card.preferences.__dict__, "latest": _latest_kind(card.preferences)})
    assert not check(r, slots_for(schedule, kind, "appt_027"), interpret(model))


def test_spec_example_conflict_note_wording(catalog, schedule):
    """Spec: 'Dr. Daniel Chen isn't available at Midtown Medical Group.'"""
    caller = new_caller()
    card = BookingCard(caller=caller)
    card.choices = Choices(specialty="Dermatology", visit_type_id="appt_027", provider_id="prov_001",
                           location_id="loc_004", slot=NOW + timedelta(days=2))
    card.change_choice("location", "the Midtown one")
    r = find_options(catalog, schedule, caller, "appt_027", card.preferences, NOW)
    assert r.options and all(o.location_id == "loc_005" for o in r.options)
    conflicts = [n for n in r.notes if n.kind == "wish_conflict"]
    assert conflicts and "Daniel Chen" in conflicts[0].say and "Midtown Medical Group" in conflicts[0].say


def test_language_impossible_note_is_literally_true(catalog, schedule):
    """'None of the doctors who offer X speaks L' must be true as a sentence. For a new
    patient wanting Hindi for Skin Cancer Screening, Dr. Wei Sato (Dermatology, Hindi)
    DOES offer it; he just isn't taking new patients. Spec: 'Every note must be true.'"""
    hindi_offering = [p["name"] for p in PROV.values()
                      if "appt_027" in p["appointment_type_ids"] and "Hindi" in p["languages"]]
    assert hindi_offering  # from catalog.json: Dr. Wei Sato
    # Round 3 s4: the note now reads "None of the doctors available to you for X speaks Y."
    # (Only doctors this caller can actually book, with open times, count.) Dr. Wei Sato
    # can't be booked by a new patient, so for a new caller the sentence is true.
    available_hindi = {p for p, _, _ in universe(schedule, True, [], "appt_027") if "Hindi" in PROV[p]["languages"]}
    assert not available_hindi
    r = find_options(catalog, schedule, new_caller(), "appt_027", Preferences(language="Hindi"), NOW)
    says = [n.say for n in r.notes if n.kind == "wish_impossible"]
    assert says == ["None of the doctors available to you for Skin Cancer Screening speaks Hindi."], says
    assert r.options


def test_language_impossible_notes_true_whole_catalog(catalog, schedule):
    """Same check across every visit type, language and caller kind."""
    false = []
    for kind in CALLERS:
        is_new, refs = CALLERS[kind]
        for vt in VT:
            if not ref_bookable(is_new, refs, vt):
                continue
            for lang in LANGS:
                r = find_options(catalog, schedule, caller_for(kind), vt, Preferences(language=lang), NOW)
                # Round 3 s4: truth = no doctor this caller can book, with open times, speaks it.
                speakers = sorted({PROV[p]["name"] for p, _, _ in slots_for(schedule, kind, vt)
                                   if lang.lower() in [x.lower() for x in PROV[p]["languages"]]})
                impossible = [n.say for n in r.notes if n.kind == "wish_impossible"]
                if speakers and impossible:
                    false.append((kind, VT[vt]["name"], lang, speakers, impossible))
                if not speakers and slots_for(schedule, kind, vt):
                    want = f"None of the doctors available to you for {VT[vt]['name']} speaks {lang.capitalize()}."
                    if lang.lower() not in {x.lower() for x in KNOWN_LANGS}:  # round 6 s5: not in our records
                        want = (f"None of our doctors is listed as speaking {lang}. Our doctors speak "
                                + ", ".join(KNOWN_LANGS[:-1]) + f" and {KNOWN_LANGS[-1]}.")
                    if impossible != [want]:
                        false.append((kind, VT[vt]["name"], lang, "expected", want, impossible))
    assert not false, (len(false), false[:5])


def test_place_impossible_note_does_not_claim_closest_when_soonest(catalog, schedule):
    """With soonest=True, options are ranked by time (spec 7), so a note saying
    'these are the closest alternatives' would be untrue."""
    # Visit types nobody can do at Mission Bay (loc_000): the place wish is impossible.
    bad = []
    for vt in VT:
        if not ref_bookable(False, list(SPECIALTIES), vt):
            continue
        if any(l == "loc_000" for _, l in ref_pairs(False, vt)):
            continue
        r = find_options(catalog, schedule, caller_for("returning-all"), vt,
                         Preferences(location_hint="Mission Bay Health Center", soonest=True), NOW)
        for n in r.notes:
            if "closest alternatives" in n.say:
                bad.append((VT[vt]["name"], str(n), [o.start.isoformat() for o in r.options]))
    assert not bad, (len(bad), bad[:3])


def test_carried_doctor_with_latest_doctor_set_directly(catalog, schedule):
    """Spec 1: latest (set by change_choice OR SET DIRECTLY) is strongest of all.
    Carried Dr. Daniel Chen + said 'the Midtown one' + latest='doctor': the doctor should win.
    (Ambiguous spec corner: change_choice never produces this, but the spec allows setting it.)"""
    p = Preferences(preferred_provider_id="prov_001", location_hint="the Midtown one", latest="doctor")
    r = find_options(catalog, schedule, new_caller(), "appt_027", p, NOW)
    assert r.options and all(o.provider_id == "prov_001" for o in r.options), \
        ([(o.provider_name, o.location_name) for o in r.options], [str(n) for n in r.notes])


def test_time_wish_with_said_doctor_latest_time(catalog, schedule):
    """Echocardiogram, said doctor Dr. David Chen, 'Monday', latest='time': Monday wins.
    Round-1 F2 case."""
    vt = next(v for v, a in VT.items() if a["name"] == "Echocardiogram")
    slots = universe(schedule, False, list(SPECIALTIES), vt)
    for latest in ["time", "doctor", ""]:
        p = Preferences(doctor_name_heard="Dr. David Chen", days=["Monday"], latest=latest)
        r = find_options(catalog, schedule, caller_for("returning-all"), vt, p, NOW)
        assert not check(r, slots, interpret(p)), (latest, [str(n) for n in r.notes])
        for n in r.notes:
            if n.say.lower().startswith("nothing is open"):
                assert not any(s[2].weekday() == 0 for s in slots), n


def test_location_change_beats_a_said_doctor(catalog, schedule):
    """Spec 1: the most recent change is strongest of all. A new caller asked for
    Dr. Daniel Chen (said, not yet chosen) for Skin Cancer Screening, then says
    'actually, the Midtown one'. change_choice sets latest='location'. Dr. Daniel
    Chen doesn't work at Midtown; Dr. Kenji Kim does skin screening there.
    Expected: Midtown options, and a note that Dr. Daniel Chen isn't available there."""
    caller = new_caller()
    card = BookingCard(caller=caller, preferences=Preferences(doctor_name_heard="Dr. Daniel Chen"))
    card.choices = Choices(specialty="Dermatology", visit_type_id="appt_027")
    assert card.change_choice("location", "the Midtown one") == BOOKING
    assert card.preferences.latest == "location"
    r = find_options(catalog, schedule, caller, "appt_027", card.preferences, NOW)
    assert r.options and all(o.location_id == "loc_005" for o in r.options), \
        ([(o.provider_name, o.location_name) for o in r.options], [str(n) for n in r.notes])
    assert any(n.kind == "wish_conflict" and "Daniel Chen" in n.say for n in r.notes)


def test_latest_location_set_directly_beats_said_doctor(catalog, schedule):
    p = Preferences(doctor_name_heard="Dr. Garcia", location_hint="the Hayes Valley one", latest="location")
    r = find_options(catalog, schedule, returning(), "appt_017", p, NOW)
    assert r.options and all(o.location_id == "loc_005" for o in r.options), \
        ([(o.provider_name, o.location_name) for o in r.options], [str(n) for n in r.notes])
