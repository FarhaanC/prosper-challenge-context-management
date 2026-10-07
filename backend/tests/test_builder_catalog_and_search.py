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


@pytest.mark.parametrize("hint,kind,locs,near", [
    ("near Downtown", "location", [DOWNTOWN], True),
    ("closer to Downtown", "location", [DOWNTOWN], True),           # 3: the baseline caller's own words
    ("the one near Downtown", "location", [DOWNTOWN], True),
    ("the Mission Bay one", "location", [MISSION_BAY], False),
    ("the Mission District one", "location", [MISSION_DISTRICT], False),
    ("Mission", "ambiguous", [MISSION_BAY, MISSION_DISTRICT], False),
    ("the Mission", "ambiguous", [MISSION_BAY, MISSION_DISTRICT], False),  # Farhaan's decision: ask
    ("North", "ambiguous", [NORTH_BEACH, NORTH_GATE], False),
    ("the Marina District", "location", [NORTH_GATE], False),        # 3: was taken as Mission District
    ("Richmond District", "location", [RICHMOND], False),            # 3: was unrecognised
    ("the Hayes Valley one", "location", [MIDTOWN], False),          # 17: neighbourhood as a name
    ("near Hayes Valley", "location", [MIDTOWN], True),              # ...but "near" still only ranks
    ("near Mission Street", "location", [NORTH_BEACH], True),        # 3: 481 Mission St, not Mission District
    ("the one on Geary", "ambiguous", [DOWNTOWN, SUNSET], False),    # 17: street names
])
def test_places(catalog, hint, kind, locs, near):
    m = catalog.resolve_place(hint)
    assert (m.kind, sorted(m.location_ids), m.near) == (kind, sorted(locs), near)


@pytest.mark.parametrize("hint,landmark", [("near the Castro", "Castro"), ("Castro District", "Castro"),
                                           ("fishermans wharf", "Fisherman's Wharf")])
def test_landmarks(catalog, hint, landmark):
    m = catalog.resolve_place(hint)
    assert m.kind == "landmark" and m.label == landmark and m.near


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


@pytest.mark.parametrize("hint,loc,near", [
    ("on the way to Downtown", DOWNTOWN, True), ("on Main", MISSION_BAY, False),
    ("Downtown SF", DOWNTOWN, False), ("mid town", MIDTOWN, False),
    # round 3, R3-9: full addresses (the number settles shared streets), "in", "near <street>"
    ("4874 Main St", MISSION_BAY, False), ("4455 Geary Blvd", DOWNTOWN, False),
    ("the Midtown one in SF", MIDTOWN, False), ("downtown in San Francisco", DOWNTOWN, False),
])
def test_round_2_place_phrasings(catalog, hint, loc, near):
    m = catalog.resolve_place(hint)
    assert (m.kind, m.location_ids, m.near) == ("location", [loc], near)


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
    # "near 9999 Geary": the caller is on Geary, so both Geary clinics are relevant,
    # but neither is the place they named, so the search isn't narrowed to them.
    for said in ("near 9999 Geary", "9999 Geary Blvd"):
        place = catalog.resolve_place(said)
        assert (place.kind, sorted(place.location_ids), place.near) == ("ambiguous", [DOWNTOWN, SUNSET], True)
    assert catalog.resolve_place("4455 Geary Blvd").location_ids == [DOWNTOWN]


@pytest.mark.parametrize("word, specialty", [
    ("dentist", "Dental"), ("orthopedist", "Orthopedics"), ("pediatrician", "Pediatrics"),
    ("allergist", "Allergy/Immunology"), ("physical therapist", "Physical Therapy"), ("urologists", "Urology"),
])
def test_r4_doctor_words_regular_rule_plus_a_short_table(catalog, word, specialty):
    assert catalog.match_specialty(word) == specialty


def test_r4_one_no_preference_list_and_a_separate_any_day_list():
    from clinic.fuzzy import ANY_DAY, NO_PREFERENCE, means_any_day, means_no_preference
    assert not NO_PREFERENCE & ANY_DAY   # so the order they're checked in can't matter
    assert means_any_day("Any day!") and not means_no_preference("any day")
    assert means_no_preference("any time works") and not means_any_day("any time works")
