import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # so `import clinic` works

from clinic import Caller, Catalog, PatientDirectory, Schedule  # noqa: E402

# A fixed "now" (Tuesday 6 Oct 2026, 9 AM) so every run sees the same open times.
NOW = datetime(2026, 10, 6, 9, 0)


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
    return patients.lookup("James Wilson").caller


@pytest.fixture
def emily(patients):
    """Returning patient with no referrals."""
    return patients.lookup("Emily Brown").caller


# Handy catalog ids
SKIN_CANCER_SCREENING = "appt_027"
ANNUAL_PHYSICAL = "appt_002"
KNEE_MRI = "appt_065"
OBGYN_TYPES = ["appt_040", "appt_041", "appt_042", "appt_043", "appt_044"]
NO_DOCTOR_TYPES = ["appt_045", "appt_046", "appt_047", "appt_048", "appt_049", "appt_070", "appt_071", "appt_077"]
DOWNTOWN, MIDTOWN, MISSION_BAY, MISSION_DISTRICT = "loc_004", "loc_005", "loc_000", "loc_001"
LINDA_RAMIREZ_RADIOLOGY, HANNAH_NGUYEN = "prov_014", "prov_015"
