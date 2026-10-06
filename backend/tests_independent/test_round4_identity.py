"""Round 4 (spec-changes-round-4.md): the identity step rules, change 2 ("unusable answers
no longer loop forever") and the "Identity steps" list, adversarially, plus privacy.

Expected answers come from the spec text and patients.json only.
"""

import itertools
import json

import pytest

from clinic import IdentityCheck, PatientDirectory
from reference import DATA

RECORDS = json.loads((DATA / "patients.json").read_text())["patients"]
REAL, REAL_DOB = "James Wilson", "1984-03-12"   # patients.json pat_001
WRONG_DOB = "1984-03-13"
FAKE = "Zed Quorra"
OFFER, NEED, AGAIN, SPELL = "offer_new_or_staff", "need_both", "try_again", "spell_last_name"

# Unusable answers: "name or date of birth missing or unusable" (round 3 s1, round 4 change 2).
UNUSABLE = [("James", REAL_DOB), ("", REAL_DOB), (REAL, None), (REAL, "12/03/1984"), ("Mr. Wilson", REAL_DOB),
            (REAL, "1984-3-12"), (None, None), ("Dr. Jr.", REAL_DOB)]


@pytest.mark.parametrize("name,dob", UNUSABLE)
def test_three_unusable_answers_in_a_row_offer_the_choice(directory, name, dob):
    # change 2: "after 3 unusable answers in a row, IdentityCheck.attempt returns offer_new_or_staff"
    c = IdentityCheck()
    assert [c.attempt(directory, name, dob).status for _ in range(3)] == [NEED, NEED, OFFER]
    s = c.attempt(directory, name, dob)
    assert s.status == OFFER and s.caller is None  # "once offer_new_or_staff has been given, ... again"
    assert "new patient" in s.say.lower() and "staff" in s.say.lower()


def test_a_usable_answer_resets_the_unusable_count(directory):
    # change 2: "A usable answer resets that count."
    c = IdentityCheck()
    seq = [("James", REAL_DOB), ("James", REAL_DOB), (FAKE, WRONG_DOB),  # 2 unusable, then the first miss
           ("James", REAL_DOB), ("James", REAL_DOB), ("James", REAL_DOB)]  # 3 more unusable in a row
    got = [c.attempt(directory, n, d).status for n, d in seq]
    assert got == [NEED, NEED, AGAIN, NEED, NEED, OFFER]


def test_unusable_answers_do_not_count_as_misses_before_the_limit(directory):
    c = IdentityCheck()
    got = [c.attempt(directory, *a).status for a in [(None, None), (FAKE, WRONG_DOB), (None, None), (FAKE, WRONG_DOB)]]
    assert got == [NEED, AGAIN, NEED, SPELL]  # still the first and second miss


def test_unusable_limit_also_applies_in_the_spelling_phase(directory):
    c = IdentityCheck()
    c.attempt(directory, FAKE, WRONG_DOB)
    c.attempt(directory, FAKE, WRONG_DOB)  # now asked to spell
    got = [c.attempt(directory, "Zed", None, spelled_last_name="Q U O R R A").status for _ in range(3)]
    assert got == [NEED, NEED, OFFER]


@pytest.mark.parametrize("route", ["unusable", "misses"])
def test_correct_details_accepted_even_after_the_choice_was_offered(directory, route):
    # "every attempt is looked up, so correct details are accepted at any step"
    c = IdentityCheck()
    if route == "unusable":
        for _ in range(3):
            c.attempt(directory, None, None)
    else:
        c.attempt(directory, FAKE, WRONG_DOB)
        c.attempt(directory, FAKE, WRONG_DOB)
        c.attempt(directory, FAKE, WRONG_DOB, spelled_last_name="Q U O R R A")
    s = c.attempt(directory, REAL, REAL_DOB)
    assert s.status == "found" and s.caller.patient_id == "pat_001"
    assert s.say == "Thank you, James. I've found your details."


def test_after_two_misses_unspelled_wrong_tries_never_count(directory):
    c = IdentityCheck()
    c.attempt(directory, FAKE, WRONG_DOB)
    c.attempt(directory, FAKE, WRONG_DOB)
    for _ in range(6):  # never jumps to the offer without a spelling
        assert c.attempt(directory, FAKE, WRONG_DOB).status == SPELL


@pytest.mark.parametrize("blank", ["", "   ", "\t", None])
def test_blank_spelling_is_no_spelling(directory, blank):
    c = IdentityCheck()
    c.attempt(directory, FAKE, WRONG_DOB)
    c.attempt(directory, FAKE, WRONG_DOB)
    assert c.attempt(directory, FAKE, WRONG_DOB, spelled_last_name=blank).status == SPELL


def test_first_name_and_spelled_surname_is_enough(directory):
    c = IdentityCheck()
    c.attempt(directory, FAKE, WRONG_DOB)
    c.attempt(directory, FAKE, WRONG_DOB)
    s = c.attempt(directory, "Emily", "1988-01-19", spelled_last_name="B R O W N")
    assert s.status == "found" and s.caller.patient_id == "pat_004"
    assert s.say == "Thank you, Emily. I've found your details."


@pytest.mark.parametrize("name", ["Anh Do", "Anh Md", "Anh Np", "Anh Pa"])
def test_degree_letters_are_names_not_titles(name):
    d = PatientDirectory([{"id": "p1", "name": name, "date_of_birth": "1970-01-01"}])
    c = IdentityCheck()
    s = c.attempt(d, name, "1970-01-01")
    assert s.status == "found", s.to_dict()


@pytest.mark.parametrize("name", ["Dr. Wilson", "Mr. Wilson", "Mrs. Wilson", "Wilson Jr", "Ms Wilson"])
def test_real_titles_still_do_not_make_a_full_name(directory, name):
    assert directory.lookup(name, REAL_DOB).status == "incomplete"


# ---------------------------------------------------------------- privacy, whole scripted calls
# Each script step is one kind of answer. The real caller uses James Wilson's real details
# EXCEPT where the spec says nothing may differ: replies must be identical for a real and a
# made-up name at every step, unless BOTH details match a record.
def _answers(real):
    name, first, sur = (REAL, "James", "W I L S O N") if real else (FAKE, "Zed", "Q U O R R A")
    return {
        "unusable_one_word": (first, REAL_DOB, None),           # real birthday, one word: not looked up
        "unusable_no_dob": (name, None, None),
        "wrong_dob": (name, WRONG_DOB, None),                   # real name, wrong birthday
        "real_dob_wrong_name": ("Peter Parker" if real else "Mary Jane", REAL_DOB, None),
        "spelled_wrong_dob": (first, WRONG_DOB, sur),
        "spelled_wrong_surname": (first, REAL_DOB, "S M I T H X"),  # 2+ letters from both surnames
    }


SCRIPTS = list(itertools.product(list(_answers(True)), repeat=4))


def test_privacy_every_reply_identical_for_real_and_made_up_names(directory):
    differences = []
    for script in SCRIPTS:
        real, fake = IdentityCheck(), IdentityCheck()
        for step in script:
            a = real.attempt(directory, *_answers(True)[step]).to_dict()
            b = fake.attempt(directory, *_answers(False)[step]).to_dict()
            if a != b or a["caller"] is not None:
                differences.append((script, step, a, b))
                break
    assert not differences, (len(differences), differences[:3])


def test_privacy_no_reply_contains_record_details(directory):
    bits = [x for r in RECORDS for x in (r["name"], r["id"], r["date_of_birth"], *r["referrals_on_file"])]
    for script in SCRIPTS[:300]:
        c = IdentityCheck()
        for step in script:
            text = json.dumps(c.attempt(directory, *_answers(True)[step]).to_dict())
            assert not [b for b in bits if b in text], (script, text)


def test_found_only_when_both_details_match(directory):
    # sanity check on the other side of privacy: the real caller IS found at any point.
    for script in SCRIPTS[::97]:
        c = IdentityCheck()
        for step in script:
            c.attempt(directory, *_answers(True)[step])
        s = c.attempt(directory, REAL, REAL_DOB)
        assert s.status == "found" and s.caller.name == REAL, script
