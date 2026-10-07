"""Round 5 (spec-changes-round-5.md), sections 2, 5 and 6: values that aren't what the
instruction asks for are refused, and the smaller changes (no-preference lists, house
numbers we don't have, named-date wording, doctor words, data checks).

Expected answers come from the spec text and the raw data files.
"""

import copy
import json
from datetime import datetime, timedelta

import pytest

from clinic import BookingCard, Catalog, CatalogError, Choices, PatientDirectory, Preferences, find_options
from conftest import NOW, new_caller
from reference import DATA, LOC, PROV, SPECIALTIES, VT, ref_pairs

RAW = json.loads((DATA / "catalog.json").read_text())
EXTRAS = json.loads((DATA / "location_extras.json").read_text())
PATIENTS = json.loads((DATA / "patients.json").read_text())["patients"]
SKIN, PHYSICAL = "appt_027", "appt_002"


def card_with(vt=SKIN, **prefs):
    card = BookingCard(caller=new_caller(), preferences=Preferences(**prefs))
    card.choices = Choices(specialty=VT[vt]["specialty"], visit_type_id=vt)
    return card


def run(catalog, schedule, prefs, vt=SKIN, now=NOW):
    return find_options(catalog, schedule, new_caller(), vt, prefs, now)


def kinds(r):
    return [n.kind for n in r.notes]


def said(r):
    return [n.say for n in r.notes]


def open_slots(schedule, vt, is_new=True):
    return [(p, l, t) for p, l in sorted(ref_pairs(is_new, vt))
            for t in schedule.open_slots(p, l, VT[vt]["duration_min"], NOW)]


# ---------------------------------------------------------------- s2 and s5: language values
def test_one_language_name_is_a_language_wish(catalog, schedule):
    card = card_with(PHYSICAL)
    card.change_choice("language", "Spanish")
    assert card.preferences.latest == "language"
    r = run(catalog, schedule, card.preferences, PHYSICAL)
    speakers = {p for p, x in PROV.items() if "Spanish" in x["languages"]}
    assert any(s[0] in speakers for s in open_slots(schedule, PHYSICAL))
    assert r.options and all(o.provider_id in speakers for o in r.options) and not r.notes


@pytest.mark.parametrize("value", ["Mandarin Chinese", "mandarin chinese", "MANDARIN"])
def test_mandarin_chinese_counts_as_mandarin(catalog, schedule, value):
    card = card_with(PHYSICAL)
    card.change_choice("language", value)
    r = run(catalog, schedule, card.preferences, PHYSICAL)
    speakers = {p for p, x in PROV.items() if "Mandarin" in x["languages"]}
    assert any(s[0] in speakers for s in open_slots(schedule, PHYSICAL))
    assert r.options and all(o.provider_id in speakers for o in r.options) and not r.notes, said(r)


def test_an_unknown_but_real_looking_language_is_kept_and_gets_the_true_note(catalog, schedule):
    card = card_with()
    card.change_choice("language", "Klingon")
    r = run(catalog, schedule, card.preferences)
    assert r.options and said(r) == ["None of the doctors available to you for Skin Cancer Screening speaks Klingon."]
    assert kinds(r) == ["wish_impossible"]


@pytest.mark.parametrize("value", ["any language", "not Spanish", "no Spanish please", "don't mind", "any",
                                   "no preference", "Spanish please", "Spanish or English", "anything but Spanish",
                                   "whatever", "none", "a Spanish speaker", "Spanish speaking"])
def test_a_sentence_is_refused_with_how_to_pass_the_language(catalog, schedule, value):
    card = card_with()
    card.change_choice("language", value)
    r = run(catalog, schedule, card.preferences)
    assert not r.options and kinds(r) == ["bad_input"], (value, said(r))
    assert "one language name" in r.notes[0].say.lower()
    assert not any("speaks" in s for s in said(r))  # never a false "nobody speaks ..." note


@pytest.mark.parametrize("clear", ["", "   "])
def test_an_empty_language_clears_the_wish(catalog, schedule, clear):
    card = card_with(language="Klingon")
    card.change_choice("language", clear)
    assert card.preferences.language == ""
    assert not run(catalog, schedule, card.preferences).notes


def test_chinese_alone_never_gives_a_false_nobody_speaks_note(catalog, schedule):
    # "Every note must be true": a doctor who speaks Mandarin speaks Chinese. If one is
    # available, "None of the doctors ... speaks Chinese." is false.
    speakers = {p for p, x in PROV.items() if "Mandarin" in x["languages"]}
    assert any(s[0] in speakers for s in open_slots(schedule, PHYSICAL))
    card = card_with(PHYSICAL)
    card.change_choice("language", "Chinese")
    r = run(catalog, schedule, card.preferences, PHYSICAL)
    assert not [s for s in said(r) if "speaks Chinese" in s], said(r)


# ---------------------------------------------------------------- s5: "morning" and "afternoon" together
@pytest.mark.parametrize("value", ["morning or afternoon", "Thursday morning or Friday afternoon",
                                   "this morning or this afternoon", "morning and afternoon",
                                   "Thursday morning, Friday afternoon", "Afternoon or morning"])
def test_both_times_of_day_in_a_spoken_value_are_refused(catalog, schedule, value):
    card = card_with()
    card.change_choice("time", value)
    r = run(catalog, schedule, card.preferences)
    assert not r.options and r.notes and set(kinds(r)) == {"bad_input"}, (value, said(r), card.preferences.time_of_day)
    assert any("one day at a time" in n.say for n in r.notes)


@pytest.mark.parametrize("prefs", [
    {"time_of_day": "morning or afternoon"},
    {"days": ["Thursday morning or Friday afternoon"]},
    {"days": ["Thursday morning", "Friday afternoon"]},      # the same wish as a two-entry list
    {"days": ["Thursday afternoon"], "time_of_day": "morning"},
])
def test_both_times_of_day_in_the_stored_wish_are_refused(catalog, schedule, prefs):
    r = run(catalog, schedule, Preferences(**prefs))
    assert not r.options and kinds(r) == ["bad_input"], (prefs, said(r), [o.spoken for o in r.options])


def test_both_times_of_day_through_the_days_argument_are_refused(catalog, schedule):
    card = card_with()
    card.change_choice("time", days=["Thursday morning", "Friday afternoon"])
    r = run(catalog, schedule, card.preferences)
    assert not r.options and kinds(r) == ["bad_input"], (card.preferences.days, card.preferences.time_of_day,
                                                          [o.spoken for o in r.options])


@pytest.mark.parametrize("value,days,tod", [("Thursday morning", ["Thursday"], "morning"),
                                            ("afternoon", [], "afternoon"),
                                            ("Thursday or Friday", ["Thursday", "Friday"], "")])
def test_one_time_of_day_is_still_fine(catalog, schedule, value, days, tod):
    card = card_with()
    card.change_choice("time", value)
    r = run(catalog, schedule, card.preferences)
    assert "bad_input" not in kinds(r)
    for o in r.options:
        assert not days or o.start.strftime("%A") in days
        assert not tod or (o.start.hour < 12) == (tod == "morning")


# ---------------------------------------------------------------- s6: "no preference" vs "any day"
NO_PREFERENCE = ["I don't mind", "no preference", "any time", "any time works", "anytime", "whenever",
                 "doesn't matter", "either", "whatever", "Any time is fine", "Dont mind"]
ANY_DAY = ["any day", "Any day", "any date", "any day is fine", "any day works", "Any day works!"]


@pytest.mark.parametrize("value", NO_PREFERENCE)
def test_no_preference_clears_day_and_time(catalog, schedule, value):
    card = card_with(days=["Thursday"], time_of_day="morning")
    card.change_choice("time", value)
    assert card.preferences.days == [] and card.preferences.time_of_day == "", value
    assert not run(catalog, schedule, card.preferences).notes


@pytest.mark.parametrize("value", ANY_DAY)
def test_any_day_clears_the_day_only(catalog, schedule, value):
    card = card_with(days=["Thursday"], time_of_day="morning")
    card.change_choice("time", value)
    assert card.preferences.days == [] and card.preferences.time_of_day == "morning", value
    r = run(catalog, schedule, card.preferences)
    assert "bad_input" not in kinds(r) and all(o.start.hour < 12 for o in r.options)


@pytest.mark.parametrize("value", ANY_DAY + NO_PREFERENCE)
def test_any_day_or_no_preference_as_a_time_of_day_means_no_time_wish(catalog, schedule, value):
    base = run(catalog, schedule, Preferences())
    r = run(catalog, schedule, Preferences(time_of_day=value))
    assert not r.notes, (value, said(r))
    assert [(o.provider_id, o.start) for o in r.options] == [(o.provider_id, o.start) for o in base.options]


@pytest.mark.parametrize("value", ["no preference", "anywhere", "don't mind", "I don't mind", "whatever"])
def test_no_preference_place_and_doctor(catalog, schedule, value):
    base = run(catalog, schedule, Preferences())
    for prefs in (Preferences(location_hint=value), Preferences(doctor_name_heard=value)):
        r = run(catalog, schedule, prefs)
        assert not r.notes, (value, said(r))
        assert [(o.provider_id, o.start) for o in r.options] == [(o.provider_id, o.start) for o in base.options]


# ---------------------------------------------------------------- s6: house numbers
def _on_street(word):
    return sorted(lid for lid, l in LOC.items() if l["address"].split()[1].lower() == word)


def _number_we_have(lid):
    return LOC[lid]["address"].split()[0]


@pytest.mark.parametrize("hint,street", [("near 9999 Geary", "geary"), ("9999 Geary Blvd", "geary"),
                                         ("the 9999 Geary Blvd one", "geary"), ("near 1 Geary Boulevard", "geary"),
                                         ("9999 Market St", "market"), ("9999 Bryant Street", "bryant"),
                                         ("4455 Market St", "market")])  # a number we have, but on another street
def test_a_house_number_we_do_not_have_means_somewhere_on_that_street(catalog, schedule, hint, street):
    clinics = _on_street(street)
    assert len(clinics) == 2  # from catalog.json addresses
    m = catalog.resolve_place(hint)
    assert m.kind == "ambiguous" and sorted(m.location_ids) == clinics and m.near, (hint, m)
    r = run(catalog, schedule, Preferences(location_hint=hint))
    base = run(catalog, schedule, Preferences())
    assert kinds(r) == ["place_ambiguous"]
    assert all(LOC[c]["name"] in r.notes[0].say for c in clinics)
    assert [(o.provider_id, o.location_id, o.start) for o in r.options] == \
           [(o.provider_id, o.location_id, o.start) for o in base.options]  # not narrowed


@pytest.mark.parametrize("lid", sorted(LOC))
def test_a_house_number_we_have_picks_that_clinic(catalog, lid):
    address = LOC[lid]["address"]                     # e.g. "4455 Geary Blvd"
    m = catalog.resolve_place(address)
    assert m.kind == "location" and m.location_ids == [lid] and not m.near, (address, m)
    m = catalog.resolve_place("near " + address)
    assert m.kind == "location" and m.location_ids == [lid] and m.near, (address, m)


@pytest.mark.parametrize("hint", ["9999 Main St", "9999 Mission Street"])
def test_an_unknown_number_on_a_one_clinic_street_does_not_narrow(catalog, hint):
    m = catalog.resolve_place(hint)
    assert m.near, (hint, m)  # "somewhere on that street": rank by distance, don't restrict


# ---------------------------------------------------------------- s6: named dates
def _date(s):
    d = datetime.fromisoformat(s).date()
    return f"{d:%A} {d.day} {d:%B}"


@pytest.mark.parametrize("day", ["2026-10-10", "2026-10-11", "2026-10-17", "2026-10-18"])  # weekends: closed
def test_a_named_date_with_nothing_open_has_no_window_phrase(catalog, schedule, day):
    r = run(catalog, schedule, Preferences(days=[day]))
    assert said(r) == [f"Nothing is open on {_date(day)} for Skin Cancer Screening; here are other options."]
    assert r.options


def test_two_named_dates_have_no_window_phrase(catalog, schedule):
    r = run(catalog, schedule, Preferences(days=["2026-10-10", "2026-10-11"]))
    (note,) = said(r)
    assert note.startswith("Nothing is open on Saturday 10 October") and "Sunday 11 October" in note
    assert note.endswith("for Skin Cancer Screening; here are other options.") and "next 14 days" not in note


@pytest.mark.parametrize("days", [["Saturday"], ["Sunday"], ["2026-10-10", "Sunday"]])
def test_weekday_names_still_get_the_window_phrase(catalog, schedule, days):
    r = run(catalog, schedule, Preferences(days=days))
    (note,) = said(r)
    assert note.endswith("for Skin Cancer Screening in the next 14 days; here are other options."), note


def test_today_with_nothing_left_has_no_window_phrase(catalog, schedule):
    late = datetime(2026, 10, 6, 16, 30)
    r = run(catalog, schedule, Preferences(days=["today"]), now=late)
    assert said(r) == ["Nothing is open today for Skin Cancer Screening; here are other options."]


# ---------------------------------------------------------------- s6: doctor words
IRREGULAR = {"Dental": ["dentist"], "Orthopedics": ["orthopedist"], "Pediatrics": ["pediatrician"]}


def _regular_words(specialty):
    out = []
    for half in specialty.split("/"):
        w = half.lower()
        if w.endswith("y"):
            out.append(w[:-1] + "ist")   # dermatology -> dermatologist, allergy -> allergist, therapy -> therapist
    return out


DOCTOR_WORDS = sorted({(w, s) for s in SPECIALTIES for w in IRREGULAR.get(s, []) + _regular_words(s)})


def test_the_doctor_word_list_covers_the_expected_specialties():
    assert {s for _, s in DOCTOR_WORDS} >= {"Dental", "Orthopedics", "Pediatrics", "Dermatology", "Physical Therapy",
                                             "Allergy/Immunology", "Psychiatry", "Cardiology"}


@pytest.mark.parametrize("word,specialty", DOCTOR_WORDS)
def test_doctor_words_regular_rule_plus_three_irregular(catalog, word, specialty):
    assert catalog.match_specialty(word) == specialty
    assert catalog.match_specialty(word + "s") == specialty           # plural allowed
    assert catalog.match_specialty(word.upper()) == specialty


@pytest.mark.parametrize("word", ["orthopedician", "podiatrist", "surgeon", "gynecologist",
                                  "generalist", "physician", "therapist", "entist", "labist", "internist"])
def test_doctor_words_that_match_nothing(catalog, word):
    assert catalog.match_specialty(word) is None, (word, catalog.match_specialty(word))


# ---------------------------------------------------------------- s6: data checks
def _load(mut_raw=None, mut_extras=None, raw=None, extras=None):
    raw = copy.deepcopy(RAW) if raw is None else raw
    extras = copy.deepcopy(EXTRAS) if extras is None else extras
    if mut_raw:
        mut_raw(raw)
    if mut_extras:
        mut_extras(extras)
    return Catalog(raw, extras)


def _loc(lid, field, value):
    return lambda e: e["locations"][lid].__setitem__(field, value)


def _raw(section, i, field, value):
    return lambda d: d[section][i].__setitem__(field, value)


CATALOG_PROBLEMS = {
    "hours with 25:00": (_raw("locations", 3, "hours", "Mon-Fri 8:00-25:00"), None),
    "hours with minute 75": (_raw("locations", 3, "hours", "Mon-Fri 8:75-17:00"), None),
    "hours as a number": (_raw("locations", 3, "hours", 8), None),
    "hours None": (_raw("locations", 3, "hours", None), None),
    "location id a list": (_raw("locations", 0, "id", ["loc_000"]), None),
    "provider id a dict": (_raw("providers", 0, "id", {"id": "prov_001"}), None),
    "visit type id a number": (_raw("appointment_types", 0, "id", 27), None),
    "capabilities as text": (_raw("locations", 1, "capabilities", "imaging"), None),
    "capabilities with a number": (_raw("locations", 1, "capabilities", ["imaging", 3]), None),
    "required_capability a list": (_raw("appointment_types", 65, "required_capability", ["imaging"]), None),
    "location_ids holding a list": (_raw("providers", 0, "location_ids", [["loc_000"]]), None),
    "appointment_type_ids None": (_raw("providers", 0, "appointment_type_ids", None), None),
    "unknown location": (lambda d: d["providers"][0]["location_ids"].append("loc_999"), None),
    "unknown visit type": (lambda d: d["providers"][0]["appointment_type_ids"].append("appt_999"), None),
    "latitude 999": (None, _loc("loc_000", "lat", 999)),
    "latitude text": (None, _loc("loc_000", "lat", "37.7")),
    "latitude True": (None, _loc("loc_000", "lat", True)),
    "latitude NaN": (None, _loc("loc_000", "lat", float("nan"))),
    "longitude -200": (None, _loc("loc_000", "lon", -200)),
    "longitude infinite": (None, _loc("loc_000", "lon", float("inf"))),
    "latitude huge integer": (None, _loc("loc_000", "lat", 10 ** 400)),
    "also_called as text": (None, _loc("loc_005", "also_called", "Midtown")),
    "also_called with a number": (None, _loc("loc_005", "also_called", ["Midtown", 5])),
    "neighbourhood a number": (None, _loc("loc_005", "neighbourhood", 5)),
    "location map entry text": (None, lambda e: e["locations"].__setitem__("loc_000", "somewhere")),
    "location map entry missing": (None, lambda e: e["locations"].pop("loc_000")),
    "landmark as text": (None, lambda e: e["landmarks"].__setitem__("Somewhere", "near the park")),
    "landmark one number": (None, lambda e: e["landmarks"].__setitem__("Somewhere", [37.7])),
    "landmark of None": (None, lambda e: e["landmarks"].__setitem__("Somewhere", [None, None])),
    "landmark latitude out of range": (None, lambda e: e["landmarks"].__setitem__("Somewhere", [137.7, -122.4])),
    "landmarks a list": (None, lambda e: e.__setitem__("landmarks", [])),
    "landmarks None": (None, lambda e: e.__setitem__("landmarks", None)),
}


@pytest.mark.parametrize("label", list(CATALOG_PROBLEMS))
def test_each_data_problem_is_a_catalog_error_not_a_crash(label):
    mut_raw, mut_extras = CATALOG_PROBLEMS[label]
    with pytest.raises(CatalogError):
        _load(mut_raw, mut_extras)


ODD_TOP_LEVEL = {
    "catalog None": lambda: (None, copy.deepcopy(EXTRAS)),
    "catalog a list": lambda: ([], copy.deepcopy(EXTRAS)),
    "catalog empty": lambda: ({}, copy.deepcopy(EXTRAS)),
    "catalog text": lambda: ("catalog", copy.deepcopy(EXTRAS)),
    "a section as text": lambda: ({"locations": "x", "providers": [], "appointment_types": []}, copy.deepcopy(EXTRAS)),
    "map data None": lambda: (copy.deepcopy(RAW), None),
    "map data a list": lambda: (copy.deepcopy(RAW), []),
    "map data text": lambda: (copy.deepcopy(RAW), "extras"),
    "map locations a list": lambda: (copy.deepcopy(RAW), {"locations": [], "landmarks": {}}),
}


@pytest.mark.parametrize("label", list(ODD_TOP_LEVEL))
def test_odd_top_level_data_is_a_catalog_error(label):
    raw, extras = ODD_TOP_LEVEL[label]()
    with pytest.raises(CatalogError):
        Catalog(raw, extras)


def test_one_catalog_error_lists_every_problem():
    picked = ["hours with 25:00", "location id a list", "capabilities as text", "required_capability a list",
              "unknown location", "unknown visit type", "latitude 999", "longitude -200", "also_called as text",
              "neighbourhood a number", "landmark as text"]
    raw, extras = copy.deepcopy(RAW), copy.deepcopy(EXTRAS)
    for label in picked:
        mut_raw, mut_extras = CATALOG_PROBLEMS[label]
        if mut_raw:
            mut_raw(raw)
        if mut_extras:
            mut_extras(extras)
    with pytest.raises(CatalogError) as e:
        Catalog(raw, extras)
    text = str(e.value)
    for marker in ["25:00", "id", "capabilities", "required_capability", "loc_999", "appt_999", "lat", "lon",
                   "also_called", "neighbourhood", "Somewhere"]:
        assert marker in text, (marker, text)
    assert text.count("\n- ") >= len(picked), text


@pytest.mark.parametrize("records", [
    "not a list", None, {"patients": []},
    ["James Wilson, 1984-03-12"],
    [{"id": "p1", "name": "Ann Lee", "date_of_birth": "1990-01-01", "referrals_on_file": "Radiology"}],
    [{"id": "p1", "name": "Ann Lee", "date_of_birth": "1990-01-01", "referrals_on_file": ["Radiology", 5]}],
    [{"id": 1, "name": "Ann Lee", "date_of_birth": "1990-01-01"}],
    [{"id": "p1", "name": ["Ann", "Lee"], "date_of_birth": "1990-01-01"}],
    [{"id": "p1", "name": "Ann Lee", "date_of_birth": 19900101}],
    [{"id": "p1", "name": "Ann Lee"}],
    [{"name": "Ann Lee", "date_of_birth": "1990-01-01"}],
])
def test_each_patient_data_problem_is_a_catalog_error(records):
    with pytest.raises(CatalogError):
        PatientDirectory(records)


def test_one_patient_error_lists_every_problem():
    records = copy.deepcopy(PATIENTS) + [
        "text, not a record",
        {"id": "p_a", "name": "Ann Lee", "date_of_birth": "1990-01-01", "referrals_on_file": "Radiology"},
        {"id": "p_b", "name": "Bo Chan"},
        {"id": "p_c", "name": 42, "date_of_birth": "1990-01-01"},
    ]
    with pytest.raises(CatalogError) as e:
        PatientDirectory(records)
    text = str(e.value)
    assert "p_a" in text and "referrals_on_file" in text and "p_b" in text and "date_of_birth" in text
    assert "p_c" in text and "name" in text and text.count("\n- ") >= 4, text


def test_the_real_data_still_loads(catalog, directory):
    assert len(catalog.providers) == len(RAW["providers"]) and len(directory.records) == len(PATIENTS)


def test_window_is_today_plus_fourteen_days(catalog, schedule):
    last = (NOW + timedelta(days=14)).date().isoformat()
    after = (NOW + timedelta(days=15)).date().isoformat()
    assert "bad_input" not in kinds(run(catalog, schedule, Preferences(days=[last])))
    assert kinds(run(catalog, schedule, Preferences(days=[after]))) == ["bad_input"]
