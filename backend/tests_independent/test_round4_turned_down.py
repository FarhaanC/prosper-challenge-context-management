"""Round 4 (spec-changes-round-4.md): "someone else" in all its forms, naming a
turned-down doctor again (change 4), and the "whom you turned down" note (change 1),
checked against the whole catalog.

Updated for round 5 (spec-changes-round-5.md): turning doctors down is now the clear
instruction BookingCard.turn_down_doctors; change_choice("doctor", ...) only ever takes
a name. Each test keeps its round-4 intent but makes the call the AI would make.

Expected answers come from the spec and catalog.json (reference.py). The module's
calendar is used only as the source of open times, as in earlier rounds.
"""

import re
from dataclasses import replace

import pytest

from clinic import BOOKING, BookingCard, Choices, Preferences, find_options
from conftest import NOW, new_caller, returning
from reference import LOC, PROV, SPECIALTIES, VT, ref_bookable, ref_pairs

CALLERS = {"new": (True, []), "returning-all": (False, list(SPECIALTIES))}
SKIN = "appt_027"  # Skin Cancer Screening (Dermatology), new patients allowed, no referral
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


def pid_named(name):
    (pid,) = [p for p, x in PROV.items() if x["name"] == name]
    return pid


def card_for(kind, vt):
    card = BookingCard(caller=caller(kind))
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


# The skin-check doctors for a new caller, from catalog.json.
def skin_doctors(schedule):
    return sorted({s[0] for s in slots(schedule, "new", SKIN)})


def test_skin_check_has_several_doctors(schedule):
    assert len(skin_doctors(schedule)) >= 3  # the scenarios below need a real choice


# ---------------------------------------------------------------- "someone else", three contexts
# Round 5 (spec-changes-round-5.md s1-s2): the code no longer reads phrases. For "someone
# else" the AI calls turn_down_doctors with exactly who: current=True (the chosen doctor,
# or else the carried-over one), on_offer=True (every doctor in the options on offer), or
# provider_ids. These tests keep the round-4 intent but make the call the AI would make.
CHOSEN_FORMS = ["current", "ids", "ids-with-spaces", "current+ids"]


def _instruction(form, pid):
    return {"current": {"current": True}, "ids": {"provider_ids": [pid]},
            "ids-with-spaces": {"provider_ids": [f"  {pid} "]},
            "current+ids": {"current": True, "provider_ids": [pid]}}[form]


@pytest.mark.parametrize("form", CHOSEN_FORMS)
def test_someone_else_turns_down_the_chosen_doctor(catalog, schedule, form):
    card = card_for("new", SKIN)
    r = search(catalog, schedule, card)
    choose(card, r.options[0])
    chosen = r.options[0].provider_id
    assert card.turn_down_doctors(catalog, **_instruction(form, chosen)) == BOOKING
    assert card.preferences.not_provider_ids == [chosen]
    r2 = search(catalog, schedule, card)
    assert r2.options and all(o.provider_id != chosen for o in r2.options)
    assert not [n for n in r2.notes if n.kind in ("doctor_not_found", "doctor_name_guess", "no_other_doctor")]
    assert "not: " + PROV[chosen]["name"] in card.summary(catalog)


@pytest.mark.parametrize("form", ["current", "ids"])
def test_someone_else_turns_down_the_carried_over_doctor(catalog, schedule, form):
    card = card_for("new", SKIN)
    r = search(catalog, schedule, card)
    choose(card, r.options[0])
    chosen = r.options[0].provider_id
    card.change_choice("time", "Thursday")      # the doctor is now only carried over
    assert card.preferences.preferred_provider_id == chosen
    search(catalog, schedule, card)             # Thursday options are on offer
    card.turn_down_doctors(catalog, **_instruction(form, chosen))
    # current means the carried-over doctor, not every doctor on offer
    assert card.preferences.not_provider_ids == [chosen]
    r3 = search(catalog, schedule, card)
    assert r3.options and all(o.provider_id != chosen for o in r3.options)
    assert all(o.start.strftime("%A") == "Thursday" for o in r3.options)  # the day wish survives


def test_someone_else_during_an_offer_turns_down_everyone_on_offer(catalog, schedule):
    card = card_for("new", SKIN)
    r = search(catalog, schedule, card)         # nothing chosen, nothing carried
    on_offer = sorted({o.provider_id for o in r.options})
    card.turn_down_doctors(catalog, on_offer=True)
    assert card.preferences.not_provider_ids == on_offer
    r2 = search(catalog, schedule, card)
    left = set(skin_doctors(schedule)) - set(on_offer)
    if left:
        assert r2.options and {o.provider_id for o in r2.options} <= left
    else:
        assert [n.kind for n in r2.notes].count("no_other_doctor") == 1


def test_someone_else_during_an_offer_of_one_named_doctor(catalog, schedule):
    card = card_for("new", SKIN)
    card.preferences.doctor_name_heard = "Dr. Daniel Chen"
    r = search(catalog, schedule, card)
    assert {o.provider_name for o in r.options} == {"Dr. Daniel Chen"}
    card.turn_down_doctors(catalog, on_offer=True)
    assert card.preferences.doctor_name_heard == ""   # "clears any doctor wish"
    r2 = search(catalog, schedule, card)
    assert r2.options and "Dr. Daniel Chen" not in {o.provider_name for o in r2.options}


# Round 4 tested that filler words still turned the doctor down. Round 5 reverses that on
# purpose: the words are only ever a name. The intent that survives: the mistake must be
# VISIBLE (a doctor_not_found note), nobody is turned down, and nothing is guessed.
@pytest.mark.parametrize("phrase", ["Someone else, please", "someone else please", "the other doctor",
                                    "Another doctor, please"])
def test_someone_else_with_ordinary_filler_words(catalog, schedule, phrase):
    card = card_for("new", SKIN)
    r = search(catalog, schedule, card)
    choose(card, r.options[0])
    card.change_choice("doctor", phrase)
    r2 = search(catalog, schedule, card)
    # the same card without the doctor words (the chosen place is still carried over)
    base = find_options(catalog, schedule, new_caller(), SKIN, replace(card.preferences, doctor_name_heard=""), NOW)
    assert card.preferences.not_provider_ids == []
    assert [n.kind for n in r2.notes] == ["doctor_not_found"], [n.say for n in r2.notes]
    assert [(o.provider_id, o.start) for o in r2.options] == [(o.provider_id, o.start) for o in base.options]


def test_not_dr_name_turns_down_every_match(catalog, schedule):
    # "not Dr. Chen": the tool layer turns the name into ids and passes them all.
    card = card_for("new", SKIN)
    chens = sorted(p for p, x in PROV.items() if x["name"].split()[-1] == "Chen")
    card.turn_down_doctors(catalog, provider_ids=chens)
    r = search(catalog, schedule, card)
    assert r.options and not {o.provider_id for o in r.options} & set(chens)
    # round 5 s4: "not: ..." lists the doctors still turned down, by full name, sorted
    assert "not: " + ", ".join(sorted(PROV[c]["name"] for c in chens)) in card.summary(catalog)


@pytest.mark.parametrize("phrase", ["No, not Dr. Chen", "anyone but Dr. Chen", "not Dr. Chen"])
def test_a_negated_name_never_becomes_a_wish_for_that_doctor(catalog, schedule, phrase):
    # Round 5 s2: if the AI wrongly passes these words to change_choice, they are "treated
    # as a name, which matches nobody, so the agent gets a doctor_not_found note". The
    # opposite must never happen: offering ONLY the doctor the caller just refused.
    card = card_for("new", SKIN)
    card.change_choice("doctor", phrase)
    r = search(catalog, schedule, card)
    names = {o.provider_name for o in r.options}
    assert names != {"Dr. Daniel Chen"}, (phrase, names, [n.say for n in r.notes])
    assert "doctor_not_found" in [n.kind for n in r.notes], [n.say for n in r.notes]


def test_visit_type_change_forgets_turned_down_doctors(catalog, schedule):
    card = card_for("new", SKIN)
    search(catalog, schedule, card)
    card.turn_down_doctors(catalog, on_offer=True)
    kims = [p for p, x in PROV.items() if x["name"].endswith(" Kim")]
    card.turn_down_doctors(catalog, provider_ids=kims)
    assert set(kims) <= set(card.preferences.not_provider_ids)
    card.change_choice("visit_type", "a mole check")
    assert card.preferences.not_provider_ids == []
    assert not hasattr(card.preferences, "not_doctor_names")   # round 5 s2: removed


# ---------------------------------------------------------------- naming them again (round 5 s3)
@pytest.mark.parametrize("named", ["Dr. Daniel Chen", "Daniel Chen", "Dr. Daniel Chen's"])
def test_naming_a_turned_down_doctor_again_brings_them_back(catalog, schedule, named):
    card = card_for("new", SKIN)
    card.preferences.doctor_name_heard = "Dr. Daniel Chen"
    r = search(catalog, schedule, card)
    choose(card, r.options[0])
    card.turn_down_doctors(catalog, current=True)
    assert card.preferences.not_provider_ids == [pid_named("Dr. Daniel Chen")]
    search(catalog, schedule, card)
    card.change_choice("doctor", named)        # "actually, Dr. Chen is fine"
    r3 = search(catalog, schedule, card)
    assert r3.options and {o.provider_name for o in r3.options} == {"Dr. Daniel Chen"}
    bad = [n.say for n in r3.notes if n.kind in ("wish_impossible", "wish_conflict", "no_other_doctor", "no_times")]
    assert not bad, bad


def test_a_doctor_named_back_stays_back_after_another_change(catalog, schedule):
    # turn down -> "actually Dr. Daniel Chen is fine" -> choose his option -> "Thursday instead?"
    card = card_for("new", SKIN)
    card.preferences.doctor_name_heard = "Dr. Daniel Chen"
    choose(card, search(catalog, schedule, card).options[0])
    card.turn_down_doctors(catalog, current=True)
    search(catalog, schedule, card)
    card.change_choice("doctor", "Dr. Daniel Chen")
    choose(card, search(catalog, schedule, card).options[0])
    card.change_choice("time", "Thursday")
    r = search(catalog, schedule, card)
    chen = pid_named("Dr. Daniel Chen")
    has_thursday = any(s[0] == chen and s[2].strftime("%A") == "Thursday" for s in slots(schedule, "new", SKIN))
    says = [n.say for n in r.notes]
    assert not any("turned down" in s for s in says), says
    assert "not:" not in card.summary(catalog)
    if has_thursday:
        assert any(o.provider_id == chen for o in r.options), ([o.spoken for o in r.options], says)


def test_carried_over_doctor_does_not_override_a_turn_down(catalog, schedule):
    kim = pid_named("Dr. Kenji Kim")
    r = find_options(catalog, schedule, new_caller(), SKIN,
                     Preferences(preferred_provider_id=kim, not_provider_ids=[kim]), NOW)
    assert r.options and all(o.provider_id != kim for o in r.options)


def test_naming_one_of_several_turned_down_doctors_brings_only_that_doctor_back(catalog, schedule):
    # Round 4 used the removed not_doctor_names=["Dr. Chen"]; round 5: all Chens turned down
    # by id, then the caller names one Chen in full.
    chens = sorted(p for p, x in PROV.items() if x["name"].split()[-1] == "Chen")
    p = Preferences(not_provider_ids=chens, doctor_name_heard="Dr. Daniel Chen")
    r = find_options(catalog, schedule, new_caller(), SKIN, p, NOW)
    assert r.options and {o.provider_name for o in r.options} == {"Dr. Daniel Chen"}
    assert not [n for n in r.notes if "turned down" in n.say or n.kind == "wish_impossible"]
    card = card_for("new", SKIN)
    card.preferences = p
    summary = card.summary(catalog)
    others = sorted(PROV[c]["name"] for c in chens if PROV[c]["name"] != "Dr. Daniel Chen")
    assert "not: " + ", ".join(others) in summary and "Dr. Daniel Chen, " not in summary.split("not: ")[1]


# ---------------------------------------------------------------- change 1: the note, whole catalog
NOTE = re.compile(r"^(?P<label>.+) is only possible with (?P<names>.+), whom you turned down\.$")


def _named_in(say):
    return {x["name"] for x in PROV.values() if x["name"] in say}


def _turn_down_cases(schedule, kind, vt):
    docs = sorted({s[0] for s in slots(schedule, kind, vt)})
    return [{d} for d in docs] + ([set(docs[:2]), set(docs[:3])] if len(docs) > 2 else [])


def _check_turned_down_note(catalog, schedule, kind, vt, down, prefs, fits, label):
    """`fits(slot)` says whether one valid slot meets the wish on its own."""
    all_slots = slots(schedule, kind, vt)
    others = [s for s in all_slots if s[0] not in down]
    if not others:
        return []
    prefs.not_provider_ids = sorted(down)
    r = find_options(catalog, schedule, caller(kind), vt, prefs, NOW)
    problems = []
    notes = [n for n in r.notes if "turned down" in n.say]
    able_down = {PROV[s[0]]["name"] for s in all_slots if s[0] in down and fits(s)}
    if not any(fits(s) for s in others) and able_down:
        if len(notes) != 1 or notes[0].kind != "wish_conflict":
            return [("missing", VT[vt]["name"], label, [str(n) for n in r.notes])]
        m = NOTE.match(notes[0].say)
        if not m or m.group("label") != label:
            problems.append(("wording", VT[vt]["name"], notes[0].say))
        if _named_in(notes[0].say) != able_down:
            problems.append(("names", VT[vt]["name"], label, sorted(able_down), notes[0].say))
        if not notes[0].say[0].isupper():
            problems.append(("starts lower case", notes[0].say))
    elif notes:
        problems.append(("unexpected", VT[vt]["name"], label, [n.say for n in notes]))
    if any(o.provider_id in down for o in r.options):
        problems.append(("offered a turned-down doctor", VT[vt]["name"], label))
    return problems


@pytest.mark.parametrize("kind", list(CALLERS))
def test_turned_down_note_for_places_whole_catalog(catalog, schedule, kind):
    problems = []
    for vt in bookable(kind):
        for down in _turn_down_cases(schedule, kind, vt):
            for lid, loc in LOC.items():
                problems += _check_turned_down_note(catalog, schedule, kind, vt, down,
                                                    Preferences(location_hint=loc["name"]),
                                                    lambda s, lid=lid: s[1] == lid, loc["name"])
    assert not problems, (len(problems), problems[:4])


@pytest.mark.parametrize("kind", list(CALLERS))
def test_turned_down_note_for_languages_whole_catalog(catalog, schedule, kind):
    langs = sorted({lang for p in PROV.values() for lang in p["languages"]} - {"English"})
    problems = []
    for vt in bookable(kind):
        for down in _turn_down_cases(schedule, kind, vt):
            for lang in langs:
                problems += _check_turned_down_note(catalog, schedule, kind, vt, down, Preferences(language=lang),
                                                    lambda s, lang=lang: lang in PROV[s[0]]["languages"], lang)
    assert not problems, (len(problems), problems[:4])


@pytest.mark.parametrize("kind", list(CALLERS))
def test_turned_down_note_for_days_whole_catalog(catalog, schedule, kind):
    """A day only turned-down doctors have: the note must name only the turned-down doctors
    who actually have that day open (spec: every note true), and read as a sentence."""
    from datetime import timedelta
    days = [(NOW + timedelta(days=k)).date() for k in range(15)]
    problems = []
    for vt in bookable(kind):
        for down in _turn_down_cases(schedule, kind, vt):
            for d in days:
                # the label is the module's own day phrase, so the exact-wording check is skipped here
                problems += [p for p in _check_turned_down_note(
                    catalog, schedule, kind, vt, down, Preferences(days=[d.isoformat()]),
                    lambda s, d=d: s[2].date() == d, "") if p[0] != "wording"]
    assert not problems, (len(problems), problems[:4])


def test_no_other_doctor_note_names_only_doctors_who_can_do_the_visit(catalog, schedule):
    """'not Dr. <surname>' when only one doctor with that surname can do the visit: the
    no_other_doctor note may name only the turned-down doctors who can actually do it."""
    problems, tried = [], 0
    for kind in CALLERS:
        for vt in bookable(kind):
            able = sorted({s[0] for s in slots(schedule, kind, vt)})
            if len(able) != 1:
                continue
            surname = PROV[able[0]]["name"].split()[-1]
            card = card_for(kind, vt)
            # round 5: "not Dr. <surname>" -> the tool layer passes every doctor with that surname
            card.turn_down_doctors(catalog, provider_ids=[p for p, x in PROV.items()
                                                          if x["name"].split()[-1] == surname])
            r = find_options(catalog, schedule, card.caller, vt, card.preferences, NOW)
            nod = [n.say for n in r.notes if n.kind == "no_other_doctor"]
            tried += 1
            if len(nod) != 1 or _named_in(nod[0]) != {PROV[able[0]]["name"]}:
                problems.append((VT[vt]["name"], PROV[able[0]]["name"], nod))
    assert tried
    assert not problems, (len(problems), problems[:3])
