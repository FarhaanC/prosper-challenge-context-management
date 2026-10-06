"""Identity: name + date of birth, the same reply for every miss, spelling as the
third try, then a choice of registering as new or speaking to staff.
(Farhaan's decisions: round-1 triage #2, round-2 triage R2-4.)"""

import pytest

from catalog_ids import EMILY_BROWN, JAMES_WILSON
from clinic import IdentityCheck, PatientDirectory


def test_name_and_date_of_birth_identify(patients):
    r = patients.lookup(*JAMES_WILSON)
    assert r.status == "found"
    assert not r.caller.is_new_patient and "Radiology" in r.caller.referrals_on_file


@pytest.mark.parametrize("heard", ["James Willson", "james wilson", "  James   Wilson. ", "James Wilson Jr"])
def test_small_mishearings_still_found(patients, heard):
    assert patients.lookup(heard, JAMES_WILSON[1]).status == "found"


def test_nothing_is_looked_up_without_both(patients):
    # The reply must not depend on whether the name exists, so a real and a made-up
    # name get the same answer when the date of birth is missing.
    assert patients.lookup("James Wilson", None).status == "incomplete"
    assert patients.lookup("Nobody Real", None).status == "incomplete"
    assert patients.lookup("Wilson", JAMES_WILSON[1]).status == "incomplete"     # surname alone
    assert patients.lookup("Mr. Wilson", JAMES_WILSON[1]).status == "incomplete"  # titles don't count
    assert patients.lookup("James Wilson", "12/03/1984").status == "incomplete"   # not YYYY-MM-DD


def test_wrong_name_and_wrong_date_get_the_same_answer(patients):
    assert patients.lookup("James Wilson", "1984-03-13").status == "not_found"   # real name, wrong date
    assert patients.lookup("Nobody Real", JAMES_WILSON[1]).status == "not_found"  # made-up name


@pytest.mark.parametrize("heard", ["Robert Tyler", "Ahmad Kim", "Farhan Jida"])
def test_these_are_not_returning_patients(patients, heard):
    for dob in ("1962-05-08", "1991-11-02"):
        assert patients.lookup(heard, dob).status == "not_found"


def test_spelled_last_name_rescues_a_misheard_name(patients):
    assert patients.lookup("Emily Braun", EMILY_BROWN[1]).status == "not_found"
    assert patients.lookup("Emily Braun", EMILY_BROWN[1], spelled_last_name="B R O W N").status == "found"
    # one misheard letter is still fine; two are not
    assert patients.lookup("Emily Braun", EMILY_BROWN[1], spelled_last_name="B-R-O-W-M").status == "found"
    assert patients.lookup("Emily Braun", EMILY_BROWN[1], spelled_last_name="BRAWM").status == "not_found"


def test_same_name_and_birthday_goes_to_staff():
    d = PatientDirectory([
        {"id": "a", "name": "John Smith", "date_of_birth": "1980-01-01"},
        {"id": "b", "name": "John Smith", "date_of_birth": "1980-01-01"},
        {"id": "c", "name": "John Smith", "date_of_birth": "1990-02-02"},
    ])
    assert d.lookup("John Smith", "1980-01-01").status == "same_name_and_birthday"
    assert d.lookup("John Smith", "1990-02-02").caller.patient_id == "c"


def test_the_steps_in_order(patients):
    check = IdentityCheck()
    assert check.attempt(patients, "James Wilson", None).status == "need_both"   # doesn't count as a try
    assert check.attempt(patients, "Emily Braun", EMILY_BROWN[1]).status == "try_again"
    assert check.attempt(patients, "Emily Braun", EMILY_BROWN[1]).status == "spell_last_name"
    # the third try must be spelled
    assert check.attempt(patients, "Emily Braun", EMILY_BROWN[1]).status == "spell_last_name"
    step = check.attempt(patients, "Emily Braun", EMILY_BROWN[1], spelled_last_name="BROWN")
    assert step.status == "found" and step.caller.name == "Emily Brown"


def test_after_spelling_fails_the_caller_chooses(patients):
    check = IdentityCheck()
    check.attempt(patients, "Mei Wang", "2000-01-01")
    check.attempt(patients, "Mei Wang", "2000-01-01")
    step = check.attempt(patients, "Mei Wang", "2000-01-01", spelled_last_name="WANG")
    assert step.status == "offer_new_or_staff"
    assert "register as a new patient" in step.say and "member of staff" in step.say


def test_returned_caller_does_not_share_its_list_with_the_record(patients):
    a = patients.lookup(*JAMES_WILSON).caller
    a.referrals_on_file.append("Cardiology")
    assert "Cardiology" not in patients.lookup(*JAMES_WILSON).caller.referrals_on_file
