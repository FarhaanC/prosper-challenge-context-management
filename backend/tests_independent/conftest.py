"""Shared setup for the independent tests.

Expected answers in these tests come from the spec and from the raw
catalog.json (see reference.py), never from the module's own code.
"""

import sys
from datetime import datetime
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from clinic import Catalog, Caller, PatientDirectory, Schedule  # noqa: E402

# Tuesday 6 Oct 2026, 09:00
NOW = datetime(2026, 10, 6, 9, 0)


@pytest.fixture(scope="session")
def catalog():
    return Catalog.load()


@pytest.fixture
def schedule(catalog):
    return Schedule(catalog)


@pytest.fixture(scope="session")
def directory():
    return PatientDirectory.load()


def new_caller(name="Farhan Jida"):
    return Caller(name=name, patient_id=None, is_new_patient=True, referrals_on_file=[])


def returning(refs=(), name="Test Returning"):
    return Caller(name=name, patient_id="pat_x", is_new_patient=False, referrals_on_file=list(refs))
