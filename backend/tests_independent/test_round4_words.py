"""Round 4 (spec-changes-round-4.md): time phrases, "no preference" forms, place rules
(change 3 and the "Places" list, including inputs that must NOT match), specialty words,
language as a change, and catalog checks with broken data.

Expected answers come from the spec text and the raw data files.
"""

import copy
import json
from datetime import timedelta

import pytest

from clinic import BookingCard, Catalog, CatalogError, Choices, PatientDirectory, Preferences, find_options
from conftest import NOW, new_caller
from reference import DATA, LOC, PROV, VT, ref_pairs

RAW = json.loads((DATA / "catalog.json").read_text())
EXTRAS = json.loads((DATA / "location_extras.json").read_text())
SKIN = "appt_027"
TODAY, THU, FRI = NOW.date(), "Thursday", "Friday"
STREETS = {}  # street word -> location ids, from catalog.json addresses
for _lid, _l in LOC.items():
    STREETS.setdefault(_l["address"].split()[1].lower(), set()).add(_lid)


def skin_slots(schedule):
    return [(p, l, t) for p, l in sorted(ref_pairs(True, SKIN))
            for t in schedule.open_slots(p, l, VT[SKIN]["duration_min"], NOW)]


def card_with(**prefs):
    card = BookingCard(caller=new_caller())
    card.choices = Choices(specialty="Dermatology", visit_type_id=SKIN)
    for k, v in prefs.items():
        setattr(card.preferences, k, v)
    return card


def run(catalog, schedule, prefs):
    return find_options(catalog, schedule, new_caller(), SKIN, prefs, NOW)


# ---------------------------------------------------------------- time wishes through change_choice
# Round 6 s1: the AI turns the caller's phrase (first column) into plain fields.
@pytest.mark.parametrize("phrase,kwargs,days,tod", [
    ("this afternoon", dict(days=["today"], time_of_day="afternoon"), ["today"], "afternoon"),
    ("This afternoon.", dict(days=["Today"], time_of_day="Afternoon"), ["today"], "afternoon"),  # case doesn't matter
    ("this morning", dict(days=["today"], time_of_day="morning"), ["today"], "morning"),
    ("Thursday or Friday", dict(days=[THU, FRI]), [THU, FRI], ""),
    ("Thursday, morning please", dict(days=["thu"], time_of_day="morning"), [THU], "morning"),
    ("Thursday afternoon please", dict(days=["thurs"], time_of_day="afternoon"), [THU], "afternoon"),
    ("tomorrow morning", dict(days=["tomorrow"], time_of_day="morning"), ["tomorrow"], "morning"),
])
def test_time_phrases_set_day_and_time(catalog, schedule, phrase, kwargs, days, tod):
    card = card_with()
    card.change_choice("time", **kwargs)
    p = card.preferences
    assert [d.lower() for d in p.days] == [d.lower() for d in kwargs.get("days", [])], p.days
    assert p.time_of_day.lower() == tod, p.time_of_day
    r = run(catalog, schedule, p)
    assert not [n for n in r.notes if n.kind == "bad_input"], [n.say for n in r.notes]
    assert r.options
    for o in r.options:  # every option meets the wish, or a note says why not
        day_ok = any((d == "today" and o.start.date() == TODAY) or (d == "tomorrow" and o.start.date() == TODAY + timedelta(1))
                     or o.start.strftime("%A") == d for d in days)
        time_ok = not tod or (o.start.hour < 12) == (tod == "morning")
        assert (day_ok and time_ok) or r.notes, (phrase, o.spoken)


@pytest.mark.parametrize("phrase", ["I don't mind", "don't mind", "dont mind", "whenever", "any time", "Any time.",
                                    "no preference", "No preference"])
def test_no_preference_time_phrases_clear_day_and_time(phrase):
    # Round 6 s2: a no-preference word counts as "" in each field it is put in.
    card = card_with(days=[THU], time_of_day="morning")
    card.change_choice("time", days=[phrase], time_of_day=phrase)
    assert card.preferences.days == [] and card.preferences.time_of_day == ""


@pytest.mark.parametrize("phrase", ["any day", "Any day"])
def test_any_day_clears_the_day_only(phrase):
    card = card_with(days=[THU], time_of_day="morning")
    card.change_choice("time", phrase)
    assert card.preferences.days == [] and card.preferences.time_of_day == "morning"


def test_only_what_is_mentioned_changes():
    card = card_with(days=[THU], time_of_day="morning")
    card.change_choice("time", time_of_day="afternoon")   # round 6 s1: None keeps the day
    assert card.preferences.days == [THU] and card.preferences.time_of_day == "afternoon"
    card.change_choice("time", "Friday")
    assert card.preferences.days == [FRI] and card.preferences.time_of_day == "afternoon"


@pytest.mark.parametrize("phrase", ["next Thursday", "lunchtime", "evening", "Oct 13", "Thursday at 3pm", "20261013"])
def test_unclear_time_phrases_give_bad_input_and_no_options(catalog, schedule, phrase):
    card = card_with()
    card.change_choice("time", phrase)
    r = run(catalog, schedule, card.preferences)
    assert not r.options and r.notes and {n.kind for n in r.notes} == {"bad_input"}


def test_time_phrases_also_work_in_preferences_days(catalog, schedule):
    # Round 6 s1: Preferences takes the same plain values; phrases there are refused.
    r = run(catalog, schedule, Preferences(days=["today"], time_of_day="afternoon"))
    assert not [n for n in r.notes if n.kind == "bad_input"]
    today_pm = [s for s in skin_slots(schedule) if s[2].date() == TODAY and s[2].hour >= 12]
    if today_pm:
        assert r.options and all(o.start.date() == TODAY and o.start.hour >= 12 for o in r.options)
    r2 = run(catalog, schedule, Preferences(days=[THU, FRI]))
    assert r2.options and all(o.start.strftime("%A") in (THU, FRI) for o in r2.options)
    for phrase in ("this afternoon", "Thursday or Friday"):
        r3 = run(catalog, schedule, Preferences(days=[phrase]))
        assert not r3.options and [n.kind for n in r3.notes] == ["bad_input"], (phrase, [n.say for n in r3.notes])


# ---------------------------------------------------------------- "no preference" everywhere
NO_PREF = ["I don't mind", "dont mind", "no preference", "No Preference", "whatever", "doesn't matter"]


@pytest.mark.parametrize("phrase", NO_PREF + ["anywhere"])
def test_no_preference_place(catalog, schedule, phrase):
    r = run(catalog, schedule, Preferences(location_hint=phrase))
    base = run(catalog, schedule, Preferences())
    assert not r.notes and [o.start for o in r.options] == [o.start for o in base.options]


@pytest.mark.parametrize("phrase", NO_PREF + ["anyone", "any", "anybody"])
def test_no_preference_doctor(catalog, schedule, phrase):
    r = run(catalog, schedule, Preferences(doctor_name_heard=phrase))
    assert not r.notes and r.options
    card = card_with()
    card.change_choice("doctor", phrase)
    r2 = run(catalog, schedule, card.preferences)
    assert not [n for n in r2.notes if n.kind.startswith("doctor")], [n.say for n in r2.notes]


@pytest.mark.parametrize("phrase", NO_PREF + ["any day", "any time", "whenever"])
def test_no_preference_day_in_preferences(catalog, schedule, phrase):
    r = run(catalog, schedule, Preferences(days=[phrase], time_of_day=phrase))
    assert not r.notes and r.options


# ---------------------------------------------------------------- language as a change
def test_language_change_is_latest_and_maps_two_word_names(catalog, schedule):
    card = card_with()
    card.change_choice("language", "Mandarin Chinese")
    assert card.preferences.latest == "language"
    r = run(catalog, schedule, card.preferences)
    speakers = {p for p, x in PROV.items() if "Mandarin" in x["languages"]}
    if any(s[0] in speakers for s in skin_slots(schedule)):
        assert r.options and all(o.provider_id in speakers for o in r.options)
    else:
        assert any("Mandarin" in n.say and "chinese" not in n.say.lower() for n in r.notes), [n.say for n in r.notes]
    card.change_choice("language", "")
    assert card.preferences.language == ""
    # Round 6 s2 (reverses round 5): "any" counts as "" for language too: no wish, no note.
    card.change_choice("language", "any")
    assert card.preferences.latest == "language"
    r = run(catalog, schedule, card.preferences)
    assert r.options and r.notes == [], [n.say for n in r.notes]


def test_unknown_language_is_kept_as_said(catalog, schedule):
    card = card_with()
    card.change_choice("language", "Klingon")
    r = run(catalog, schedule, card.preferences)
    assert r.options and any("Klingon" in n.say and n.kind == "wish_impossible" for n in r.notes)


# ---------------------------------------------------------------- places (change 3 and the list)
# Round 7 reverses round-4 change 3: a bare street name is never a street. "near Geary"
# is now passed as "Geary Street" with near=True; bare "Geary" with near=True isn't recognised.
@pytest.mark.parametrize("hint", ["Geary Street", "Market Street", "Geary Blvd", "Market St", "Bryant Street"])
def test_near_a_bare_street_is_recognised_and_ambiguous(catalog, schedule, hint):
    street = hint.split()[0].lower()
    m = catalog.resolve_place(hint, near=True)
    assert m.kind == "ambiguous" and set(m.location_ids) == STREETS[street] and m.near
    assert catalog.resolve_place(hint.split()[0], near=True).kind == "none"
    r = run(catalog, schedule, Preferences(location_hint=hint, near=True))
    base = run(catalog, schedule, Preferences())
    assert [n.kind for n in r.notes] == ["place_ambiguous"]
    assert [(o.provider_id, o.location_id, o.start) for o in r.options] == \
           [(o.provider_id, o.location_id, o.start) for o in base.options]  # a note, no narrowing


@pytest.mark.parametrize("hint", ["Geary", "Market", "Bryant", "Main", "Market area"])
def test_a_bare_street_name_without_near_is_not_a_street(catalog, hint):
    assert catalog.resolve_place(hint).kind not in ("location", "ambiguous")


# round 7: "near 4455 Geary" -> ("4455 Geary Street", near=True); "near Main" -> ("Main Street", near=True)
@pytest.mark.parametrize("hint,lid,near", [("4455 Geary Street", "loc_004", True), ("4293 Geary Blvd", "loc_006", True),
                                           ("944 Bryant St", "loc_003", False), ("4671 Bryant Street", "loc_007", False),
                                           ("Main Street", "loc_000", True), ("Mission Street", "loc_002", True)])
def test_house_numbers_and_near_streets_pick_one_clinic(catalog, hint, lid, near):
    m = catalog.resolve_place(hint, near=near)
    assert m.kind == "location" and m.location_ids == [lid] and m.near is near


# round 7: "near X" is now the name X with near=True; each must still not match
@pytest.mark.parametrize("hint", ["Marin", "Van Ness", "Lombard", "Union Street", "St Mary's",
                                  "St Mary's Clinic", "Sunset Boulevard", "nowhere", "the bay",
                                  "Twin Peaks", "FiDi", "main", "the main one"])
@pytest.mark.parametrize("near", [False, True])
def test_places_that_must_not_match(catalog, hint, near):
    m = catalog.resolve_place(hint, near=near)
    assert m.kind == "none", (hint, m)


# round 7: "in SF" / "near SF" -> "SF" (near=True for the latter); linking words aren't read
@pytest.mark.parametrize("hint,near", [("SF", False), ("San Francisco", False), ("SF", True), ("sf", False)])
def test_city_words_alone_are_no_place_wish(catalog, schedule, hint, near):
    assert catalog.resolve_place(hint, near=near).kind == "any"
    assert not run(catalog, schedule, Preferences(location_hint=hint, near=near)).notes


# round 7: linking words are no longer read; the AI passes "Midtown SF" / "the Marina"
@pytest.mark.parametrize("hint,lid", [("Midtown SF", "loc_005"), ("Richmund", "loc_007"),
                                      ("Mision Bay", "loc_000"), ("the Marina", "loc_003")])
def test_linking_words_and_long_misspellings(catalog, hint, lid):
    m = catalog.resolve_place(hint)
    assert m.kind == "location" and m.location_ids == [lid]


# ---------------------------------------------------------------- specialty words
@pytest.mark.parametrize("word", ["podiatrist", "hematologist", "nephrologist", "audiologist", "generalist",
                                  "physician", "gynecologist", "podiatrists", "hematologists", "oncologist",
                                  "rheumatologist", "psychologist", "optometrist", "ist", "ologist"])
def test_specialty_words_that_match_nothing(catalog, word):
    assert catalog.match_specialty(word) is None


@pytest.mark.parametrize("word,spec", [
    ("dermatologist", "Dermatology"), ("Dermatologists", "Dermatology"), ("pediatrician", "Pediatrics"),
    ("allergist", "Allergy/Immunology"), ("immunologist", "Allergy/Immunology"), ("dentist", "Dental"),
    ("dentists", "Dental"), ("orthopedist", "Orthopedics"), ("psychiatrist", "Psychiatry"),
    ("physical therapist", "Physical Therapy"), ("cardiologists", "Cardiology"), ("pulmonologist", "Pulmonology"),
    ("gastroenterologist", "Gastroenterology"), ("ophthalmologist", "Ophthalmology"), ("urologist", "Urology"),
])
def test_doctor_words_built_from_specialty_names(catalog, word, spec):
    assert catalog.match_specialty(word) == spec


# ---------------------------------------------------------------- catalog checks with broken data
def _load(mut_raw=None, mut_extras=None):
    raw, extras = copy.deepcopy(RAW), copy.deepcopy(EXTRAS)
    if mut_raw:
        mut_raw(raw)
    if mut_extras:
        mut_extras(extras)
    return Catalog(raw, extras)


def _set(section, i, field, value):
    return lambda d: d[section][i].__setitem__(field, value)


@pytest.mark.parametrize("label,mut", [
    ("duration as text", _set("appointment_types", 0, "duration_min", "abc")),
    ("duration 30.5", _set("appointment_types", 0, "duration_min", 30.5)),
    ("languages null", _set("providers", 0, "languages", None)),
    ("location_ids as text", _set("providers", 0, "location_ids", "loc_000")),
    ("record not a record", lambda d: d["providers"].append("prov_x")),
    ("referral flag as text", _set("appointment_types", 0, "requires_referral", "yes")),
    ("repeated id", lambda d: d["locations"].append(copy.deepcopy(d["locations"][0]))),
])
def test_wrong_kinds_of_value_are_refused_clearly(label, mut):
    with pytest.raises(CatalogError):
        _load(mut)


def test_every_problem_is_listed_at_once():
    def mut(d):
        d["appointment_types"][0]["duration_min"] = "abc"
        d["providers"][0]["languages"] = None
        d["providers"].append("junk")
    with pytest.raises(CatalogError) as e:
        _load(mut)
    text = str(e.value)
    assert "duration_min" in text and "languages" in text and text.count("\n-") >= 3


# The spec examples are "e.g."; these are the same kinds of wrong value in fields the
# given schema also defines. Each must be a clear CatalogError, not a crash or silent nonsense.
@pytest.mark.parametrize("label,mut_raw,mut_extras", [
    ("id is a list", _set("locations", 0, "id", ["loc_000"]), None),
    ("unreadable hours (25:00)", _set("locations", 0, "hours", "Mon-Fri 8:00-25:00"), None),
    ("capabilities as text", _set("locations", 1, "capabilities", "imaging"), None),
    ("latitude not a number", None, lambda e: e["locations"]["loc_000"].__setitem__("lat", "abc")),
    ("latitude missing value", None, lambda e: e["locations"]["loc_000"].__setitem__("lat", None)),
])
def test_other_wrong_values_are_catalog_errors(label, mut_raw, mut_extras):
    with pytest.raises(CatalogError):
        _load(mut_raw, mut_extras)


@pytest.mark.parametrize("records", [["not a record"], [{"id": "p", "name": "A B"}], [{"name": "A B", "date_of_birth": "1990-01-01"}]])
def test_patient_records_that_are_broken_are_catalog_errors(records):
    with pytest.raises(CatalogError):
        PatientDirectory(records)
