"""Independent reviewer's tests for backend/evals/. Run from backend/:

    python3 -m pytest -q -p no:cacheprovider ../../out/tests      (adjust the path)

or from anywhere, with backend/ on the import path:

    PYTHONPATH=/home/claude/review/repo/backend python3 -m pytest -q -p no:cacheprovider /home/claude/review/out/tests

Tests named test_finding_* describe the CORRECT behaviour and FAIL on the code as reviewed:
each one is evidence for a numbered finding in review.md. Tests named test_ok_* pass and
document something checked and found fine.
"""

import sys
from pathlib import Path

import pytest

BACKEND = Path("/home/claude/review/repo/backend")
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from clinic import Catalog, PatientDirectory  # noqa: E402


@pytest.fixture(scope="session")
def catalog():
    return Catalog.load()


@pytest.fixture(scope="session")
def patients():
    return PatientDirectory.load()
