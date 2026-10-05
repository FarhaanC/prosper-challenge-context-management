"""Search: specialties, misheard doctor names, duplicate names, places, patients."""

from conftest import DOWNTOWN, MISSION_BAY, MISSION_DISTRICT


def test_21_specialties_each_small(catalog):
    specs = catalog.specialties()
    assert len(specs) == 21
    # The AI only ever sees one specialty's visit types at a time: keep that small.
    assert max(len(catalog.visit_types_in(s)) for s in specs) <= 8


def test_specialty_wording_is_forgiven(catalog):
    assert catalog.match_specialty("OBGYN") == "OB/GYN"
    assert catalog.match_specialty("ob-gyn") == "OB/GYN"
    assert catalog.match_specialty("dermatology") == "Dermatology"
    assert catalog.match_specialty("astrology") is None


def test_misheard_garcia_finds_all_garcias(catalog):
    found = catalog.find_providers_by_name("Dr. Garsha")
    assert sorted(p.name for p in found) == ["Dr. Carlos Garcia", "Dr. Maria Garcia", "Dr. Maria Garcia"]


def test_duplicate_names_return_every_match(catalog):
    marias = catalog.find_providers_by_name("Dr. Maria Garcia")
    assert len(marias) == 2
    assert {p.specialty for p in marias} == {"Pediatrics", "Family Medicine"}
    assert len(catalog.find_providers_by_name("Linda Ramirez")) == 2
    assert len(catalog.find_providers_by_name("Doctor Michael Sato")) == 2


def test_places(catalog):
    near = catalog.resolve_place("near Downtown")
    assert near.kind == "location" and near.location_ids == [DOWNTOWN] and near.near

    the_one = catalog.resolve_place("the Mission Bay one")
    assert the_one.kind == "location" and the_one.location_ids == [MISSION_BAY] and not the_one.near

    # "Mission" fits two locations: we must ask, not guess.
    amb = catalog.resolve_place("Mission")
    assert amb.kind == "ambiguous" and set(amb.location_ids) == {MISSION_BAY, MISSION_DISTRICT}

    assert catalog.resolve_place("near the Castro").kind == "landmark"
    assert catalog.resolve_place("Narnia").kind == "none"


def test_patient_lookup_forgives_spelling(patients):
    r = patients.lookup("James Willson")
    assert r.status == "found"
    assert not r.caller.is_new_patient and "Radiology" in r.caller.referrals_on_file


def test_unknown_or_partial_names_are_not_matched(patients):
    assert patients.lookup("Farhan Jida").status == "not_found"
    assert patients.lookup("Wilson").status == "not_found"  # surname alone is too weak
