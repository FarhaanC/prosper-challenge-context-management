"""Round 5 (spec-changes-round-5.md), sections 1-3: turning doctors down is its own clear
instruction, change_choice never reads instructions from words, and naming a
turned-down doctor again.

Expected answers come from the spec text and catalog.json (reference.py). The module's
fake calendar is used only as the source of open times, as in earlier rounds.
"""

from collections import Counter
from dataclasses import replace

import pytest

from clinic import BOOKING, VISIT_TYPE, BookingCard, Choices, Preferences, find_options
from conftest import NOW, new_caller, returning
from reference import PROV, SPECIALTIES, VT, ref_bookable, ref_pairs

SKIN = "appt_027"          # Skin Cancer Screening: new patients allowed, several doctors
NEW_CONSULT = "appt_000"   # New Patient Consultation: both Dr. Michael Satos and both Dr. Maria Garcias offer it
CALLERS = {"new": (True, []), "returning-all": (False, list(SPECIALTIES))}
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


def card_for(kind, vt, **prefs):
    card = BookingCard(caller=caller(kind), preferences=Preferences(**prefs))
    card.choices = Choices(specialty=VT[vt]["specialty"], visit_type_id=vt)
    return card


def search(catalog, schedule, card):
    r = find_options(catalog, schedule, card.caller, card.choices.visit_type_id, card.preferences, NOW,
                     first_option_number=card.next_option_number)
    card.remember_offer(r.options)
    return r


def choose(card, option):
    card.choices.provider_id, card.choices.location_id, card.choices.slot = (
        option.provider_id, option.location_id, option.start)


def ids_named(name):
    return sorted(p for p, x in PROV.items() if x["name"] == name)


def ids_with_surname(surname):
    return sorted(p for p, x in PROV.items() if x["name"].split()[-1] == surname)


def says(r, kind=None):
    return [n.say for n in r.notes if kind is None or n.kind == kind]


def not_list(summary):
    """The names after 'not: ' in the card summary ('' if none)."""
    if "not: " not in summary:
        return ""
    return summary.split("not: ", 1)[1].split("\n")[0].split(";")[0]


# ---------------------------------------------------------------- s1: every instruction form and mix
def _offer_and_choose(catalog, schedule):
    """A skin-check call: options on offer, the first one chosen. Returns card, chosen option, offered doctors."""
    card = card_for("new", SKIN)
    r = search(catalog, schedule, card)
    assert len({o.provider_id for o in r.options}) >= 2  # the cases below need a real choice
    choose(card, r.options[0])
    return card, r.options[0], sorted({o.provider_id for o in r.options})


@pytest.mark.parametrize("form", ["ids", "ids-not-on-offer", "on_offer", "current", "ids+on_offer",
                                  "ids+current", "on_offer+current", "all-three", "duplicate-ids"])
def test_every_instruction_form_and_mix(catalog, schedule, form):
    card, chosen, on_offer = _offer_and_choose(catalog, schedule)
    outsider = next(p for p in sorted(PROV) if p not in on_offer)          # a doctor not on offer
    other = next(p for p in on_offer if p != chosen.provider_id)          # on offer, not chosen
    instruction, want = {
        "ids": ({"provider_ids": [other]}, {other}),
        "ids-not-on-offer": ({"provider_ids": [outsider]}, {outsider}),
        "on_offer": ({"on_offer": True}, set(on_offer)),
        "current": ({"current": True}, {chosen.provider_id}),
        "ids+on_offer": ({"provider_ids": [outsider], "on_offer": True}, set(on_offer) | {outsider}),
        "ids+current": ({"provider_ids": [outsider], "current": True}, {outsider, chosen.provider_id}),
        "on_offer+current": ({"on_offer": True, "current": True}, set(on_offer)),
        "all-three": ({"provider_ids": [outsider], "on_offer": True, "current": True}, set(on_offer) | {outsider}),
        "duplicate-ids": ({"provider_ids": [other, other, f" {other} "]}, {other}),
    }[form]
    assert card.turn_down_doctors(catalog, **instruction) == BOOKING
    p, c = card.preferences, card.choices
    assert set(p.not_provider_ids) == want and len(p.not_provider_ids) == len(want)
    # "It counts as a doctor change": clears doctor, place and time, carries the place over,
    # clears any doctor wish, and marks the doctor as the latest change.
    assert (c.provider_id, c.location_id, c.slot) == ("", "", None)
    assert p.preferred_location_id == chosen.location_id
    assert p.doctor_name_heard == "" and p.preferred_provider_id == ""
    assert p.latest == "doctor"
    assert c.visit_type_id == SKIN  # the visit type is not touched
    r = search(catalog, schedule, card)
    others = {s[0] for s in slots(schedule, "new", SKIN)} - want
    if others:
        assert r.options and not {o.provider_id for o in r.options} & want
        assert "no_other_doctor" not in [n.kind for n in r.notes]


def test_turning_down_adds_to_the_list(catalog, schedule):
    card, chosen, on_offer = _offer_and_choose(catalog, schedule)
    card.turn_down_doctors(catalog, current=True)
    nxt = search(catalog, schedule, card)
    choose(card, nxt.options[0])
    card.turn_down_doctors(catalog, current=True)
    assert set(card.preferences.not_provider_ids) == {chosen.provider_id, nxt.options[0].provider_id}


def test_a_said_place_is_kept_and_a_carried_place_stays(catalog):
    card = card_for("new", SKIN, location_hint="the Midtown one")
    card.turn_down_doctors(catalog, provider_ids=[ids_named("Dr. Kenji Kim")[0]])
    assert card.preferences.location_hint == "the Midtown one"
    card = card_for("new", SKIN, preferred_location_id="loc_004", preferred_provider_id="prov_001")
    card.turn_down_doctors(catalog, current=True)   # the carried-over doctor
    p = card.preferences
    assert p.preferred_location_id == "loc_004" and p.not_provider_ids == ["prov_001"] and p.preferred_provider_id == ""


def test_without_a_visit_type_the_stage_is_visit_type(catalog):
    card = BookingCard(caller=new_caller())
    assert card.turn_down_doctors(catalog, provider_ids=["prov_001"]) == VISIT_TYPE
    assert card.preferences.not_provider_ids == ["prov_001"]


# ---------------------------------------------------------------- s1: refusals change nothing
REFUSALS = {
    "nothing given": {},
    "empty id list": {"provider_ids": []},
    "blank ids": {"provider_ids": ["", "   "]},
    "current with no chosen or carried doctor": {"current": True},
    "on_offer with nothing on offer": {"on_offer": True},
    "unknown id": {"provider_ids": ["prov_999"]},
    "a known id mixed with an unknown one": {"provider_ids": ["prov_001", "prov_999"]},
    "a visit type id": {"provider_ids": [SKIN]},
    "a location id": {"provider_ids": ["loc_000"]},
    "a doctor's name instead of an id": {"provider_ids": ["Dr. Daniel Chen"]},
}


@pytest.mark.parametrize("label", list(REFUSALS))
def test_an_instruction_that_cannot_be_followed_is_refused_and_changes_nothing(catalog, label):
    # A doctor was only NAMED (not chosen or carried), and nothing is on offer.
    card = card_for("new", SKIN, doctor_name_heard="Dr. Daniel Chen", location_hint="near Union Square",
                    days=["Thursday"], language="Arabic", not_provider_ids=["prov_027"], latest="time")
    before = card.to_dict()
    with pytest.raises(ValueError) as e:
        card.turn_down_doctors(catalog, **REFUSALS[label])
    assert str(e.value).strip()  # a plain message
    assert card.to_dict() == before


@pytest.mark.parametrize("instruction", [{"on_offer": True, "current": True},
                                         {"provider_ids": ["prov_001"], "current": True}])
def test_a_mix_with_one_impossible_part_is_refused_whole(catalog, schedule, instruction):
    card = card_for("new", SKIN)
    search(catalog, schedule, card)   # options on offer, nothing chosen or carried
    before = card.to_dict()
    with pytest.raises(ValueError):
        card.turn_down_doctors(catalog, **instruction)
    assert card.to_dict() == before


def test_the_nothing_given_message_says_how(catalog):
    with pytest.raises(ValueError, match="Say which doctors to turn down"):
        card_for("new", SKIN).turn_down_doctors(catalog)


# ---------------------------------------------------------------- s1: the search leaves them out, whole catalog
@pytest.mark.parametrize("kind", list(CALLERS))
def test_turning_down_everyone_on_offer_whole_catalog(catalog, schedule, kind):
    problems = []
    for vt in bookable(kind):
        able = {s[0] for s in slots(schedule, kind, vt)}
        if not able:
            continue
        card = card_for(kind, vt)
        r = search(catalog, schedule, card)
        on_offer = {o.provider_id for o in r.options}
        card.turn_down_doctors(catalog, on_offer=True)
        r2 = search(catalog, schedule, card)
        got = {o.provider_id for o in r2.options}
        if able - on_offer:
            if not r2.options or got & on_offer or "no_other_doctor" in [n.kind for n in r2.notes]:
                problems.append((VT[vt]["name"], "turned-down doctor offered or false note", says(r2)))
        else:
            if not r2.options or [n.kind for n in r2.notes].count("no_other_doctor") != 1:
                problems.append((VT[vt]["name"], "expected one no_other_doctor note and options", says(r2)))
    assert not problems, (len(problems), problems[:4])


# ---------------------------------------------------------------- s2: change_choice never reads instructions
PHRASES = ["someone else", "somebody else", "a different doctor", "another doctor", "anyone else", "other doctor",
           "Someone else, please", "not Dr. Chen", "No, not Dr. Chen", "anyone but Dr. Chen", "not him",
           "the other one", "a different one"]


@pytest.mark.parametrize("phrase", PHRASES + [""])
def test_change_choice_doctor_never_turns_anyone_down(catalog, schedule, phrase):
    card, chosen, _ = _offer_and_choose(catalog, schedule)
    card.preferences.not_provider_ids = ["prov_027"]   # turned down earlier in the call
    assert card.change_choice("doctor", phrase) == BOOKING
    assert card.preferences.not_provider_ids == ["prov_027"]
    assert chosen.provider_id not in card.preferences.not_provider_ids or chosen.provider_id == "prov_027"


@pytest.mark.parametrize("vt", [SKIN, NEW_CONSULT])
@pytest.mark.parametrize("phrase", PHRASES)
def test_words_passed_as_a_name_give_a_visible_not_found_note_and_no_guess(catalog, schedule, vt, phrase):
    # Spec s2: they "are treated as a name, which matches nobody, so the agent gets a
    # doctor_not_found note (the mistake is visible, not guessed at)".
    card = card_for("returning-all", vt)
    choose(card, search(catalog, schedule, card).options[0])
    card.change_choice("doctor", phrase)
    r = search(catalog, schedule, card)
    without = find_options(catalog, schedule, card.caller, vt, replace(card.preferences, doctor_name_heard=""), NOW)
    assert "doctor_not_found" in [n.kind for n in r.notes], (phrase, says(r))
    assert [(o.provider_id, o.start) for o in r.options] == [(o.provider_id, o.start) for o in without.options], \
        (phrase, [o.spoken for o in r.options], says(r))


def test_empty_doctor_value_means_no_doctor_wish(catalog, schedule):
    card, chosen, _ = _offer_and_choose(catalog, schedule)
    card.change_choice("doctor", "")
    assert card.preferences.not_provider_ids == [] and card.preferences.doctor_name_heard == ""
    r = search(catalog, schedule, card)
    assert not [n for n in r.notes if n.kind.startswith("doctor")]


# ---------------------------------------------------------------- s3: naming a turned-down doctor again
@pytest.mark.parametrize("named", ["Dr. Daniel Chen", "Daniel Chen", "Dr. Daniel Chen's", "dr. daniel chen",
                                   "  Dr.   Daniel  Chen  "])
def test_a_full_name_brings_that_doctor_back(catalog, schedule, named):
    chen = ids_named("Dr. Daniel Chen")[0]
    card = card_for("new", SKIN)
    card.turn_down_doctors(catalog, provider_ids=[chen])
    card.change_choice("doctor", named)
    r = search(catalog, schedule, card)
    assert r.options and {o.provider_id for o in r.options} == {chen}
    assert not [n for n in r.notes if n.kind in ("wish_conflict", "wish_impossible", "no_other_doctor")], says(r)
    assert "Dr. Daniel Chen" not in not_list(card.summary(catalog))


def test_a_surname_fitting_several_doctors_does_not_bring_one_back(catalog, schedule):
    chen = ids_named("Dr. Daniel Chen")[0]
    card = card_for("new", SKIN)
    card.turn_down_doctors(catalog, provider_ids=[chen])
    card.change_choice("doctor", "Dr. Chen")   # seven doctors are called Chen (catalog.json)
    assert len(ids_with_surname("Chen")) == 7
    r = search(catalog, schedule, card)
    assert r.options and chen not in {o.provider_id for o in r.options}
    assert says(r, "wish_conflict") == [
        "The only doctor matching 'Dr. Chen' who can do this is Dr. Daniel Chen, whom you turned down. "
        "Check whether the caller wants that doctor after all."]
    assert "Dr. Daniel Chen" in not_list(card.summary(catalog))


def test_a_surname_that_fits_exactly_one_doctor_brings_them_back(catalog, schedule):
    # "only if the name picks out that one doctor": a surname nobody else has does.
    counts = Counter(x["name"].split()[-1] for x in PROV.values())
    found = 0
    for kind in CALLERS:
        for vt in bookable(kind):
            able = sorted({s[0] for s in slots(schedule, kind, vt)})
            unique = [p for p in able if counts[PROV[p]["name"].split()[-1]] == 1]
            if len(able) < 2 or not unique:
                continue
            pid = unique[0]
            card = card_for(kind, vt)
            card.turn_down_doctors(catalog, provider_ids=[pid])
            card.change_choice("doctor", "Dr. " + PROV[pid]["name"].split()[-1])
            r = search(catalog, schedule, card)
            assert r.options and {o.provider_id for o in r.options} == {pid}, (VT[vt]["name"], says(r))
            found += 1
            break
    assert found


@pytest.mark.parametrize("name", ["Dr. Michael Sato", "Dr. Maria Garcia"])
def test_two_doctors_with_the_same_full_name_count_as_one_name(catalog, schedule, name):
    pair = ids_named(name)
    assert len(pair) == 2 and all(NEW_CONSULT in PROV[p]["appointment_type_ids"] for p in pair)
    able = {s[0] for s in slots(schedule, "returning-all", NEW_CONSULT)}
    assert set(pair) <= able
    for down in ([pair[0]], [pair[1]], pair):
        card = card_for("returning-all", NEW_CONSULT)
        card.turn_down_doctors(catalog, provider_ids=down)
        card.change_choice("doctor", name)
        r = search(catalog, schedule, card)
        assert r.options and {o.provider_id for o in r.options} <= set(pair), (down, [o.spoken for o in r.options])
        assert set(pair) == {o.provider_id for o in find_options(
            catalog, schedule, card.caller, NEW_CONSULT, card.preferences, NOW, limit=20).options}, down
        assert not [s for s in says(r) if "turned down" in s or "only option" in s], says(r)
        assert name not in not_list(card.summary(catalog))


def test_same_name_pair_turned_down_and_the_surname_said(catalog, schedule):
    pair = ids_named("Dr. Michael Sato")
    card = card_for("returning-all", NEW_CONSULT)
    card.turn_down_doctors(catalog, provider_ids=pair)
    card.change_choice("doctor", "Dr. Sato")   # fits Omar Sato too, who wasn't turned down
    r = search(catalog, schedule, card)
    assert r.options and {o.provider_name for o in r.options} == {"Dr. Omar Sato"}
    assert not [s for s in says(r) if "turned down" in s]
    assert "Dr. Michael Sato" in not_list(card.summary(catalog))


@pytest.mark.parametrize("change", [("time", "Thursday"), ("time", "afternoon"), ("location", "the Richmond one"),
                                    ("location", "near Union Square"), ("language", "Arabic"), ("time", "any time")])
def test_named_back_then_chosen_stays_back_after_any_other_change(catalog, schedule, change):
    chen = ids_named("Dr. Daniel Chen")[0]
    card = card_for("new", SKIN)
    card.turn_down_doctors(catalog, provider_ids=[chen])
    card.change_choice("doctor", "Dr. Daniel Chen")
    choose(card, search(catalog, schedule, card).options[0])
    card.change_choice(*change)
    card.change_choice("time", "Friday") if change[0] != "time" else None   # and one more change for good measure
    r = search(catalog, schedule, card)
    assert chen not in card.preferences.not_provider_ids
    assert not_list(card.summary(catalog)) == ""
    assert not [s for s in says(r) if "turned down" in s or "only option" in s], says(r)
    can = find_options(catalog, schedule, card.caller, SKIN, replace(card.preferences, not_provider_ids=[]), NOW)
    assert [(o.provider_id, o.start) for o in r.options] == [(o.provider_id, o.start) for o in can.options]


def test_one_of_a_same_name_pair_named_back_and_chosen_stays_back(catalog, schedule):
    pair = ids_named("Dr. Michael Sato")
    card = card_for("returning-all", NEW_CONSULT)
    card.turn_down_doctors(catalog, provider_ids=pair)
    card.change_choice("doctor", "Dr. Michael Sato")
    r = search(catalog, schedule, card)
    pick = r.options[0]
    choose(card, pick)
    card.change_choice("time", "Thursday")
    assert pick.provider_id not in card.preferences.not_provider_ids
    r2 = search(catalog, schedule, card)
    assert not [s for s in says(r2) if "turned down" in s]


# ---------------------------------------------------------------- s1: picking one from a no_other_doctor offer
def _everyone_turned_down(catalog, schedule, kind, vt):
    able = sorted({s[0] for s in slots(schedule, kind, vt)})
    card = card_for(kind, vt)
    card.turn_down_doctors(catalog, provider_ids=able)
    r = search(catalog, schedule, card)
    return card, r, able


@pytest.mark.parametrize("kind", list(CALLERS))
def test_picking_from_a_no_other_doctor_offer_then_changing_the_day_whole_catalog(catalog, schedule, kind):
    problems = []
    for vt in bookable(kind):
        if not slots(schedule, kind, vt):
            continue
        card, r, able = _everyone_turned_down(catalog, schedule, kind, vt)
        if [n.kind for n in r.notes] != ["no_other_doctor"] or not r.options:
            problems.append((VT[vt]["name"], "expected one no_other_doctor note", says(r)))
            continue
        pick = r.options[0]
        choose(card, pick)
        card.change_choice("time", "any time")
        if pick.provider_id in card.preferences.not_provider_ids:
            problems.append((VT[vt]["name"], "picked doctor still turned down"))
        if PROV[pick.provider_id]["name"] in not_list(card.summary(catalog)) and \
                len(ids_named(PROV[pick.provider_id]["name"])) == 1:
            problems.append((VT[vt]["name"], "summary still lists the picked doctor", card.summary(catalog)))
        r2 = search(catalog, schedule, card)
        if pick.provider_id not in {o.provider_id for o in r2.options} and r2.options:
            # the carried-over doctor must be honoured again (they have open times: they were just offered)
            problems.append((VT[vt]["name"], "picked doctor not offered after the change", says(r2)))
    assert not problems, (len(problems), problems[:4])


def test_picked_doctor_is_not_called_turned_down_in_the_summary_right_after_choosing(catalog, schedule):
    # s1: "once chosen, that doctor is off the list for good"; s4: "not: ..." lists the
    # doctors STILL turned down. The summary is pasted into the AI's instructions.
    card, r, able = _everyone_turned_down(catalog, schedule, "new", SKIN)
    choose(card, r.options[0])
    summary = card.summary(catalog)
    assert r.options[0].provider_name not in not_list(summary), summary


def test_picked_doctor_stays_off_the_list_after_a_later_doctor_change(catalog, schedule):
    # s1: "once chosen, that doctor is off the list for good, even after later changes."
    card, r, able = _everyone_turned_down(catalog, schedule, "new", SKIN)
    pick = r.options[0]
    choose(card, pick)
    card.change_choice("doctor", "")   # "any doctor is fine, actually"
    assert pick.provider_id not in card.preferences.not_provider_ids, card.preferences.not_provider_ids
