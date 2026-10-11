"""Catalog loading and search: specialties, doctor names (with match quality), places.

Regression tests for review findings are marked with the triage item number (#N),
see docs/reviews/2026-10-06-rules-module/triage.md.
"""

import copy
import json

import pytest

from catalog_ids import (
    DOWNTOWN, GRACE_RODRIGUEZ, MIDTOWN, MISSION_BAY, MISSION_DISTRICT, NORTH_BEACH, NORTH_GATE, RICHMOND, SUNSET,
)
from clinic import Catalog, CatalogError
from clinic.catalog import DATA_DIR

RAW = json.loads((DATA_DIR / "catalog.json").read_text(encoding="utf-8"))
EXTRAS = json.loads((DATA_DIR / "location_extras.json").read_text(encoding="utf-8"))


def test_21_specialties_each_small(catalog):
    specs = catalog.specialties()
    assert len(specs) == 21
    # The AI only ever sees one specialty's visit types at a time: keep that small.
    assert max(len(catalog.visit_types_in(s)) for s in specs) <= 8


@pytest.mark.parametrize("said,expected", [
    ("OBGYN", "OB/GYN"), ("ob-gyn", "OB/GYN"), ("dermatology", "Dermatology"), ("nuerology", "Neurology"),
    # 17: the words people use for the doctor, not the department
    ("dermatologist", "Dermatology"), ("pediatrician", "Pediatrics"), ("cardiologists", "Cardiology"),
    ("allergist", "Allergy/Immunology"), ("Allergy", "Allergy/Immunology"), ("physical therapist", "Physical Therapy"),
    ("dentist", "Dental"), ("orthopedist", "Orthopedics"),
    ("astrology", None), ("banana", None), ("", None), ("physician", None),  # R2-9: not Physical Therapy
    # R3-2: other doctors' words must NOT land on a look-alike specialty
    ("podiatrist", None), ("hematologist", None), ("nephrologist", None), ("audiologist", None),
    ("generalist", None),
])
def test_specialty_wording(catalog, said, expected):
    assert catalog.match_specialty(said) == expected


def test_misheard_garcia_finds_all_garcias_and_says_it_is_a_guess(catalog):
    found = catalog.match_providers("Dr. Garsha")
    assert sorted(m.provider.name for m in found) == ["Dr. Carlos Garcia", "Dr. Maria Garcia", "Dr. Maria Garcia"]
    assert not any(m.is_exact for m in found)  # 4: reported as approximate


def test_duplicate_names_return_every_match(catalog):
    marias = catalog.find_providers_by_name("Dr. Maria Garcia")
    assert len(marias) == 2
    assert {p.specialty for p in marias} == {"Pediatrics", "Family Medicine"}
    assert len(catalog.find_providers_by_name("Linda Ramirez")) == 2
    assert len(catalog.find_providers_by_name("Doctor Michael Sato")) == 2


def test_name_matching_edge_cases(catalog):
    # 4: an exact first name beats a sounds-alike surname ("Grace" also sounds like "Garcia")
    assert [p.id for p in catalog.find_providers_by_name("Dr. Grace")] == [GRACE_RODRIGUEZ]
    # 4: a possessive from speech-to-text
    assert len(catalog.find_providers_by_name("Dr. Garcia's")) == 3
    # 4: a wrong first name falls back to the surname, clearly labelled
    fallback = catalog.match_providers("Dr. John Garcia")
    assert len(fallback) == 3 and not any(m.first_name_matched for m in fallback)
    # 4: a different name that's merely close is labelled close, not exact
    cohen = catalog.match_providers("Dr. Cohen")
    assert cohen and all(m.describe() == "close spelling" for m in cohen)


# Round 6 (Farhaan's decision): the AI passes a place NAME plus near = yes/no. Names are
# matched forgivingly against our list; "near" is never read from the words.
@pytest.mark.parametrize("name,near,kind,locs", [
    ("Downtown", True, "location", [DOWNTOWN]),                       # "closer to Downtown" (baseline caller)
    ("Mission Bay", False, "location", [MISSION_BAY]),                # "the Mission Bay one"
    ("Mission District", False, "location", [MISSION_DISTRICT]),
    ("Mission", False, "ambiguous", [MISSION_BAY, MISSION_DISTRICT]),
    ("the Mission", False, "ambiguous", [MISSION_BAY, MISSION_DISTRICT]),  # Farhaan's decision: ask
    ("North", False, "ambiguous", [NORTH_BEACH, NORTH_GATE]),
    ("the Marina District", False, "location", [NORTH_GATE]),        # 3: was taken as Mission District
    ("Richmond District", False, "location", [RICHMOND]),            # 3: was unrecognised
    ("Hayes Valley", False, "location", [MIDTOWN]),                  # 17: neighbourhood as a name
    ("Hayes Valley", True, "location", [MIDTOWN]),                   # ...near only ranks
    ("Mission Street", True, "location", [NORTH_BEACH]),             # 3: 481 Mission St, not Mission District
    ("Geary Street", False, "ambiguous", [DOWNTOWN, SUNSET]),        # 17: "the one on Geary"
    ("Downtown SF", False, "location", [DOWNTOWN]),
    ("mid town", False, "location", [MIDTOWN]),
    ("4874 Main St", False, "location", [MISSION_BAY]),              # R3-9: a full address
    ("4455 Geary Blvd", False, "location", [DOWNTOWN]),               # the number settles a shared street
])
def test_places(catalog, name, near, kind, locs):
    m = catalog.resolve_place(name, near=near)
    assert (m.kind, sorted(m.location_ids), m.near) == (kind, sorted(locs), near)


@pytest.mark.parametrize("name,landmark", [("Castro", "Castro"), ("the Castro", "Castro"),
                                           ("Castro District", "Castro"), ("fishermans wharf", "Fisherman's Wharf")])
def test_landmarks(catalog, name, landmark):
    m = catalog.resolve_place(name)
    assert m.kind == "landmark" and m.label == landmark and m.near   # a landmark is never a clinic


@pytest.mark.parametrize("phrase", ["near Downtown", "closer to Downtown", "the Midtown one", "on Geary",
                                    "Union Square area", "the Midtown one in SF", "Geary", "main",
                                    # round 7: words that aren't in any of our place names
                                    "Midtown office", "Downtown location", "Sunset hospital", "Richmond branch"])
def test_r6_place_phrases_are_not_read(catalog, phrase):
    # The AI passes the name and near; a whole phrase isn't a place name, so it isn't guessed at.
    assert catalog.resolve_place(phrase).kind == "none"


@pytest.mark.parametrize("hint", ["Narnia", "", "   ", None, "the clinic",
                                  # round 2, R2-3: short or partial words must NOT pick a place
                                  "the main one", "Bay Area", "Glen Park", "Cole Valley", "Marina Boulevard",
                                  "Valley", "Gate", "Square",
                                  # round 3, R3-9
                                  "Marin", "St Marys"])
def test_unknown_places_are_not_guessed(catalog, hint):
    assert catalog.resolve_place(hint).kind == "none"


@pytest.mark.parametrize("hint", ["anywhere", "no preference", "none", "don't mind", "I don't mind", "SF"])
def test_no_preference_is_not_a_place(catalog, hint):
    assert catalog.resolve_place(hint).kind == "any"


# ---- 7: bad data fails loudly at load instead of being papered over
def test_missing_coordinates_refused():
    extras = copy.deepcopy(EXTRAS)
    del extras["locations"][MIDTOWN]
    with pytest.raises(CatalogError, match=MIDTOWN):
        Catalog(RAW, extras)


def test_unreadable_opening_hours_refused():
    raw = copy.deepcopy(RAW)
    raw["locations"][0]["hours"] = "Monday-Friday 8am-5pm"
    with pytest.raises(CatalogError, match="opening hours"):
        Catalog(raw, EXTRAS)


def test_missing_fields_and_repeated_ids_refused():  # R2-11
    raw = copy.deepcopy(RAW)
    del raw["locations"][0]["hours"]
    raw["providers"].append(copy.deepcopy(raw["providers"][0]))
    with pytest.raises(CatalogError) as e:
        Catalog(raw, EXTRAS)
    assert "missing hours" in str(e.value) and "appears more than once" in str(e.value)


def test_wrong_kinds_of_value_refused():  # R3-9
    raw = copy.deepcopy(RAW)
    raw["appointment_types"][0]["duration_min"] = "abc"
    raw["providers"][0]["languages"] = None
    raw["providers"][1]["location_ids"] = "loc_000"
    with pytest.raises(CatalogError) as e:
        Catalog(raw, EXTRAS)
    msg = str(e.value)
    assert "duration_min should be whole number" in msg and "languages should be list of text" in msg
    assert "location_ids should be list of text" in msg


def test_unknown_ids_refused():
    raw = copy.deepcopy(RAW)
    raw["providers"][0]["location_ids"].append("loc_999")
    raw["providers"][1]["appointment_type_ids"].append("appt_999")
    with pytest.raises(CatalogError) as e:
        Catalog(raw, EXTRAS)
    assert "loc_999" in str(e.value) and "appt_999" in str(e.value)


# ---- round 4 (triage.md, round 4 section): the data checks have no holes left
def _problems(raw=RAW, extras=EXTRAS) -> str:
    with pytest.raises(CatalogError) as e:
        Catalog(raw, extras)
    return str(e.value)


def test_r4_a_time_that_does_not_exist_is_a_catalog_error():
    raw = copy.deepcopy(RAW)
    raw["locations"][0]["hours"] = "Mon-Fri 8:00-25:00"
    assert "doesn't exist" in _problems(raw)


def test_r4_an_id_written_as_a_list_is_reported_not_a_crash():
    raw = copy.deepcopy(RAW)
    raw["providers"][0]["id"] = ["prov_001"]
    assert "id should be text" in _problems(raw)


def test_r4_capabilities_must_be_a_list():
    # As text, "imaging" would be read letter by letter and MRIs would quietly vanish.
    raw = copy.deepcopy(RAW)
    raw["locations"][0]["capabilities"] = "imaging"
    assert "capabilities should be list of text" in _problems(raw)


@pytest.mark.parametrize("lat", ["abc", "", None, 999, True])
def test_r4_map_points_must_be_real_coordinates(lat):
    extras = copy.deepcopy(EXTRAS)
    extras["locations"][MIDTOWN]["lat"] = lat
    assert f"Location {MIDTOWN} in location_extras.json: lat should be a latitude" in _problems(extras=extras)


def test_r4_landmarks_must_be_points():
    extras = copy.deepcopy(EXTRAS)
    extras["landmarks"]["Somewhere"] = "near the park"
    assert "Landmark 'Somewhere'" in _problems(extras=extras)


def test_r4_every_kind_of_problem_is_listed_in_one_go():
    raw, extras = copy.deepcopy(RAW), copy.deepcopy(EXTRAS)
    raw["locations"][1]["hours"] = "Mon-Fri 8:00-25:00"
    raw["providers"][0]["location_ids"].append("loc_999")
    del extras["locations"][MIDTOWN]
    msg = _problems(raw, extras)
    assert "doesn't exist" in msg and "loc_999" in msg and MIDTOWN in msg


def test_r4_a_house_number_we_do_not_have_is_somewhere_on_that_street(catalog):
    # "9999 Geary Street": the caller is on Geary, so both Geary clinics are relevant,
    # but neither is the place they named, so the search isn't narrowed to them.
    for said in ("9999 Geary Street", "9999 Geary Blvd"):
        place = catalog.resolve_place(said)
        assert (place.kind, sorted(place.location_ids), place.near) == ("ambiguous", [DOWNTOWN, SUNSET], True)
    assert catalog.resolve_place("4455 Geary Blvd").location_ids == [DOWNTOWN]


@pytest.mark.parametrize("word, specialty", [
    ("dentist", "Dental"), ("orthopedist", "Orthopedics"), ("pediatrician", "Pediatrics"),
    ("allergist", "Allergy/Immunology"), ("physical therapist", "Physical Therapy"), ("urologists", "Urology"),
])
def test_r4_doctor_words_regular_rule_plus_a_short_table(catalog, word, specialty):
    assert catalog.match_specialty(word) == specialty


def test_r5_one_no_preference_list():
    # Round 5: with plain time fields, "any day" just empties the day field, so the
    # separate "any day" list is gone and there is one list.
    from clinic import fuzzy
    from clinic.fuzzy import means_no_preference
    assert not hasattr(fuzzy, "ANY_DAY")
    assert all(means_no_preference(x) for x in ("Any day!", "any time works", "I don't mind", "whatever"))


def test_r5_an_empty_neighbourhood_is_fine():
    extras = copy.deepcopy(EXTRAS)
    extras["locations"][MIDTOWN]["neighbourhood"] = ""
    Catalog(RAW, extras)


def test_r6_a_repeated_id_is_reported_once():
    raw = copy.deepcopy(RAW)
    raw["providers"] += [copy.deepcopy(raw["providers"][0]) for _ in range(2)]
    assert _problems(raw).count("appears more than once") == 1


@pytest.mark.parametrize("name, loc", [("Sunset Clinic", SUNSET), ("Sunset Community Clinic", SUNSET),
                                       ("Mission Bay Health Center", MISSION_BAY), ("Richmond Care Center", RICHMOND)])
def test_r7_a_word_from_that_place_own_name_is_fine(catalog, name, loc):
    assert catalog.resolve_place(name).location_ids == [loc]


@pytest.mark.parametrize("name", ["Richmond clinic", "Downtown clinic", "Chinatown clinic", "Richmond Medical Group",
                                  "Midtown Health Center"])
def test_r7_a_word_from_another_place_name_is_not_borrowed(catalog, name):
    # Verifier's ruling (round 7): "clinic" counts only for a place whose own name has it.
    # "Chinatown clinic" must not quietly become "near Chinatown".
    assert catalog.resolve_place(name).kind == "none"


# ---------------------------------------------------------------- our visit-type notes (decision 79)
def _notes():
    import json as _json
    from clinic.catalog import DATA_DIR
    return _json.loads((DATA_DIR / "visit_type_notes.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("break_it, says", [
    (lambda n: n["groups"][0]["visit_types"].update(appt_999="x"), "appt_999 isn't a visit type"),
    (lambda n: n["groups"][1]["visit_types"].update(appt_027="again"), "appt_027 is in more than one group"),
    (lambda n: n["groups"][0].update(usual="appt_001"), "'usual' must be one of the group's visit types"),
    (lambda n: n["groups"][0]["visit_types"].update(appt_027="  "), "needs a one-line description"),
    (lambda n: n.pop("groups"), "has no 'groups' list"),
])
def test_visit_type_notes_are_checked_at_load(break_it, says):
    notes = _notes()
    break_it(notes)
    with pytest.raises(CatalogError, match=says):
        Catalog(RAW, EXTRAS, notes)


def test_every_look_alike_group_named_in_the_brief_has_descriptions():
    """The brief's data notes name Skin Cancer Screening vs Full Body Skin Exam and Annual
    Physical vs Annual Wellness Visit as look-alikes to handle."""
    c = Catalog(RAW, EXTRAS, _notes())
    by_name = {vt.name: vt for vt in c.visit_types.values()}
    for name in ("Skin Cancer Screening", "Full Body Skin Exam", "Annual Physical", "Annual Wellness Visit"):
        assert by_name[name].description, name
    assert sum(vt.usual for vt in c.visit_types.values()) == len(_notes()["groups"])
