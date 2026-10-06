"""Round 3, spec change 1: identity is a step-by-step check (spec-changes-round-3.md s1).

Expected answers come from the spec text and patients.json only.
"""

import copy
import json
import pickle

import pytest

from clinic import BookingCard, IdentityCheck, IdentityStep, PatientDirectory
from reference import DATA

RECORDS = json.loads((DATA / "patients.json").read_text())["patients"]
DOB = {r["name"]: r["date_of_birth"] for r in RECORDS}
ID = {r["name"]: r["id"] for r in RECORDS}
LOOKUP_STATUSES = {"incomplete", "not_found", "found", "same_name_and_birthday"}
STEP_STATUSES = {"need_both", "try_again", "spell_last_name", "offer_new_or_staff", "found", "hand_to_staff"}
FAKE = "Nobody Madeup"
FAKE_DOB = "1990-06-15"


def leaks(obj):
    text = json.dumps(obj.to_dict()) + " " + str(getattr(obj, "say", ""))
    return [bit for r in RECORDS for bit in (r["name"], r["id"], r["date_of_birth"], *r["referrals_on_file"])
            if bit and bit in text]


def miss(directory, check, n):
    """n failed tries with a made-up caller."""
    for _ in range(n):
        check.attempt(directory, FAKE, FAKE_DOB)


# ---------------------------------------------------------------- lookup
def test_date_of_birth_is_a_required_argument(directory):
    with pytest.raises(TypeError):
        directory.lookup("James Wilson")  # spec: "date of birth is now a required argument"


@pytest.mark.parametrize("name", list(DOB))
def test_lookup_found_copies_referrals(directory, name):
    r = directory.lookup(name, DOB[name])
    assert r.status == "found" and r.caller.patient_id == ID[name] and not r.caller.is_new_patient
    rec = next(x for x in RECORDS if x["name"] == name)
    assert r.caller.referrals_on_file == rec["referrals_on_file"]
    assert r.caller.referrals_on_file is not rec["referrals_on_file"]
    assert r.to_dict()["status"] == "found"
    json.dumps(r.to_dict())


@pytest.mark.parametrize("dob", [None, "", "  ", "12/03/1984", "1984/03/12", "March 12 1984", "19840312",
                                 "1984-3-12", "84-03-12", "1984-03-12T00:00", "1984-03-12 extra", "yesterday"])
def test_bad_or_missing_dob_is_incomplete_for_real_and_fake(directory, dob):
    for name in list(DOB) + [FAKE, "John Smith"]:
        r = directory.lookup(name, dob)
        assert r.status == "incomplete" and r.caller is None, (name, dob, r.status)
        assert not leaks(r)


@pytest.mark.parametrize("name", ["", None, "   ", "James", "Wilson", "Mr. Wilson", "Mr Wilson", "Mrs. Johnson",
                                  "Ms Brown", "Dr. Taylor", "Miss Wong", "Wilson Jr", "Mr. Wilson Jr.", "James Jr",
                                  "Mr. Jr.", "Ahmed", "Mr. Khan Sr."])
def test_fewer_than_two_name_words_is_incomplete_whatever_the_date(directory, name):
    """Spec: 'titles like "Mr." and endings like "Jr" don't count'; nothing is looked up."""
    for dob in [*DOB.values(), FAKE_DOB]:
        r = directory.lookup(name, dob)
        assert r.status == "incomplete" and r.caller is None, (name, dob, r.status)


@pytest.mark.parametrize("name", list(DOB))
def test_wrong_name_and_wrong_date_give_the_same_answer(directory, name):
    """Spec: 'not_found ... Same answer whether the name or the date was wrong.'"""
    wrong_date = directory.lookup(name, "2001-02-03")
    other_dob = next(d for n, d in DOB.items() if n != name)
    wrong_other = directory.lookup(name, other_dob)
    wrong_name = directory.lookup("Zed Quimby", DOB[name])
    both_wrong = directory.lookup("Zed Quimby", "2001-02-03")
    dicts = [x.to_dict() for x in (wrong_date, wrong_other, wrong_name, both_wrong)]
    assert all(d == dicts[0] for d in dicts), dicts
    assert dicts[0]["status"] == "not_found" and dicts[0]["caller"] is None


def test_lookup_statuses_only_from_spec_list(directory):
    names = list(DOB) + [FAKE, "Mr. Wilson", "James", "", "Ahmad Kim", "Mei Wang"]
    dobs = [None, "bad", "1984-03-12", "2000-01-01", *DOB.values()]
    for n in names:
        for d in dobs:
            r = directory.lookup(n, d)
            assert r.status in LOOKUP_STATUSES
            assert set(r.to_dict()) == {"status", "caller"} or "candidates" not in r.to_dict()
            assert not hasattr(r, "candidates") and not hasattr(r, "names")


@pytest.mark.parametrize("heard,who", [
    ("James Willson", "James Wilson"), ("Ahmed Kahn", "Ahmed Khan"), ("Sara Jonson", "Sarah Johnson"),
    ("Mr. James Wilson", "James Wilson"), ("James Wilson Jr.", "James Wilson"), ("Dr. Emily Brown", "Emily Brown"),
    ("Mrs Sarah Johnson", "Sarah Johnson"), ("Mei Wang", "Mei Wong"),
])
def test_forgiving_spelling_with_titles(directory, heard, who):
    r = directory.lookup(heard, DOB[who])
    assert r.status == "found" and r.caller.patient_id == ID[who]


@pytest.mark.parametrize("heard,who", [("Ahmad Kim", "Ahmed Khan"), ("Robert Tyler", "Robert Taylor"),
                                       ("Emily Bryan", "Emily Brown"), ("Amy Wong", "Mei Wong"),
                                       ("Wilson James", "James Wilson")])
def test_never_by_sound_alone_even_with_the_right_birthday(directory, heard, who):
    assert directory.lookup(heard, DOB[who]).status == "not_found"


def test_same_name_different_birthdays_picks_by_birthday():
    d = PatientDirectory([
        {"id": "a", "name": "John Smith", "date_of_birth": "1980-01-01", "referrals_on_file": ["Radiology"]},
        {"id": "b", "name": "John Smith", "date_of_birth": "1990-02-02"},
    ])
    assert d.lookup("John Smith", "1980-01-01").caller.patient_id == "a"
    assert d.lookup("John Smyth", "1990-02-02").caller.patient_id == "b"
    assert d.lookup("John Smith", "1985-05-05").status == "not_found"


def test_same_name_and_birthday_goes_to_staff_without_details():
    d = PatientDirectory([
        {"id": "a", "name": "John Smith", "date_of_birth": "1980-01-01", "referrals_on_file": ["Radiology"]},
        {"id": "b", "name": "John Smith", "date_of_birth": "1980-01-01"},
        {"id": "c", "name": "Jane Doe", "date_of_birth": "1980-01-01"},
    ])
    r = d.lookup("John Smith", "1980-01-01")
    assert r.status == "same_name_and_birthday" and r.caller is None
    assert "Radiology" not in json.dumps(r.to_dict())
    step = IdentityCheck().attempt(d, "John Smith", "1980-01-01")
    assert step.status == "hand_to_staff" and step.caller is None and step.say
    # someone else with that birthday is still found
    assert d.lookup("Jane Doe", "1980-01-01").caller.patient_id == "c"


# ---------------------------------------------------------------- spelled last name
@pytest.mark.parametrize("spelled", ["B R O W N", "BROWN", "brown", "B-R-O-W-N", "b r o w n",
                                     "B R A W N",   # one letter changed
                                     "B R O W N E",  # one letter added
                                     "B R O N",     # one letter removed
                                     "D R O W N"])  # B/D misheard
def test_spelled_surname_one_letter_out_passes(directory, spelled):
    r = directory.lookup("Emily Brown", DOB["Emily Brown"], spelled_last_name=spelled)
    assert r.status == "found" and r.caller.patient_id == ID["Emily Brown"], spelled


@pytest.mark.parametrize("spelled", ["B R A W M", "B R O W N I E", "B O N", "S M I T H", "N W O R B"])
def test_spelled_surname_two_letters_out_fails(directory, spelled):
    r = directory.lookup("Emily Brown", DOB["Emily Brown"], spelled_last_name=spelled)
    assert r.status == "not_found" and r.caller is None, spelled


def test_spelled_surname_khan_transposed_is_two_changes(directory):
    # "one added, removed or changed": swapping two letters is two changes
    assert directory.lookup("Ahmed Khan", DOB["Ahmed Khan"], spelled_last_name="K A H N").status == "not_found"
    assert directory.lookup("Ahmed Khan", DOB["Ahmed Khan"], spelled_last_name="K H A N").status == "found"


def test_spelled_surname_first_name_still_forgiving(directory):
    dob = DOB["Emily Brown"]
    assert directory.lookup("Emly Brwn", dob, spelled_last_name="BROWN").status == "found"
    assert directory.lookup("Amy Brown", dob, spelled_last_name="BROWN").status == "not_found"


def test_spelled_surname_still_needs_the_birthday(directory):
    assert directory.lookup("Emily Brown", "1988-01-20", spelled_last_name="BROWN").status == "not_found"
    assert directory.lookup("Emily Brown", None, spelled_last_name="BROWN").status == "incomplete"


# ---------------------------------------------------------------- IdentityCheck, step by step
def test_steps_in_order_for_a_made_up_caller(directory):
    c = IdentityCheck()
    s = [c.attempt(directory, FAKE, FAKE_DOB) for _ in range(2)]
    assert [x.status for x in s] == ["try_again", "spell_last_name"]
    assert s[0].say == ("Sorry, I couldn't find you. Could you tell me your full name and date of birth "
                        "once more?")
    assert "spell" in s[1].say.lower() and "date of birth" in s[1].say.lower()
    # from now on, an attempt WITHOUT a spelling repeats the request and doesn't count
    for _ in range(3):
        again = c.attempt(directory, FAKE, FAKE_DOB)
        assert again.status == "spell_last_name"
    last = c.attempt(directory, FAKE, FAKE_DOB, spelled_last_name="M A D E U P")
    assert last.status == "offer_new_or_staff"
    assert "new patient" in last.say.lower() and "staff" in last.say.lower()
    for x in (*s, again, last):
        assert x.caller is None and isinstance(x, IdentityStep)


@pytest.mark.parametrize("name,dob", [(None, None), ("", FAKE_DOB), ("James", "1984-03-12"),
                                      ("James Wilson", None), ("James Wilson", "12/03/1984"), ("Mr. Wilson", "1984-03-12")])
def test_need_both_does_not_count(directory, name, dob):
    # Round 4, change 2: need_both still doesn't count as a miss, but "after 3 unusable answers
    # in a row, IdentityCheck.attempt returns offer_new_or_staff". So two unusable answers, then
    # a usable miss is still the FIRST miss ...
    c = IdentityCheck()
    for _ in range(2):
        assert c.attempt(directory, name, dob).status == "need_both"
    assert c.attempt(directory, FAKE, FAKE_DOB).status == "try_again"  # still the FIRST miss
    # ... and "a usable answer resets that count": two more unusable answers are need_both again.
    for _ in range(2):
        assert c.attempt(directory, name, dob).status == "need_both"
    assert c.attempt(directory, FAKE, FAKE_DOB).status == "spell_last_name"  # the SECOND miss


def test_found_at_any_step(directory):
    for misses in range(0, 2):
        c = IdentityCheck()
        miss(directory, c, misses)
        s = c.attempt(directory, "James Wilson", "1984-03-12")
        assert s.status == "found" and s.caller.patient_id == "pat_001", misses
    c = IdentityCheck()
    miss(directory, c, 2)
    s = c.attempt(directory, "James Wilson", "1984-03-12", spelled_last_name="W I L S O N")
    assert s.status == "found" and s.caller.patient_id == "pat_001"
    c = IdentityCheck()
    miss(directory, c, 2)
    c.attempt(directory, FAKE, FAKE_DOB, spelled_last_name="X Y Z")  # offer_new_or_staff
    s = c.attempt(directory, "James Willson", "1984-03-12", spelled_last_name="W I L S O N")
    assert s.status == "found"


def test_blank_spelling_counts_as_no_spelling(directory):
    """Spec s1 step 3: 'an attempt without spelled_last_name returns spell_last_name again
    without counting.' A spelling of only spaces is no spelling at all."""
    c = IdentityCheck()
    miss(directory, c, 2)
    s = c.attempt(directory, FAKE, FAKE_DOB, spelled_last_name="   ")
    assert s.status == "spell_last_name", s.status


def test_step_to_dict_and_found_say(directory):
    s = IdentityCheck().attempt(directory, "James Wilson", "1984-03-12")
    d = s.to_dict()
    assert set(d) >= {"status", "say", "caller"} and d["status"] == "found"
    json.dumps(d)
    for st in (IdentityCheck().attempt(directory, FAKE, FAKE_DOB), IdentityCheck().attempt(directory, None, None)):
        assert set(st.to_dict()) >= {"status", "say", "caller"} and st.to_dict()["say"] == st.say and st.say


def test_card_keeps_one_identity_check(directory):
    card = BookingCard()
    assert isinstance(card.identity, IdentityCheck)
    assert card.identity.attempt(directory, FAKE, FAKE_DOB).status == "try_again"
    assert card.identity.attempt(directory, FAKE, FAKE_DOB).status == "spell_last_name"
    other = BookingCard()
    assert other.identity.attempt(directory, FAKE, FAKE_DOB).status == "try_again"  # not shared between calls
    json.dumps(card.to_dict(), default=str)


# ---------------------------------------------------------------- privacy, as a whole
def _transcript(directory, script):
    c = IdentityCheck()
    return [c.attempt(directory, *args).to_dict() for args in script]


@pytest.mark.parametrize("real", list(DOB))
def test_privacy_real_name_wrong_date_reads_exactly_like_a_made_up_name(directory, real):
    """No answer may differ between a real and a made-up name unless both name and date match.
    Same scripted call, step by step, compared on the whole to_dict()."""
    other_dob = next(d for n, d in DOB.items() if n != real)
    surname = real.split()[-1]
    for wrong_dob in ("2001-02-03", other_dob):
        script_real = [(real.split()[0], wrong_dob), (real, None), (real, wrong_dob), (real, wrong_dob),
                       (real, wrong_dob), (real, wrong_dob, " ".join(surname.upper())), (real, wrong_dob, surname)]
        script_fake = [("Zed", wrong_dob), (FAKE, None), (FAKE, wrong_dob), (FAKE, wrong_dob),
                       (FAKE, wrong_dob), (FAKE, wrong_dob, "M A D E U P"), (FAKE, wrong_dob, "Madeup")]
        assert _transcript(directory, script_real) == _transcript(directory, script_fake), (real, wrong_dob)


@pytest.mark.parametrize("real", list(DOB))
def test_privacy_real_birthday_with_wrong_name_reads_like_anything_else(directory, real):
    script_a = [("Zed Quimby", DOB[real])] * 3 + [("Zed Quimby", DOB[real], "Q U I M B Y")]
    script_b = [("Zed Quimby", "2002-02-02")] * 3 + [("Zed Quimby", "2002-02-02", "Q U I M B Y")]
    assert _transcript(directory, script_a) == _transcript(directory, script_b)


def test_identity_objects_copy_and_pickle(directory):
    s = IdentityCheck().attempt(directory, "James Wilson", "1984-03-12")
    assert pickle.loads(pickle.dumps(s)).to_dict() == s.to_dict()
    c = IdentityCheck()
    miss(directory, c, 1)
    c2 = copy.deepcopy(c)
    assert c2.attempt(directory, FAKE, FAKE_DOB).status == "spell_last_name"
    assert c.attempt(directory, FAKE, FAKE_DOB).status == "spell_last_name"  # the copy didn't share its count


def test_vietnamese_surname_do_is_a_name_not_a_title():
    """My own realistic case for a San Francisco clinic: 'Do' is a common Vietnamese surname.
    Spec: only 'titles like "Mr." and endings like "Jr"' are not counted as name words."""
    d = PatientDirectory([{"id": "v", "name": "Anh Do", "date_of_birth": "1980-01-01"}])
    r = d.lookup("Anh Do", "1980-01-01")
    assert r.status == "found", r.status
