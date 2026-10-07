"""Round 3, spec change 4: the newest wish wins whatever it is (even a carried-over one),
time changes split into day and time of day, "someone else, please", "any" doctor wishes,
and notes that say only true things. Differential checks against round2_reference.py
(updated to the round-3 spec) and against catalog.json."""

import random
import re
from datetime import timedelta

import pytest

from clinic import BOOKING, BookingCard, Choices, Preferences, find_options
from clinic.card import DOCTOR, LANGUAGE, LOCATION, TIME
from conftest import NOW, new_caller, returning
from reference import LOC, PROV, SPECIALTIES, VT, ref_bookable
from round2_reference import check, interpret, universe

CALLERS = {"new": (True, []), "returning-all": (False, list(SPECIALTIES)), "returning-none": (False, [])}
_U = {}


def slots_for(schedule, kind, vt):
    if (kind, vt) not in _U:
        is_new, refs = CALLERS[kind]
        _U[(kind, vt)] = universe(schedule, is_new, refs, vt)
    return _U[(kind, vt)]


def caller_for(kind):
    is_new, refs = CALLERS[kind]
    return new_caller() if is_new else returning(refs)


def bookable_vts(kind):
    is_new, refs = CALLERS[kind]
    return [vt for vt in VT if ref_bookable(is_new, refs, vt)]


def says(r, kind=None):
    return [n.say for n in r.notes if kind is None or n.kind == kind]


def test_shared_constants():
    assert (DOCTOR, LOCATION, TIME, LANGUAGE) == ("doctor", "location", "time", "language")


# ---------------------------------------------------------------- newest wish wins, through change_choice
def _combos(schedule, kind, vt, n_doctors=3):
    slots = slots_for(schedule, kind, vt)
    doctors = sorted({s[0] for s in slots})[:n_doctors]
    places = sorted({s[1] for s in slots})
    return slots, doctors, places


@pytest.mark.parametrize("kind", ["new", "returning-all"])
def test_location_change_after_a_said_doctor_whole_catalog(catalog, schedule, kind):
    """Caller NAMED a doctor (not yet chosen), then changes location: the place wins."""
    problems = []
    for vt in bookable_vts(kind):
        slots, doctors, places = _combos(schedule, kind, vt)
        for pid in doctors:
            for lid in places:
                card = BookingCard(caller=caller_for(kind), preferences=Preferences(doctor_name_heard=PROV[pid]["name"]))
                card.choices = Choices(specialty=VT[vt]["specialty"], visit_type_id=vt)
                assert card.change_choice("location", LOC[lid]["name"]) == BOOKING
                p = card.preferences
                assert p.latest == "location" and p.doctor_name_heard == PROV[pid]["name"]
                r = find_options(catalog, schedule, card.caller, vt, p, NOW)
                problems += [(VT[vt]["name"], PROV[pid]["name"], LOC[lid]["name"], x) for x in check(r, slots, interpret(p))]
                unique = sum(1 for q in PROV.values() if q["name"] == PROV[pid]["name"]) == 1
                if unique and r.options and all(o.location_id == lid for o in r.options) \
                        and lid not in PROV[pid]["location_ids"]:
                    want = f"{PROV[pid]['name']} isn't available at {LOC[lid]['name']}."
                    if want not in says(r, "wish_conflict"):
                        problems.append((VT[vt]["name"], "wording", want, says(r)))
    assert not problems, (len(problems), problems[:4])


@pytest.mark.parametrize("kind", ["new", "returning-all"])
def test_location_change_after_a_chosen_doctor_whole_catalog(catalog, schedule, kind):
    """Doctor CHOSEN (so carried over), then a location change: the place wins."""
    problems = []
    for vt in bookable_vts(kind):
        slots, doctors, places = _combos(schedule, kind, vt)
        for pid in doctors:
            home = next(s[1] for s in slots if s[0] == pid)
            for lid in places:
                card = BookingCard(caller=caller_for(kind))
                card.choices = Choices(specialty=VT[vt]["specialty"], visit_type_id=vt, provider_id=pid,
                                       location_id=home, slot=NOW + timedelta(days=1))
                card.change_choice("location", LOC[lid]["name"])
                p = card.preferences
                assert (p.preferred_provider_id, p.latest) == (pid, "location")
                r = find_options(catalog, schedule, card.caller, vt, p, NOW)
                problems += [(VT[vt]["name"], PROV[pid]["name"], LOC[lid]["name"], x) for x in check(r, slots, interpret(p))]
    assert not problems, (len(problems), problems[:4])


@pytest.mark.parametrize("kind", ["new", "returning-all"])
def test_doctor_change_after_said_or_chosen_place_whole_catalog(catalog, schedule, kind):
    problems = []
    for vt in bookable_vts(kind):
        slots, doctors, places = _combos(schedule, kind, vt)
        for lid in places:
            for pid in doctors:
                # said place, then the doctor changes
                card = BookingCard(caller=caller_for(kind), preferences=Preferences(location_hint=LOC[lid]["name"]))
                card.choices = Choices(specialty=VT[vt]["specialty"], visit_type_id=vt)
                card.change_choice("doctor", PROV[pid]["name"])
                p = card.preferences
                r = find_options(catalog, schedule, card.caller, vt, p, NOW)
                problems += [("said", VT[vt]["name"], x) for x in check(r, slots, interpret(p))]
                if r.options and lid not in PROV[pid]["location_ids"] and \
                        sum(1 for q in PROV.values() if q["name"] == PROV[pid]["name"]) == 1:
                    want = f"{LOC[lid]['name']} isn't available with {PROV[pid]['name']}."
                    if want not in says(r, "wish_conflict"):
                        problems.append((VT[vt]["name"], "wording", want, says(r)))
                # chosen place (carried), then the doctor changes
                other = next((s for s in slots if s[1] == lid), None)
                if other:
                    card = BookingCard(caller=caller_for(kind))
                    card.choices = Choices(specialty=VT[vt]["specialty"], visit_type_id=vt, provider_id=other[0],
                                           location_id=lid, slot=other[2])
                    card.change_choice("doctor", PROV[pid]["name"])
                    p = card.preferences
                    assert p.preferred_location_id == lid and p.latest == "doctor"
                    r = find_options(catalog, schedule, card.caller, vt, p, NOW)
                    problems += [("carried", VT[vt]["name"], x) for x in check(r, slots, interpret(p))]
    assert not problems, (len(problems), problems[:4])


@pytest.mark.parametrize("latest", ["doctor", "location"])
def test_latest_promotes_a_carried_wish_whole_catalog(catalog, schedule, latest):
    """Spec s4: latest 'promotes that kind of wish to strongest, even if it's a carried-over choice'."""
    kind = "returning-all"
    problems = []
    for vt in bookable_vts(kind):
        slots, doctors, places = _combos(schedule, kind, vt)
        for pid in doctors:
            for lid in places:
                if latest == "doctor":
                    p = Preferences(preferred_provider_id=pid, location_hint=LOC[lid]["name"], latest="doctor")
                    winner = lambda o: o.provider_id == pid  # noqa: E731
                else:
                    p = Preferences(preferred_location_id=lid, doctor_name_heard=PROV[pid]["name"], latest="location")
                    winner = lambda o: o.location_id == lid  # noqa: E731
                r = find_options(catalog, schedule, caller_for(kind), vt, p, NOW)
                problems += [(VT[vt]["name"], x) for x in check(r, slots, interpret(p))]
                if not r.options or not all(winner(o) for o in r.options):
                    problems.append((VT[vt]["name"], PROV[pid]["name"], LOC[lid]["name"], "latest carried wish lost",
                                     [(o.provider_name, o.location_name) for o in r.options]))
    assert not problems, (len(problems), problems[:4])


@pytest.mark.parametrize("seed", range(10))
def test_random_combinations_latest_any_wish_including_carried(catalog, schedule, seed):
    rng = random.Random(1000 + seed)
    kind = rng.choice(list(CALLERS))
    vts = bookable_vts(kind)
    names = sorted({p["name"] for p in PROV.values()})
    langs = sorted({l for p in PROV.values() for l in p["languages"]}) + ["Klingon"]
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "today", "tomorrow",
            (NOW + timedelta(days=8)).date().isoformat(), (NOW + timedelta(days=15)).date().isoformat(),
            (NOW - timedelta(days=1)).date().isoformat()]
    problems = []
    for _ in range(100):
        vt = rng.choice(vts)
        p = Preferences()
        present = []
        d = rng.choice(["none", "said", "carried"])
        if d == "said":
            p.doctor_name_heard = rng.choice(names); present.append("doctor")
        elif d == "carried":
            p.preferred_provider_id = rng.choice(sorted(PROV)); present.append("doctor")
        pl = rng.choice(["none", "said", "carried"])
        if pl == "said":
            p.location_hint = LOC[rng.choice(sorted(LOC))]["name"]; present.append("location")
        elif pl == "carried":
            p.preferred_location_id = rng.choice(sorted(LOC)); present.append("location")
        if rng.random() < 0.5:
            p.days = [rng.choice(days)]; present.append("time")
        if rng.random() < 0.3:
            p.time_of_day = rng.choice(["morning", "afternoon"])
            if "time" not in present:
                present.append("time")
        if rng.random() < 0.4:
            p.language = rng.choice(langs); present.append("language")
        if rng.random() < 0.2:
            p.not_provider_ids = rng.sample(sorted({s[0] for s in slots_for(schedule, kind, vt)}) or ["prov_001"], 1)
        p.latest = rng.choice([""] + present)
        r = find_options(catalog, schedule, caller_for(kind), vt, p, NOW)
        for x in check(r, slots_for(schedule, kind, vt), interpret(p)):
            problems.append((kind, VT[vt]["name"], {k: v for k, v in p.__dict__.items() if v}, x))
    assert not problems, (len(problems), problems[:4])


# ---------------------------------------------------------------- spec wording examples
def test_conflict_wording_examples(catalog, schedule):
    # Skin Cancer Screening, new caller: Dr. Daniel Chen (English, Arabic; Downtown, Richmond).
    c = new_caller()
    r = find_options(catalog, schedule, c, "appt_027",
                     Preferences(doctor_name_heard="Dr. Daniel Chen", language="Spanish"), NOW)
    assert "No Spanish-speaking doctor is available with Dr. Daniel Chen." in says(r, "wish_conflict")
    # a time clash: a uniquely named doctor with nothing on a weekday when others have times
    for vt in bookable_vts("returning-all"):
        slots = slots_for(schedule, "returning-all", vt)
        for pid in sorted({s[0] for s in slots}):
            name = PROV[pid]["name"]
            if sum(1 for q in PROV.values() if q["name"] == name) > 1:
                continue
            for day in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]:
                mine = [s for s in slots if s[0] == pid and s[2].strftime("%A") == day]
                others = [s for s in slots if s[2].strftime("%A") == day]
                if not mine and others:
                    r = find_options(catalog, schedule, returning(list(SPECIALTIES)), vt,
                                     Preferences(doctor_name_heard=name, days=[day]), NOW)
                    assert f"There's nothing on {day} with {name}." in says(r, "wish_conflict"), says(r)
                    return
    pytest.skip("no time clash found in the calendar")


def test_an_arabic_speaking_doctor(catalog, schedule):
    # Kenji Kim + Arabic, language latest -> the doctor clash note reads "an Arabic-speaking doctor"
    r = find_options(catalog, schedule, returning(list(SPECIALTIES)), "appt_027",
                     Preferences(doctor_name_heard="Dr. Kenji Kim", language="Arabic", latest="language"), NOW)
    text = " ".join(says(r))
    assert "a Arabic" not in text and "A Arabic" not in text
    if r.options and "Kenji Kim" in text:
        assert "an Arabic-speaking doctor" in text, says(r)


# ---------------------------------------------------------------- notes say only true things, whole catalog
GRAMMAR = [re.compile(r"\b[Aa] [AEIOUaeiou]\w*-speaking"), re.compile(r"  "), re.compile(r" [.,;]"),
           re.compile(r"\bNone\b(?! of)"), re.compile(r"\[|\]"), re.compile(r"\.\.")]


def _who_can_names(say):
    if "Doctors who can:" not in say:
        return []
    tail = say.split("Doctors who can:")[1]
    tail = re.sub(r" and \d+ more", "", tail)
    return [m.strip() for m in re.findall(r"(Dr\. [A-Z][a-z]+ [A-Z][a-z]+)", tail)]


@pytest.mark.parametrize("kind", list(CALLERS))
def test_every_note_is_true_and_well_formed_whole_catalog(catalog, schedule, kind):
    """Doctor wishes for every doctor name and surname, plus language and day wishes, on every
    bookable visit type: language 'impossible' notes, 'Doctors who can' lists and grammar."""
    problems = []
    names = sorted({p["name"] for p in PROV.values()}) + sorted({"Dr. " + p["name"].split()[-1] for p in PROV.values()})
    langs = sorted({l for p in PROV.values() for l in p["languages"]})
    rng = random.Random(7)
    for vt in bookable_vts(kind):
        slots = slots_for(schedule, kind, vt)
        can = {PROV[s[0]]["name"] for s in slots}
        for name in rng.sample(names, 12):
            p = Preferences(doctor_name_heard=name, language=rng.choice(langs), days=[rng.choice(["Monday", "Friday"])])
            r = find_options(catalog, schedule, caller_for(kind), vt, p, NOW)
            for n in r.notes:
                for g in GRAMMAR:
                    if g.search(n.say):
                        problems.append((VT[vt]["name"], "grammar", g.pattern, n.say))
                if not n.say.rstrip().endswith((".", "?")):
                    problems.append((VT[vt]["name"], "no full stop", n.say))
                for who in _who_can_names(n.say):
                    if who not in can:
                        problems.append((VT[vt]["name"], "listed as able but can't", who, n.say))
                if n.kind == "wish_impossible" and n.say.startswith("None of the doctors available to you"):
                    if any(p.language.lower() in [x.lower() for x in PROV[s[0]]["languages"]] for s in slots):
                        problems.append((VT[vt]["name"], "false language note", n.say))
    assert not problems, (len(problems), problems[:5])


# ---------------------------------------------------------------- "someone else, please"
# Round 5 (spec-changes-round-5.md s1-s2): the code no longer reads "someone else" or "".
# The AI gives a clear instruction instead: turn_down_doctors(catalog, current=True) for
# "someone else" about the chosen (or carried-over) doctor. These tests now make that call.
def _chosen_card(kind, vt, pid, lid, slot):
    card = BookingCard(caller=caller_for(kind))
    card.choices = Choices(specialty=VT[vt]["specialty"], visit_type_id=vt, provider_id=pid, location_id=lid, slot=slot)
    return card


@pytest.mark.parametrize("kind", ["new", "returning-all"])
def test_someone_else_whole_catalog(catalog, schedule, kind):
    problems = []
    for vt in bookable_vts(kind):
        slots = slots_for(schedule, kind, vt)
        if not slots:
            continue
        pid, lid, start = slots[0]
        card = _chosen_card(kind, vt, pid, lid, start)
        assert card.turn_down_doctors(catalog, current=True) == BOOKING
        p = card.preferences
        if pid not in p.not_provider_ids:
            problems.append((VT[vt]["name"], "not recorded", p.not_provider_ids))
        r = find_options(catalog, schedule, card.caller, vt, p, NOW)
        others = {s[0] for s in slots} - {pid}
        if others:
            if any(o.provider_id == pid for o in r.options) or not r.options:
                problems.append((VT[vt]["name"], "turned-down doctor offered again or nothing offered"))
            if "no_other_doctor" in [n.kind for n in r.notes]:
                problems.append((VT[vt]["name"], "no_other_doctor note although others exist"))
        else:
            if not r.options or any(o.provider_id != pid for o in r.options):
                problems.append((VT[vt]["name"], "only doctor should stay"))
            nod = says(r, "no_other_doctor")
            if len(nod) != 1 or PROV[pid]["name"] not in nod[0]:
                problems.append((VT[vt]["name"], "missing no_other_doctor note", says(r)))
        for x in check(r, slots, interpret(p)):
            problems.append((VT[vt]["name"], x))
    assert not problems, (len(problems), problems[:4])


def test_someone_else_twice_and_kept_through_other_changes(catalog, schedule):
    kind, vt = "returning-all", "appt_002"
    slots = slots_for(schedule, kind, vt)
    first = slots[0]
    card = _chosen_card(kind, vt, *first)
    card.turn_down_doctors(catalog, current=True)
    r = find_options(catalog, schedule, card.caller, vt, card.preferences, NOW)
    o = r.options[0]
    card.choices.provider_id, card.choices.location_id, card.choices.slot = o.provider_id, o.location_id, o.start
    card.turn_down_doctors(catalog, current=True)
    assert set(card.preferences.not_provider_ids) == {first[0], o.provider_id}
    card.change_choice("time", "Thursday")
    card.change_choice("location", "the Midtown one")
    assert set(card.preferences.not_provider_ids) == {first[0], o.provider_id}  # "for the rest of the call"
    r = find_options(catalog, schedule, card.caller, vt, card.preferences, NOW)
    assert r.options and not {x.provider_id for x in r.options} & {first[0], o.provider_id}
    card.change_choice("visit_type", "something else")
    assert card.preferences.not_provider_ids == []  # "Changing the visit type clears the list."


def test_someone_else_without_a_chosen_doctor_turns_nobody_down(catalog):
    card = BookingCard(caller=new_caller(), preferences=Preferences(doctor_name_heard="Dr. Daniel Chen"))
    card.choices = Choices(specialty="Dermatology", visit_type_id="appt_027")
    # Round 5: "current" with no chosen or carried-over doctor is refused and changes nothing
    # (a doctor who was only NAMED isn't "current").
    before = card.to_dict()
    with pytest.raises(ValueError):
        card.turn_down_doctors(catalog, current=True)
    assert card.to_dict() == before
    card.change_choice("doctor", "")   # "" now only means "no doctor wish"
    assert card.preferences.not_provider_ids == [] and card.preferences.doctor_name_heard == ""


def test_turned_down_doctor_asked_for_again_gets_a_true_note(catalog, schedule):
    """Caller turns Dr. Daniel Chen down, then asks for him by name. He stays turned down
    (spec), but any note about him must be true: he DOES have open times."""
    slots = slots_for(schedule, "new", "appt_027")
    chen = [s for s in slots if s[0] == "prov_001"]
    assert chen  # from the calendar: he has open times
    card = _chosen_card("new", "appt_027", *chen[0])
    card.turn_down_doctors(catalog, current=True)
    assert card.preferences.not_provider_ids == ["prov_001"]
    card.change_choice("doctor", "Dr. Daniel Chen")
    r = find_options(catalog, schedule, card.caller, "appt_027", card.preferences, NOW)
    false = [n.say for n in r.notes if "Daniel Chen" in n.say and "no open times" in n.say]
    assert not false, false


def test_who_can_list_leaves_out_turned_down_doctors(catalog, schedule):
    """'They aren't offered again': a 'Doctors who can' list naming them would offer them."""
    slots = slots_for(schedule, "new", "appt_027")
    first = slots[0]
    card = _chosen_card("new", "appt_027", *first)
    card.turn_down_doctors(catalog, current=True)
    card.change_choice("doctor", "Dr. Garcia")  # no Garcia does skin screening -> 'Doctors who can' note
    r = find_options(catalog, schedule, card.caller, "appt_027", card.preferences, NOW)
    for n in r.notes:
        assert PROV[first[0]]["name"] not in _who_can_names(n.say), n.say


@pytest.mark.parametrize("value", ["any", "anyone", "no preference", "Any", "Anyone", "No preference", "  anyone "])
def test_any_doctor_means_no_doctor_wish(catalog, schedule, value):
    base = find_options(catalog, schedule, new_caller(), "appt_027", Preferences(), NOW)
    r = find_options(catalog, schedule, new_caller(), "appt_027", Preferences(doctor_name_heard=value), NOW)
    assert not r.notes, says(r)
    assert [(o.provider_id, o.location_id, o.start) for o in r.options] == \
           [(o.provider_id, o.location_id, o.start) for o in base.options]
    card = _chosen_card("new", "appt_027", *slots_for(schedule, "new", "appt_027")[0])
    card.change_choice("doctor", value)
    r = find_options(catalog, schedule, card.caller, "appt_027", card.preferences, NOW)
    assert not [n for n in r.notes if n.kind.startswith("doctor")], says(r)


# ---------------------------------------------------------------- time changes through change_choice
def _card(days=(), tod=""):
    card = BookingCard(caller=new_caller(), preferences=Preferences(days=list(days), time_of_day=tod))
    card.choices = Choices(specialty="Dermatology", visit_type_id="appt_027")
    return card


# Round 6 s1: the AI fills plain fields; the spoken phrase each case stood for is in the comment.
@pytest.mark.parametrize("kwargs,start,want", [
    (dict(days=["Thursday"], time_of_day="morning"), ([], ""), (["Thursday"], "morning")),   # "Thursday morning"
    (dict(days=["thursday"], time_of_day="afternoon"), (["Monday"], "morning"), (["thursday"], "afternoon")),
    (dict(time_of_day="afternoon"), (["Thursday"], "morning"), (["Thursday"], "afternoon")),  # keeps Thursday
    (dict(time_of_day="morning"), (["Friday"], ""), (["Friday"], "morning")),
    (dict(new_value="Thursday"), ([], "morning"), (["Thursday"], "morning")),                # keeps the morning
    (dict(days=[]), (["Thursday"], "morning"), ([], "morning")),                             # "any day"
    (dict(new_value="Any day"), (["Thursday"], "afternoon"), ([], "afternoon")),             # s2: a no-preference entry
    (dict(days=[], time_of_day=""), (["Thursday"], "morning"), ([], "")),                    # "any time"
    (dict(days=["Any time"], time_of_day="any time"), (["Thursday"], "afternoon"), ([], "")),
    (dict(days=["tomorrow"], time_of_day="morning"), ([], ""), (["tomorrow"], "morning")),
    (dict(days=["today"], time_of_day="afternoon"), ([], ""), (["today"], "afternoon")),     # "this afternoon"
])
def test_time_change_only_what_is_mentioned_changes(kwargs, start, want):
    card = _card(*start)
    assert card.change_choice("time", **kwargs) == BOOKING
    p = card.preferences
    got = ([d for d in p.days], p.time_of_day)
    assert (got[0] if got[0] else [], got[1] or "") == (want[0], want[1]), (kwargs, got)
    assert p.latest == "time"


def test_time_change_arguments_still_work():
    card = _card(["Monday"], "morning")
    card.change_choice("time", days=["Friday"])
    assert card.preferences.days == ["Friday"] and card.preferences.time_of_day == "morning"
    card.change_choice("time", time_of_day="afternoon")
    assert card.preferences.days == ["Friday"] and card.preferences.time_of_day == "afternoon"


@pytest.mark.parametrize("value", [dict(days=["Thursday"], time_of_day="morning"), dict(time_of_day="afternoon"),
                                   dict(new_value="Tuesday"), dict(days=[], time_of_day=""),
                                   dict(days=["tomorrow"], time_of_day="afternoon")])
def test_time_change_then_options_honour_it_whole_catalog(catalog, schedule, value):
    """After change_choice('time', value) from a chosen option, every visit type: options meet
    the new day/time when anyone can, and the carried doctor/place follow the model."""
    kind = "returning-all"
    problems = []
    for vt in bookable_vts(kind):
        slots = slots_for(schedule, kind, vt)
        if not slots:
            continue
        pid, lid, start = slots[0]
        card = _chosen_card(kind, vt, pid, lid, start)
        card.preferences.days, card.preferences.time_of_day = ["Wednesday"], "morning"
        card.change_choice("time", **value)   # round 6 s1: plain fields
        p = card.preferences
        r = find_options(catalog, schedule, card.caller, vt, p, NOW)
        if "bad_input" in [n.kind for n in r.notes]:
            problems.append((VT[vt]["name"], "bad_input", says(r)))
            continue
        problems += [(VT[vt]["name"], x) for x in check(r, slots, interpret(p))]
    assert not problems, (len(problems), problems[:4])


def test_someone_else_after_a_time_change_does_not_offer_the_same_doctor(catalog, schedule):
    """Realistic flow: caller picks Dr. Daniel Chen, asks for Thursday instead (the doctor is
    now a carried-over wish), hears Dr. Chen's Thursday times, then says 'someone else, please'.
    Spec s4: 'They aren't offered again.' Literal spec text only covers a doctor who is
    *chosen*, so this may be a spec gap rather than a code bug."""
    slots = slots_for(schedule, "new", "appt_027")
    first = next(s for s in slots if s[0] == "prov_001")
    card = _chosen_card("new", "appt_027", *first)
    card.change_choice("time", "Thursday")
    card.turn_down_doctors(catalog, current=True)   # round 5: "current" covers a carried-over doctor
    r = find_options(catalog, schedule, card.caller, "appt_027", card.preferences, NOW)
    others = {s[0] for s in slots if s[2].strftime("%A") == "Thursday"} - {"prov_001"}
    assert others
    assert not any(o.provider_id == "prov_001" for o in r.options), [o.spoken for o in r.options]
