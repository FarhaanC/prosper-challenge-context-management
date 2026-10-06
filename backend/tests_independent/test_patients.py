"""Fake patient lookup (decision 29): first AND last name must match (forgivingly);
surname alone does not identify; date of birth separates same names; unknown = new."""

import json

import pytest

from clinic import PatientDirectory
from reference import DATA

RECORDS = json.loads((DATA / "patients.json").read_text())["patients"]
DOB = {r["id"]: r["date_of_birth"] for r in RECORDS}  # round 2: identity is name AND date of birth


def test_six_patients():
    assert len(RECORDS) == 6


@pytest.mark.parametrize("rec", RECORDS, ids=[r["name"] for r in RECORDS])
def test_exact_name_found_with_referrals(directory, rec):
    # round 3 s1: date of birth is a required argument; missing -> "incomplete"
    assert directory.lookup(rec["name"], None).status == "incomplete"
    r = directory.lookup(rec["name"], rec["date_of_birth"])
    assert r.status == "found"
    assert r.caller.patient_id == rec["id"]
    assert r.caller.is_new_patient is False
    assert sorted(r.caller.referrals_on_file) == sorted(rec["referrals_on_file"])


@pytest.mark.parametrize("heard,pid", [
    ("james wilson", "pat_001"), ("JAMES WILSON", "pat_001"), ("James Willson", "pat_001"),
    ("Sara Jonson", "pat_002"), ("Ahmed Kahn", "pat_003"), ("Emily Browne", "pat_004"),
    ("Robert Tailor", "pat_005"), ("  James   Wilson  ", "pat_001"), ("James Wilson.", "pat_001"),
])
def test_misheard_names_found(directory, heard, pid):
    assert directory.lookup(heard, None).status == "incomplete"  # round 3 s1
    r = directory.lookup(heard, DOB[pid])
    assert r.status == "found" and r.caller.patient_id == pid


@pytest.mark.parametrize("heard", ["Wilson", "James", "Khan", "Emily"])
def test_single_word_does_not_identify(directory, heard):
    # round 3 s1: fewer than two words -> "incomplete", nothing looked up, whatever the date
    for dob in [None] + list(DOB.values()):
        assert directory.lookup(heard, dob).status == "incomplete", (heard, dob)


@pytest.mark.parametrize("heard", ["Mr. Wilson", "Mrs. Johnson", "Ms Brown", "Mr Khan", "Mr. Taylor"])
def test_title_plus_surname_does_not_identify(directory, heard):
    """A title is not a first name: 'Mr. Wilson' is still a surname alone."""
    for dob in [None] + list(DOB.values()):  # round 3 s1: titles don't count as words
        assert directory.lookup(heard, dob).status == "incomplete", (heard, dob)


@pytest.mark.parametrize("heard", ["Farhan Jida", "John Smith", "James Watson", "Sarah Jones", "", None])
def test_unknown_is_not_found(directory, heard):
    # round 3 s1: two-word unknown name + a real patient's date -> not_found; blank name -> incomplete
    want = "not_found" if len(str(heard or "").split()) >= 2 else "incomplete"
    for dob in DOB.values():
        assert directory.lookup(heard, dob).status == want, (heard, dob)


def test_date_of_birth_confirms_and_rejects(directory):
    assert directory.lookup("James Wilson", "1984-03-12").status == "found"
    assert directory.lookup("James Wilson", "1999-01-01").status != "found"


def test_same_name_needs_date_of_birth():
    d = PatientDirectory([
        {"id": "a", "name": "John Smith", "date_of_birth": "1980-01-01", "referrals_on_file": ["Radiology"]},
        {"id": "b", "name": "John Smith", "date_of_birth": "1990-02-02", "referrals_on_file": []},
    ])
    r = d.lookup("John Smith", None)
    # round 3 s1: name only -> "incomplete"; no candidate list (privacy)
    assert r.status == "incomplete" and r.caller is None and not hasattr(r, "candidates")
    r = d.lookup("John Smith", "1990-02-02")
    assert r.status == "found" and r.caller.patient_id == "b" and r.caller.referrals_on_file == []
    r = d.lookup("Jon Smyth", "1980-01-01")
    assert r.status == "found" and r.caller.patient_id == "a"


def test_returned_caller_does_not_share_list_with_record(directory):
    r = directory.lookup("James Wilson", "1984-03-12")
    r.caller.referrals_on_file.append("Cardiology")
    again = directory.lookup("James Wilson", "1984-03-12")
    assert "Cardiology" not in again.caller.referrals_on_file


def test_different_surname_not_matched_by_sound_alone(directory):
    """Judgement call: 'Kim' and 'Khan' are different surnames that only share a
    'sounds-alike' code. Identifying 'Ahmad Kim' as Ahmed Khan would hand a stranger
    Ahmed Khan's record and his Dermatology referral."""
    assert directory.lookup("Ahmad Kim", DOB["pat_003"]).status == "not_found"  # round 3: with Khan's real DOB
