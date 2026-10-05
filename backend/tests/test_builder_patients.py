"""Identity: a returning patient is name + date of birth (Farhaan's decision, triage #2)."""

import pytest

from catalog_ids import JAMES_WILSON


def test_name_and_date_of_birth_identify(patients):
    r = patients.lookup(*JAMES_WILSON)
    assert r.status == "found"
    assert not r.caller.is_new_patient and "Radiology" in r.caller.referrals_on_file


@pytest.mark.parametrize("heard", ["James Willson", "james wilson", "  James   Wilson. "])
def test_misheard_name_still_found_with_date_of_birth(patients, heard):
    assert patients.lookup(heard, JAMES_WILSON[1]).status == "found"


def test_name_alone_asks_for_date_of_birth(patients):
    r = patients.lookup("James Wilson")
    assert r.status == "need_date_of_birth" and r.caller is None


def test_wrong_date_of_birth_is_not_quietly_a_new_patient(patients):
    r = patients.lookup("James Wilson", "1984-03-13")
    assert r.status == "dob_mismatch" and r.caller is None


def test_badly_written_date_of_birth(patients):
    assert patients.lookup("James Wilson", "12/03/1984").status == "invalid_date_of_birth"


@pytest.mark.parametrize("heard", [
    "Mr. Wilson", "Dr Wilson", "Wilson",   # a surname alone (titles don't count as a first name)
    "Robert Tyler",                        # a different surname, only close-ish to Taylor
    "Ahmad Kim",                           # only "sounds like" Khan
    "Farhan Jida", "", None,
])
def test_these_are_not_returning_patients(patients, heard):
    assert patients.lookup(heard, "1962-05-08").status == "not_found"


def test_swapped_letters_in_surname_still_match(patients):
    assert patients.lookup("Ahmed Kahn", "1991-11-02").status == "found"


def test_returned_caller_does_not_share_its_list_with_the_record(patients):
    a = patients.lookup(*JAMES_WILSON).caller
    a.referrals_on_file.append("Cardiology")
    assert "Cardiology" not in patients.lookup(*JAMES_WILSON).caller.referrals_on_file
