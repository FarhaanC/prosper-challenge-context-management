"""Shared fixtures for the builder's tests. Constants live in catalog_ids.py."""

import pytest

from catalog_ids import EMILY_BROWN, JAMES_WILSON
from clinic import Caller, Catalog, PatientDirectory, Schedule


@pytest.fixture(scope="session")
def catalog():
    return Catalog.load()


@pytest.fixture(scope="session")
def patients():
    return PatientDirectory.load()


@pytest.fixture
def schedule(catalog):
    return Schedule(catalog)


@pytest.fixture
def new_caller():
    return Caller(name="Farhan Jida")


@pytest.fixture
def james(patients):
    """Returning patient with a Radiology referral (the knee MRI demo path)."""
    return patients.lookup(*JAMES_WILSON).caller


@pytest.fixture
def emily(patients):
    """Returning patient with no referrals."""
    return patients.lookup(*EMILY_BROWN).caller
