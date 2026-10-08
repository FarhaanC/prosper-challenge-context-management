"""Voice stages, area 2: identity steps through start_booking (decisions 32 and 36).

32: returning patients give full name AND date of birth; nothing is looked up without
both; every miss gets the same reply. 36: try again -> spell the last name (third try)
-> offer to register as new or speak to staff; same name and birthday -> staff; after
3 unusable answers in a row, the same offer. INTERFACE.md: "If they choose to register
as new, call again with returning false."
"""

import copy

import pytest

from clinic import PatientDirectory
from voice_reference import (END, IDENTIFY, JAMES, NEW, PATIENT, PATIENTS, VISIT_TYPE, make_clinic, new_call,
                             snapshot, step)

DOB = PATIENT["James Wilson"]["date_of_birth"]
WRONG_DOB = "1984-03-13"


@pytest.fixture
def clinic(catalog, directory, tmp_path):
    return make_clinic(catalog, directory, bookings_file=tmp_path / "b.jsonl", log_dir=None)


def statuses(s, tries):
    out = []
    for t in tries:
        o = step(s, "start_booking", {"full_name": "James Wilson", "returning": True, **t})
        out.append((o.result.get("status"), o.next_stage))
    return out


def test_found_returning_patient_moves_on_with_their_record(clinic):
    s = new_call(clinic)
    out = step(s, "start_booking", dict(JAMES))
    assert out.result["ok"] is True and out.next_stage == VISIT_TYPE and s.stage == VISIT_TYPE
    c = s.card.caller
    assert (c.name, c.patient_id, c.is_new_patient) == ("James Wilson", "pat_001", False)
    assert sorted(c.referrals_on_file) == sorted(PATIENT["James Wilson"]["referrals_on_file"])
    assert "James" in out.result.get("say", ""), "decision 36: thank them by first name"


@pytest.mark.parametrize("dob", [None, "", "12/03/1984", "March 12 1984"])
def test_no_lookup_without_a_usable_date_of_birth(clinic, dob):
    s = new_call(clinic)
    args = {"full_name": "James Wilson", "returning": True}
    if dob is not None:
        args["date_of_birth"] = dob
    out = step(s, "start_booking", args)
    assert out.result["ok"] is False and out.next_stage is None and s.stage == IDENTIFY
    assert s.card.caller is None, "decision 32: nothing is looked up without both"
    assert out.result["status"] == "need_both"
    assert "date of birth" in out.result["say"].lower()


def test_same_reply_whether_the_name_or_the_birthday_was_wrong(clinic):
    a, b = new_call(clinic), new_call(clinic)
    wrong_name = step(a, "start_booking", {"full_name": "Jane Wilson", "returning": True, "date_of_birth": DOB})
    wrong_dob = step(b, "start_booking", {"full_name": "James Wilson", "returning": True, "date_of_birth": WRONG_DOB})
    assert wrong_name.result == wrong_dob.result, "decision 32: every miss gets the same reply"
    assert wrong_name.result["status"] == "try_again"


def test_steps_try_again_then_spell_then_offer(clinic):
    s = new_call(clinic)
    got = statuses(s, [{"date_of_birth": WRONG_DOB}, {"date_of_birth": WRONG_DOB},
                       {"date_of_birth": WRONG_DOB, "spelled_last_name": "WILSON"}])
    assert got == [("try_again", None), ("spell_last_name", None), ("offer_new_or_staff", None)]
    assert s.stage == IDENTIFY and s.card.caller is None


def test_third_try_must_be_spelled(clinic):
    s = new_call(clinic)
    got = statuses(s, [{"date_of_birth": WRONG_DOB}, {"date_of_birth": WRONG_DOB}, {"date_of_birth": WRONG_DOB}])
    assert [g[0] for g in got] == ["try_again", "spell_last_name", "spell_last_name"]


def test_offer_says_register_or_staff(clinic):
    s = new_call(clinic)
    statuses(s, [{"date_of_birth": WRONG_DOB}, {"date_of_birth": WRONG_DOB}])
    out = step(s, "start_booking", {"full_name": "James Wilson", "returning": True, "date_of_birth": WRONG_DOB,
                                    "spelled_last_name": "WILSON"})
    say = out.result["say"].lower()
    assert "new patient" in say and "staff" in say


@pytest.mark.parametrize("misses", [0, 1, 2, 3])
def test_correct_details_accepted_at_any_step(clinic, misses):
    s = new_call(clinic)
    tries = [{"date_of_birth": WRONG_DOB}, {"date_of_birth": WRONG_DOB},
             {"date_of_birth": WRONG_DOB, "spelled_last_name": "WILSON"}][:misses]
    statuses(s, tries)
    out = step(s, "start_booking", dict(JAMES))
    assert out.result["ok"] is True and s.stage == VISIT_TYPE and s.card.caller.patient_id == "pat_001"


def test_register_as_new_after_the_offer(clinic):
    s = new_call(clinic)
    statuses(s, [{"date_of_birth": WRONG_DOB}, {"date_of_birth": WRONG_DOB},
                 {"date_of_birth": WRONG_DOB, "spelled_last_name": "WILSON"}])
    out = step(s, "start_booking", {"full_name": "James Wilson", "returning": False, "visit_description": "knee MRI"})
    assert out.result["ok"] is True and out.next_stage == VISIT_TYPE
    c = s.card.caller
    assert c.is_new_patient is True and c.patient_id is None
    assert c.referrals_on_file == [], "a caller registered as new must not get anyone's referrals"
    assert s.card.preferences.visit_description == "knee MRI"


def test_unusable_answers_three_in_a_row_get_the_offer(clinic):
    s = new_call(clinic)
    got = []
    for _ in range(3):
        o = step(s, "start_booking", {"full_name": "James", "returning": True, "date_of_birth": DOB})
        got.append(o.result.get("status"))
    assert got == ["need_both", "need_both", "offer_new_or_staff"]
    assert s.card.caller is None


@pytest.mark.parametrize("name,dob", [
    ("Robert Tyler", "1962-05-08"),     # decision 32: must not get Robert Taylor's record
    ("Mr. Wilson", DOB),                # decision 32: "Mr. Wilson" must not find James Wilson
    ("Ahmad Kim", "1991-11-02"),        # patients.py: "Ahmad Kim" can't become Ahmed Khan
])
def test_near_names_never_identify_someone_else(clinic, name, dob):
    s = new_call(clinic)
    out = step(s, "start_booking", {"full_name": name, "returning": True, "date_of_birth": dob})
    assert out.result["ok"] is False and s.card.caller is None and s.stage == IDENTIFY


def test_same_name_and_birthday_goes_to_staff(clinic, catalog, directory):
    twin = copy.deepcopy(PATIENT["James Wilson"])
    twin["id"] = "pat_099"
    twins = make_clinic(catalog, directory, patients=PatientDirectory(copy.deepcopy(PATIENTS) + [twin]))
    s = new_call(twins)
    out = step(s, "start_booking", dict(JAMES))
    assert out.next_stage == END and s.stage == END
    assert s.card.caller is None, "two records share name and birthday: don't guess"
    assert s.card.status == "handed_off"
    assert "staff" in s.fill("{outcome}").lower()


def test_new_patient_needs_no_date_of_birth(clinic):
    s = new_call(clinic)
    out = step(s, "start_booking", dict(NEW))
    assert out.result["ok"] is True and s.stage == VISIT_TYPE
    assert s.card.caller.is_new_patient is True and s.card.caller.referrals_on_file == []


def test_new_patient_with_one_word_name_is_asked_for_full_name(clinic):
    s = new_call(clinic)
    before = snapshot(s)
    out = step(s, "start_booking", {"full_name": "Farhan", "returning": False})
    assert out.result["ok"] is False and out.next_stage is None
    assert snapshot(s) == before


def test_new_patient_who_shares_a_patients_name_gets_no_record(clinic):
    s = new_call(clinic)
    step(s, "start_booking", {"full_name": "James Wilson", "returning": False})
    assert s.card.caller.patient_id is None and s.card.caller.referrals_on_file == []


def test_identity_cannot_be_swapped_once_identified(clinic):
    s = new_call(clinic)
    step(s, "start_booking", dict(NEW))
    before = snapshot(s)
    out = step(s, "start_booking", dict(JAMES))
    assert out.result["ok"] is False and out.next_stage is None
    assert snapshot(s) == before, "a second start_booking must not swap in another patient's record"


def test_wishes_travel_with_start_booking(clinic):
    # Decision 47: one tool call carries everything said so far.
    s = new_call(clinic)
    step(s, "start_booking", {**JAMES, "visit_description": "knee MRI", "doctor_name": "Dr. Linda Ramirez",
                              "place": "Union Square", "near": True, "days": ["Thursday", "Friday"],
                              "time_of_day": "morning", "soonest": True, "language": "Arabic"})
    p = s.card.preferences
    assert p.visit_description == "knee MRI"
    assert p.doctor_name_heard == "Dr. Linda Ramirez"
    assert (p.location_hint, p.near) == ("Union Square", True)
    assert p.days == ["Thursday", "Friday"] and p.time_of_day == "morning"
    assert p.soonest is True and p.language == "Arabic"
