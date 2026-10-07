"""Round 7 (spec-changes-round-7.md), sections 2, 3, 4 and 6: plain values.

- s2 languages: one name, nothing guessed (the accept / refuse table).
- s3 "no preference" words are stored as "" (doctor, place, language), never shown.
- s4 exact names for what can be changed (change_choice) and asked about (answer_question),
  and answer_question's sentence guard.
- s6 the weekday word table, and repeated ids reported once (catalog and patients).

Expected answers come from the spec text and the raw data files.
"""

import copy
import json

import pytest

from clinic import BookingCard, Catalog, CatalogError, Choices, PatientDirectory, Preferences, answer_question, \
    find_options
from conftest import NOW, new_caller, returning
from reference import DATA, LOC, PROV, SPECIALTIES, VT, ref_pairs

RAW = json.loads((DATA / "catalog.json").read_text())
EXTRAS = json.loads((DATA / "location_extras.json").read_text())
PATIENTS = json.loads((DATA / "patients.json").read_text())["patients"]
PHYSICAL = "appt_002"
OUR_LANGS = sorted({l for x in PROV.values() for l in x["languages"]})
ALL = returning(list(SPECIALTIES))


def run(catalog, schedule, prefs, vt=PHYSICAL, caller=None):
    return find_options(catalog, schedule, caller or new_caller(), vt, prefs, NOW)


def kinds(r):
    return [n.kind for n in r.notes]


def refused(r):
    return not r.options and kinds(r) == ["bad_input"]


def full_card():
    card = BookingCard(caller=new_caller(), preferences=Preferences(doctor_name_heard="Dr. Kenji Kim",
                                                                    location_hint="Downtown", near=True,
                                                                    days=["Thursday"], time_of_day="morning",
                                                                    language="Spanish"))
    card.choices = Choices(specialty="Dermatology", visit_type_id="appt_027")
    return card


# =============================================================== s2: languages
@pytest.mark.parametrize("lang", OUR_LANGS)
@pytest.mark.parametrize("form", [str, str.lower, str.upper, lambda s: f"  {s}  "])
def test_a_language_in_our_records_in_any_case(catalog, schedule, lang, form):
    r = run(catalog, schedule, Preferences(language=form(lang)), caller=ALL)
    assert "bad_input" not in kinds(r), [n.say for n in r.notes]
    speakers = {p for p, x in PROV.items() if lang in x["languages"]}
    if any(p in speakers for p, _ in ref_pairs(False, PHYSICAL)):
        assert r.options and all(o.provider_id in speakers for o in r.options), (lang, [o.provider_name for o in r.options])
        assert not r.notes
    for n in r.notes:   # the canonical name is used, never the caller's casing
        assert form(lang).strip() == lang or form(lang).strip() not in n.say


@pytest.mark.parametrize("said", ["Mandarin Chinese", "mandarin chinese", "Chinese Mandarin", "CHINESE MANDARIN",
                                  "Mandarin  Chinese"])
def test_the_listed_other_name_for_mandarin(catalog, schedule, said):
    r = run(catalog, schedule, Preferences(language=said), caller=ALL)
    speakers = {p for p, x in PROV.items() if "Mandarin" in x["languages"]}
    assert r.options and all(o.provider_id in speakers for o in r.options) and not r.notes, [n.say for n in r.notes]


@pytest.mark.parametrize("said,shown", [("Klingon", "Klingon"), ("Haitian Creole", "Haitian Creole"), ("ASL", "ASL"),
                                        ("Chinese", "Chinese"), ("klingon", "Klingon"), ("Cantonese", "Cantonese"),
                                        ("French", "French"), ("haitian creole", "Haitian Creole")])
def test_a_name_we_have_no_record_of_is_kept_as_said(catalog, schedule, said, shown):
    r = run(catalog, schedule, Preferences(language=said))
    base = run(catalog, schedule, Preferences())
    want = f"None of our doctors is listed as speaking {shown}. Our doctors speak " \
           f"{', '.join(OUR_LANGS[:-1])} and {OUR_LANGS[-1]}."
    assert [(n.kind, n.say) for n in r.notes] == [("wish_impossible", want)]
    assert [(o.provider_id, o.start) for o in r.options] == [(o.provider_id, o.start) for o in base.options]


@pytest.mark.parametrize("said", [
    # a language we have mixed with other words
    "Spanish French", "French Spanish", "Spanish only", "only Spanish", "Cantonese Mandarin", "Spanish Klingon",
    "English Spanish", "Mandarin Cantonese", "spanish ideally", "Spanish speaking",
    # more than two words
    "Haitian Creole French", "Old Church Slavonic", "Mandarin Chinese please", "the Spanish language",
    # sentences (round 6)
    "not Spanish", "no Spanish", "anyone but Spanish", "Spanish please", "any language", "someone Spanish",
    # not letters
    "Spanish-speaking", "Spanish/English", "Spanish, French", "Hindi?", "123",
])
def test_anything_else_is_refused(catalog, schedule, said):
    r = run(catalog, schedule, Preferences(language=said))
    assert refused(r), (said, [(n.kind, n.say) for n in r.notes], len(r.options))
    assert r.notes[0].say == (f"I couldn't use the language '{said}'. Pass one language name, like 'Spanish', "
                              "or leave it empty for no language wish.")


@pytest.mark.parametrize("said", ["", "  ", "any", "I don't mind", "no preference", "whatever", "Any", "doesn't matter"])
def test_no_preference_means_no_language_wish(catalog, schedule, said):
    r = run(catalog, schedule, Preferences(language=said))
    base = run(catalog, schedule, Preferences())
    assert not r.notes and [(o.provider_id, o.start) for o in r.options] == [(o.provider_id, o.start) for o in base.options]


def test_language_change_through_the_card_is_checked_the_same_way(catalog, schedule):
    card = full_card()
    card.change_choice("language", "Spanish only")
    assert card.preferences.language == "Spanish only"     # stored as said; the search refuses it
    assert refused(run(catalog, schedule, card.preferences, vt="appt_027"))
    card.change_choice("language", "Mandarin Chinese")
    r = run(catalog, schedule, card.preferences, vt="appt_027")
    assert "bad_input" not in kinds(r)


# =============================================================== s3: no preference stored as ""
NO_PREF_WORDS = ["any", "Any", "anyone", "anywhere", "I don't mind", "dont mind", "no preference", "No Preference",
                 "whatever", "whenever", "doesn't matter", "  anywhere  ", "anything"]


@pytest.mark.parametrize("word", NO_PREF_WORDS)
@pytest.mark.parametrize("what,field", [("doctor", "doctor_name_heard"), ("location", "location_hint"),
                                        ("language", "language")])
def test_no_preference_words_are_stored_as_empty(catalog, word, what, field):
    card = full_card()
    card.change_choice(what, word)
    assert getattr(card.preferences, field) == "", (what, word)
    label = {"doctor": "doctor:", "location": "place:", "language": "language:"}[what]
    assert label not in card.summary(catalog), card.summary(catalog)   # never shown


@pytest.mark.parametrize("word", ["any day", "Any Day", "any", "whenever", "I don't mind"])
def test_a_no_preference_day_as_new_value_clears_the_day(catalog, word):
    card = full_card()
    card.change_choice("time", word)
    p = card.preferences
    assert p.days == [] and p.time_of_day == "morning"   # only the day is cleared
    assert "days:" not in card.summary(catalog)


@pytest.mark.parametrize("word", ["any", "any time", "whenever", "no preference"])
def test_a_no_preference_time_of_day_clears_only_the_time_of_day(catalog, word):
    card = full_card()
    card.change_choice("time", time_of_day=word)
    p = card.preferences
    assert p.time_of_day == "" and p.days == ["Thursday"]


# =============================================================== s4: exact names
@pytest.mark.parametrize("what,field,value", [
    ("doctor", "doctor_name_heard", "Dr. Daniel Chen"), ("Doctor", "doctor_name_heard", "Dr. Daniel Chen"),
    (" DOCTOR ", "doctor_name_heard", "Dr. Daniel Chen"), ("location", "location_hint", "Midtown"),
    ("Location", "location_hint", "Midtown"), ("language", "language", "Hindi"), ("LANGUAGE", "language", "Hindi"),
    ("time", "days", ["Friday"]), ("Time", "days", ["Friday"]),
    ("visit_type", "visit_description", "knee MRI"), ("Visit Type", "visit_description", "knee MRI"),
    ("VISIT_TYPE", "visit_description", "knee MRI"), ("visit type", "visit_description", "knee MRI"),
])
def test_the_five_names_are_accepted_case_and_spaces_ignored(what, field, value):
    card = full_card()
    card.change_choice(what, value if not isinstance(value, list) else value[0])
    assert getattr(card.preferences, field) == value


@pytest.mark.parametrize("what", ["provider", "place", "clinic", "slot", "reason", "service", "day", "date", "visit",
                                  "appointment_type", "appointment", "doctors", "locations", "", "name", None])
def test_synonyms_are_refused_and_change_nothing(what):
    card = full_card()
    before = card.to_dict()
    with pytest.raises(ValueError) as e:
        card.change_choice(what, "x")
    assert "visit_type, doctor, location, time or language" in str(e.value)
    assert card.to_dict() == before


@pytest.mark.parametrize("about,name", [("location", "Midtown"), ("Location", "Midtown"), (" LOCATION ", "Midtown"),
                                        ("doctor", "Dr. Wei Lee"), ("Doctor", "Dr. Wei Lee"),
                                        ("visit_type", "knee MRI"), ("Visit_Type", "knee MRI"),
                                        ("visit type", "knee MRI"), ("Visit Type", "knee MRI")])
def test_answer_question_takes_the_three_names_case_and_spaces_ignored(catalog, about, name):
    """s4: "`about` must be location, doctor or visit_type (case and spaces ignored)" - the same
    words s4 uses for change_choice, where "Visit Type" is accepted."""
    r = answer_question(catalog, about, name)
    assert r["found"] is True, (about, r)


@pytest.mark.parametrize("about", ["provider", "clinic", "place", "office", "visit", "appointment", "service",
                                   "appointment_type", "weather", "doctors", "", None])
def test_answer_question_refuses_anything_else(catalog, about):
    r = answer_question(catalog, about, "Midtown")
    assert r["found"] is False
    if about:
        assert r["message"] == "Pass about as location, doctor or visit_type."


SENTENCE_WORDS = ["not", "but", "except", "without", "another", "other", "else", "someone", "somebody",
                  "anyone", "anybody", "different", "instead", "please"]


@pytest.mark.parametrize("word", SENTENCE_WORDS)
@pytest.mark.parametrize("about,name", [("doctor", "Dr. Chen"), ("doctor", "Dr. Daniel Chen"),
                                        ("location", "Downtown"), ("location", "Union Square")])
def test_answer_question_refuses_a_sentence_as_a_name(catalog, word, about, name):
    for value in (f"{word} {name}", f"{name} {word}", f"{word.upper()} {name}!", f"{name}, {word}"):
        r = answer_question(catalog, about, value)
        assert r["found"] is False and "results" not in r, (value, r)
        assert r["message"] == f"'{value}' isn't a {about} name. Pass just the name.", r["message"]


@pytest.mark.parametrize("value", ["not Dr. Chen", "another doctor", "anywhere but Downtown", "No, not Dr. Chen",
                                   "someone else", "the other one", "Dr. Chen please"])
def test_answer_question_spec_examples(catalog, value):
    for about in ("doctor", "location"):
        r = answer_question(catalog, about, value)
        assert r["found"] is False and r["message"].endswith("Pass just the name."), (about, value, r)


@pytest.mark.parametrize("name", sorted({x["name"] for x in PROV.values()}))
def test_answer_question_every_real_doctor_name_is_not_a_sentence(catalog, name):
    r = answer_question(catalog, "doctor", name)
    assert r["found"] is True and any(x["name"].startswith(name) for x in r["results"])


@pytest.mark.parametrize("name", sorted({l["name"] for l in LOC.values()} | set(EXTRAS["landmarks"])))
def test_answer_question_every_real_place_is_not_a_sentence(catalog, name):
    assert answer_question(catalog, "location", name)["found"] is True, name


def test_answer_question_does_not_read_place_phrases(catalog):
    """s1 applies here too: answer_question resolves place NAMES only."""
    for phrase in ("near Downtown", "the Midtown one", "on Geary", "Union Square area"):
        assert answer_question(catalog, "location", phrase)["found"] is False, phrase


# =============================================================== s6: weekday words
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
SHORT = {"mon": 0, "tue": 1, "tues": 1, "wed": 2, "thu": 3, "thur": 3, "thurs": 3, "fri": 4, "sat": 5, "sun": 6}
ACCEPTED = [(w, i) for i, w in enumerate(WEEKDAYS)] + [(w + "s", i) for i, w in enumerate(WEEKDAYS)] + \
           [(w.lower() + "s", i) for i, w in enumerate(WEEKDAYS)] + [(w.upper() + "S", i) for i, w in enumerate(WEEKDAYS)] + \
           list(SHORT.items()) + [(s.upper(), i) for s, i in SHORT.items()] + [(s.capitalize(), i) for s, i in SHORT.items()]
REFUSED = ["thus", "frid", "wednes", "mond", "monda", "tu", "th", "we", "fr", "sa", "su", "satur", "sund", "weds",
           "tuesd", "thursd", "thurss", "mondayss", "frday", "thrusday", "wensday", "mon.day", "m"]


def _skin_slots(schedule):
    return [(p, l, t) for p, l in sorted(ref_pairs(True, "appt_027"))
            for t in schedule.open_slots(p, l, VT["appt_027"]["duration_min"], NOW)]


@pytest.mark.parametrize("word,weekday", ACCEPTED)
def test_every_accepted_weekday_word(catalog, schedule, word, weekday):
    r = run(catalog, schedule, Preferences(days=[word]), vt="appt_027")
    assert "bad_input" not in kinds(r), (word, [n.say for n in r.notes])
    if any(t.weekday() == weekday for _, _, t in _skin_slots(schedule)):
        assert r.options and all(o.start.weekday() == weekday for o in r.options)
    else:
        assert r.options and kinds(r) == ["wish_impossible"] and WEEKDAYS[weekday] in r.notes[0].say


@pytest.mark.parametrize("word", REFUSED)
def test_every_other_weekday_word_is_refused(catalog, schedule, word):
    r = run(catalog, schedule, Preferences(days=[word]), vt="appt_027")
    assert refused(r), (word, [n.say for n in r.notes], [o.spoken for o in r.options])
    card = full_card()
    card.change_choice("time", word)
    assert refused(run(catalog, schedule, card.preferences, vt="appt_027")), word


# =============================================================== s6: repeated ids
def _catalog_problems(raw):
    with pytest.raises(CatalogError) as e:
        Catalog(raw, EXTRAS)
    return str(e.value)


@pytest.mark.parametrize("section", ["locations", "providers", "appointment_types"])
@pytest.mark.parametrize("copies", [2, 3, 5])
def test_a_repeated_catalog_id_is_reported_once(section, copies):
    raw = copy.deepcopy(RAW)
    first = raw[section][0]
    raw[section] += [copy.deepcopy(first) for _ in range(copies - 1)]
    text = _catalog_problems(raw)
    assert text.count(first["id"] + " appears more than once") == 1, text


@pytest.mark.parametrize("section", ["locations", "providers", "appointment_types"])
def test_two_different_repeated_ids_are_each_reported_once(section):
    raw = copy.deepcopy(RAW)
    a, b = raw[section][0], raw[section][1]
    raw[section] += [copy.deepcopy(a), copy.deepcopy(a), copy.deepcopy(b), copy.deepcopy(b), copy.deepcopy(b)]
    text = _catalog_problems(raw)
    assert text.count("appears more than once") == 2, text
    assert text.count(a["id"] + " appears") == 1 and text.count(b["id"] + " appears") == 1


@pytest.mark.parametrize("variant", [" {}", "{} ", "  {}  ", "\t{}"])
def test_catalog_ids_are_compared_without_surrounding_spaces(variant):
    raw = copy.deepcopy(RAW)
    twin = copy.deepcopy(raw["appointment_types"][0])
    twin["id"] = variant.format(twin["id"])
    raw["appointment_types"].append(twin)
    text = _catalog_problems(raw)
    assert text.count("appears more than once") == 1, text


def _patient_problems(records):
    with pytest.raises(CatalogError) as e:
        PatientDirectory(records)
    return str(e.value)


@pytest.mark.parametrize("copies", [2, 3, 6])
def test_a_repeated_patient_id_is_reported_once(copies):
    recs = copy.deepcopy(PATIENTS) + [dict(copy.deepcopy(PATIENTS[0]), name=f"Other Person{i}") for i in range(copies - 1)]
    text = _patient_problems(recs)
    assert text.count("appears more than once") == 1, text


@pytest.mark.parametrize("variant", [" {}", "{} ", "  {}  "])
def test_patient_ids_are_compared_without_surrounding_spaces(variant):
    twin = dict(copy.deepcopy(PATIENTS[1]), id=variant.format(PATIENTS[1]["id"]))
    text = _patient_problems(copy.deepcopy(PATIENTS) + [twin])
    assert text.count("appears more than once") == 1, text


def test_the_real_files_still_load():
    Catalog(RAW, EXTRAS)
    PatientDirectory(PATIENTS)
