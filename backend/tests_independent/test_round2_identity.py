"""Round 2, spec change 2: identity is name AND date of birth."""

import json

import pytest

from clinic import CatalogError, PatientDirectory
from reference import DATA

RECORDS = json.loads((DATA / "patients.json").read_text())["patients"]
DOB = {r["name"]: r["date_of_birth"] for r in RECORDS}
ID = {r["name"]: r["id"] for r in RECORDS}
ALL_NAMES = [r["name"] for r in RECORDS]
# round 3 s1: "There are no other statuses"
STATUSES = {"incomplete", "not_found", "found", "same_name_and_birthday"}
TITLES = {"mr", "mrs", "ms", "miss", "dr", "jr", "sr"}


def words(name):
    return [w for w in str(name or "").replace(".", " ").lower().split() if w not in TITLES]


def leaks(result):
    """Does any part of the result mention a record's name, id, date of birth or referrals?"""
    text = json.dumps(result.to_dict()) + " " + str(getattr(result, "message", ""))
    found = []
    for r in RECORDS:
        for bit in (r["name"], r["id"], r["date_of_birth"], *r["referrals_on_file"]):
            if bit and bit in text:
                found.append(bit)
    return found


@pytest.mark.parametrize("name", ALL_NAMES)
def test_found_with_name_and_dob(directory, name):
    r = directory.lookup(name, DOB[name])
    assert r.status == "found" and r.caller.patient_id == ID[name] and r.caller.is_new_patient is False


@pytest.mark.parametrize("name", ALL_NAMES)
def test_need_dob_gives_no_details(directory, name):
    for dob in (None, "", "   "):
        r = directory.lookup(name, dob)
        assert r.status == "incomplete" and r.caller is None  # round 3 s1
        assert not leaks(r), leaks(r)


@pytest.mark.parametrize("name", ALL_NAMES)
def test_wrong_dob_is_mismatch_not_new_patient(directory, name):
    r = directory.lookup(name, "2000-01-01")
    # round 3 s1: "Same answer whether the name or the date was wrong."
    assert r.status == "not_found" and r.caller is None
    assert not leaks(r), leaks(r)
    assert r.to_dict() == directory.lookup("Nobody Madeup", "2000-01-01").to_dict()


@pytest.mark.parametrize("dob", ["12/03/1984", "1984/03/12", "March 12 1984", "12 March 1984", "19840312",
                                 "1984-3-12", "84-03-12", "1984-03-12T00:00", "yesterday", "1984-03"])
def test_invalid_dob_format(directory, dob):
    r = directory.lookup("James Wilson", dob)
    assert r.status == "incomplete" and r.caller is None  # round 3 s1: "not written YYYY-MM-DD"
    assert not leaks(r), leaks(r)


def test_dob_with_spaces_around_is_fine(directory):
    assert directory.lookup("James Wilson", " 1984-03-12 ").status == "found"


def test_impossible_calendar_date_is_not_found_as_someone(directory):
    # well-formed but not a real date: must never be 'found'
    assert directory.lookup("James Wilson", "1984-02-30").status in ("incomplete", "not_found")  # round 3


def test_unknown_name_is_not_found_even_with_any_dob(directory):
    for dob, want in ((None, "incomplete"), ("1984-03-12", "not_found"), ("rubbish", "incomplete")):  # round 3
        r = directory.lookup("Farhan Jida", dob)
        assert r.status == want and r.caller is None


def test_another_patients_dob_does_not_unlock(directory):
    # James Wilson's name with Sarah Johnson's date of birth
    r = directory.lookup("James Wilson", DOB["Sarah Johnson"])
    assert r.status == "not_found" and r.caller is None  # round 3 s1


@pytest.mark.parametrize("heard,who", [
    ("Ahmed Kahn", "Ahmed Khan"), ("James Willson", "James Wilson"), ("Sara Jonson", "Sarah Johnson"),
    ("Robert Tailor", "Robert Taylor"), ("Emily Browne", "Emily Brown"), ("JAMES WILSON", "James Wilson"),
    ("Mr. James Wilson", "James Wilson"), ("Dr. Sarah Johnson", "Sarah Johnson"), ("Ms. Mei Wong", "Mei Wong"),
    ("james wilson", "James Wilson"), ("Ahmed Khan.", "Ahmed Khan"), ("Mei  Wong", "Mei Wong"),
    ("James R. Wilson", "James Wilson"),
])
def test_close_misspellings_and_titles_match(directory, heard, who):
    r = directory.lookup(heard, DOB[who])
    assert r.status == "found" and r.caller.patient_id == ID[who]


@pytest.mark.parametrize("heard", [
    "Ahmad Kim",        # spec: sounds-alike, spelled differently
    "Robert Tyler",     # spec: clearly different
    "James Watson", "Emily Bryan", "James Wilkins", "Sarah Jones", "Amy Wong",
    "Wilson", "Mr. Wilson", "Mrs. Johnson", "Ms Brown", "Mr Khan", "Dr. Taylor", "Mr. and Mrs. Wilson",
    "Wilson James", "Khan Ahmed",   # reversed order is not the same person
    "Robert", "Emily", "", None, "   ",
])
def test_names_that_must_not_match(directory, heard):
    # round 3 s1: never found; fewer than two (non-title) words -> incomplete whatever the date;
    # otherwise a missing date -> incomplete and a real date -> not_found.
    for dob in (None, *DOB.values()):
        r = directory.lookup(heard, dob)
        want = "incomplete" if (len(words(heard)) < 2 or dob is None) else "not_found"
        assert r.status == want and r.caller is None, (heard, dob, r.status)


def test_statuses_are_from_the_spec_list(directory):
    for name in ALL_NAMES + ["Nobody Here", "Mr. Wilson"]:
        for dob in (None, "1984-03-12", "bad", "2000-01-01"):
            assert directory.lookup(name, dob).status in STATUSES


def test_no_candidate_list_anywhere(directory):
    for name in ALL_NAMES:
        for dob in (None, "1999-09-09", "bad"):
            r = directory.lookup(name, dob)
            assert not hasattr(r, "candidates") and not hasattr(r, "matches")
            assert "candidates" not in r.to_dict()


def test_same_name_same_dob_is_several_without_details():
    d = PatientDirectory([
        {"id": "a", "name": "John Smith", "date_of_birth": "1980-01-01", "referrals_on_file": ["Radiology"]},
        {"id": "b", "name": "John Smith", "date_of_birth": "1980-01-01", "referrals_on_file": []},
    ])
    r = d.lookup("John Smith", "1980-01-01")
    assert r.status == "same_name_and_birthday" and r.caller is None  # round 3 s1


def test_same_name_different_dob_picks_the_right_one():
    d = PatientDirectory([
        {"id": "a", "name": "John Smith", "date_of_birth": "1980-01-01", "referrals_on_file": ["Radiology"]},
        {"id": "b", "name": "John Smith", "date_of_birth": "1990-02-02", "referrals_on_file": []},
    ])
    assert d.lookup("John Smith", None).status == "incomplete"  # round 3 s1
    assert d.lookup("John Smith", "1990-02-02").caller.patient_id == "b"
    assert d.lookup("John Smith", "1980-01-01").caller.referrals_on_file == ["Radiology"]
    assert d.lookup("John Smith", "1970-01-01").status == "not_found"  # round 3 s1


def test_returned_caller_does_not_share_referral_list(directory):
    a = directory.lookup("Ahmed Khan", DOB["Ahmed Khan"]).caller
    a.referrals_on_file.clear()
    b = directory.lookup("Ahmed Khan", DOB["Ahmed Khan"]).caller
    assert b.referrals_on_file == ["Dermatology"]
    assert a is not b


@pytest.mark.parametrize("bad", [
    {"name": "X Y", "date_of_birth": "1990-01-01"},
    {"id": "p", "date_of_birth": "1990-01-01"},
    {"id": "p", "name": "X Y"},
    {"id": "p", "name": "", "date_of_birth": "1990-01-01"},
])
def test_directory_refuses_broken_records(bad):
    with pytest.raises(CatalogError):
        PatientDirectory([bad])


def test_referrals_missing_means_none():
    d = PatientDirectory([{"id": "p", "name": "Jane Doe", "date_of_birth": "1990-01-01"}])
    assert d.lookup("Jane Doe", "1990-01-01").caller.referrals_on_file == []


def test_mei_wang_is_close_enough_by_the_spec_rule(directory):
    """'Wang' vs 'Wong' is exactly 75% alike, so it counts as a close misspelling.
    Round 3: a NEW caller called Mei Wang with her own birthday is simply not_found."""
    assert directory.lookup("Mei Wang", DOB["Mei Wong"]).status == "found"
    assert directory.lookup("Mei Wang", "2001-04-04").status == "not_found"
