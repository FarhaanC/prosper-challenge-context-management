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
    ("astrology", None), ("banana", None), ("", None),
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


@pytest.mark.parametrize("hint", ["Narnia", "", "   ", None, "the clinic"])
def test_unknown_places_are_not_guessed(catalog, hint):
    assert catalog.resolve_place(hint).kind == "none"


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


def test_unknown_ids_refused():
    raw = copy.deepcopy(RAW)
    raw["providers"][0]["location_ids"].append("loc_999")
    raw["providers"][1]["appointment_type_ids"].append("appt_999")
    with pytest.raises(CatalogError) as e:
        Catalog(raw, EXTRAS)
    assert "loc_999" in str(e.value) and "appt_999" in str(e.value)
