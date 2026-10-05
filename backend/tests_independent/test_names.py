"""Forgiving doctor-name matching. Spec: 'Garsha' still finds Garcia; always return
ALL matches for duplicate names."""

import pytest

from reference import PROV, first_name, last_name


def ids(lst):
    return {p.id for p in lst}


def with_full(full):
    return {pid for pid, p in PROV.items() if p["name"] == full}


def with_last(last):
    return {pid for pid, p in PROV.items() if last_name(p["name"]) == last}


def with_first(first):
    return {pid for pid, p in PROV.items() if first_name(p["name"]) == first}


def test_maria_garcia_two_results(catalog):
    assert ids(catalog.find_providers_by_name("Dr. Maria Garcia")) == {"prov_002", "prov_003"}


@pytest.mark.parametrize("heard", ["Garcia", "Dr. Garcia", "Dr. Garsha", "doctor garsia", "GARCIA", "dr garcia."])
def test_garcia_variants_find_all_three_garcias(catalog, heard):
    assert ids(catalog.find_providers_by_name(heard)) == {"prov_002", "prov_003", "prov_008"}


def test_every_full_name_returns_exactly_its_holders(catalog):
    bad = {}
    for full in {p["name"] for p in PROV.values()}:
        got = ids(catalog.find_providers_by_name(full))
        if got != with_full(full):
            bad[full] = got
    assert not bad


def test_every_surname_returns_all_holders(catalog):
    bad = {}
    for last in {last_name(p["name"]) for p in PROV.values()}:
        got = ids(catalog.find_providers_by_name(f"Dr. {last}"))
        if got != with_last(last):
            bad[last] = got
    assert not bad


def test_every_first_name_alone_finds_its_holders(catalog):
    """'Dr. Grace' or 'Dr. Olivia' heard alone: the doctors with that first name
    must be among the results (spec: return all matches so the agent can ask)."""
    bad = {}
    for first in {first_name(p["name"]) for p in PROV.values()}:
        got = ids(catalog.find_providers_by_name(f"Dr. {first}"))
        if not with_first(first) <= got:
            bad[first] = sorted(got)
    assert not bad, bad


@pytest.mark.parametrize("heard,last", [
    ("Dr. Ramires", "Ramirez"), ("Dr. Nyugen", "Nguyen"), ("Dr. Hernandes", "Hernandez"),
    ("Dr. Martines", "Martinez"), ("Dr. Smyth", "Smith"), ("Dr. Patell", "Patel"),
    ("Dr. Soto", "Sato"), ("Dr. Chenn", "Chen"), ("Dr. Rodrigues", "Rodriguez"),
])
def test_misheard_surnames(catalog, heard, last):
    assert ids(catalog.find_providers_by_name(heard)) == with_last(last)


def test_misheard_full_name(catalog):
    assert ids(catalog.find_providers_by_name("Dr. Mary Garsha")) == {"prov_002", "prov_003"}
    assert ids(catalog.find_providers_by_name("Linda Ramires")) == {"prov_005", "prov_014"}


@pytest.mark.parametrize("heard", ["Dr. Brown", "Dr. House", "Dr. Zhivago", "", "Dr.", "the dermatologist",
                                   None])
def test_names_that_should_not_match(catalog, heard):
    assert catalog.find_providers_by_name(heard) == []


def test_carlos_garcia_not_returned_for_maria_garcia(catalog):
    assert "prov_008" not in ids(catalog.find_providers_by_name("Maria Garcia"))


def test_seven_chens_all_returned(catalog):
    assert len(catalog.find_providers_by_name("Dr. Chen")) == 7
