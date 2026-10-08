"""Round 2: start_booking and stage 2's opening (decisions 52, 53, 54; spec note "start_booking").

- start_booking takes an optional specialty, matched as list_visit_types matches them; an
  unknown name is refused. Once the caller is found or registered, stage 2's
  {visit_types} lists that specialty's visit types with ids, each "can book" or
  "can't book (reason)". Without one: "Not looked up yet: call list_visit_types...".
- The success reply is {"ok": true}.
- Wishes and the visit description sent with a try that doesn't find the caller are
  recorded, as long as every value is usable. A refused value still records nothing.
- When choose_visit_type is accepted, the card's visit description becomes the visit's
  name (decision 53). A visit the caller can't book is not a refused value: wishes sent
  with it still count (decision 54).

Expected visit types and can/can't book come from catalog.json and patients.json
(reference.py's own rules 1-5).
"""

import pytest

from agent_builder import AgentBuilder
from voice_reference import (AGENT_FILE, NOW, IDENTIFY, JAMES, KNEE_MRI, NEW, PATIENT, SKIN_CHECK, SPECIALTIES, VISIT_TYPE, VT,
                             make_clinic, new_call, offered, ref_bookable, snapshot, step, to_visit_type)
from voice_round2_reference import refused_unchanged, visit_type_lines, visit_types_of

WRONG_DOB = "1984-03-13"
JAMES_REFS = PATIENT["James Wilson"]["referrals_on_file"]
EMILY = {"full_name": "Emily Brown", "returning": True, "date_of_birth": PATIENT["Emily Brown"]["date_of_birth"]}
EMILY_REFS = PATIENT["Emily Brown"]["referrals_on_file"]


@pytest.fixture
def clinic(catalog, directory, tmp_path):
    return make_clinic(catalog, directory, bookings_file=tmp_path / "b.jsonl", log_dir=None)


# ================================================================== the success reply
@pytest.mark.parametrize("who", [NEW, JAMES], ids=["new", "returning"])
def test_success_reply_is_just_ok(clinic, who):
    s = new_call(clinic)
    out = step(s, "start_booking", {**who, "specialty": "Dermatology"})
    assert out.result == {"ok": True} and out.next_stage == VISIT_TYPE


# ================================================================== {visit_types}
CASES = [(NEW, True, []), (JAMES, False, JAMES_REFS), (EMILY, False, EMILY_REFS)]


@pytest.mark.parametrize("specialty", ["Radiology", "Dermatology", "Cardiology", "Family Medicine", "Pediatrics"])
@pytest.mark.parametrize("who,is_new,refs", CASES, ids=["new", "james", "emily"])
def test_visit_types_are_listed_for_the_specialty_sent(clinic, specialty, who, is_new, refs):
    s = new_call(clinic)
    assert step(s, "start_booking", {**who, "specialty": specialty}).result["ok"] is True
    text = s.fill("{visit_types}")
    rows = visit_type_lines(text)
    assert set(rows) == visit_types_of(specialty), text
    for vid, (name, minutes, can_book, reason) in rows.items():
        v = VT[vid]
        assert name == v["name"]
        assert minutes in (None, v["duration_min"])
        assert can_book == ref_bookable(is_new, refs, vid), (vid, text)
        if not can_book:
            assert reason, f"a visit that can't be booked says why: {vid}"
            low = reason.lower()
            if is_new and not v["new_patients_allowed"]:
                assert "existing patients" in low or "new patient" in low, reason
            if v["requires_referral"] and specialty not in refs:
                assert "referral" in low, reason
    # Nothing from another specialty is listed.
    others = {v["name"] for vid, v in VT.items() if v["specialty"] != specialty}
    assert not any(f": {n}:" in text or f": {n} (" in text for n in others)


def test_visit_types_without_a_specialty_says_not_looked_up(clinic):
    s = to_visit_type(clinic, NEW)
    assert s.fill("{visit_types}").startswith("Not looked up yet")
    assert "list_visit_types" in s.fill("{visit_types}")


@pytest.mark.parametrize("specialty", ["dermatology", "DERMATOLOGY", "Dermatologist", "dermatologists", "skin",
                                       "Derm", "Family medicine", "cardiologist", "heart doctor", "Astrology", ""])
def test_specialty_is_matched_exactly_as_list_visit_types_matches_it(clinic, specialty):
    probe = to_visit_type(clinic, NEW)
    listed = step(probe, "list_visit_types", {"specialty": specialty}).result
    s = new_call(clinic)
    out = step(s, "start_booking", {**NEW, "specialty": specialty})
    if specialty == "":
        # An empty value counts as not sent.
        assert out.result["ok"] is True and s.fill("{visit_types}").startswith("Not looked up yet")
        return
    assert (out.result["ok"] is True) == (listed["ok"] is not False), (specialty, listed, out.result)
    if out.result["ok"] is True:
        rows = visit_type_lines(s.fill("{visit_types}"))
        assert set(rows) == {r["id"] for r in listed["visit_types"]}


@pytest.mark.parametrize("bad", ["Astrology", "Dental Surgery Department", 5, ["Dermatology"]])
def test_unknown_specialty_is_refused_and_records_nothing(clinic, bad):
    s = new_call(clinic)
    refused_unchanged(s, "start_booking", {**NEW, "specialty": bad, "days": ["Thursday"]})
    assert s.card.caller is None and s.stage == IDENTIFY


def test_the_specialty_list_in_stage_1_is_the_21_names(clinic):
    # Spec note: "Stage 1 now shows {specialties} too" (the AI picks start_booking's specialty from it).
    node = AgentBuilder.from_json(AGENT_FILE).build_initial_node(clinic.new_call(clock=lambda: NOW))
    text = "\n".join(m["content"] for m in node["task_messages"])
    assert len(SPECIALTIES) == 21
    for name in SPECIALTIES:
        assert name in text, name


# ================================================================== wishes on a failed identity try
WISHES = {"visit_description": "knee MRI", "doctor_name": "Dr. Linda Ramirez", "place": "Downtown", "near": True,
          "days": ["Thursday"], "time_of_day": "morning", "soonest": True, "language": "English"}


def prefs_of(s):
    p = s.card.preferences
    return {"visit_description": p.visit_description, "doctor_name": p.doctor_name_heard, "place": p.location_hint,
            "near": p.near, "days": p.days, "time_of_day": p.time_of_day, "soonest": p.soonest,
            "language": p.language}


@pytest.mark.parametrize("attempt,status", [
    ({"full_name": "James Wilson", "returning": True, "date_of_birth": WRONG_DOB}, "try_again"),
    ({"full_name": "James Wilson", "returning": True}, "need_both"),
    ({"full_name": "Jane Wilson", "returning": True, "date_of_birth": PATIENT["James Wilson"]["date_of_birth"]},
     "try_again"),
], ids=["wrong birthday", "no birthday", "wrong name"])
def test_wishes_sent_with_a_failed_try_are_kept(clinic, attempt, status):
    s = new_call(clinic)
    out = step(s, "start_booking", {**attempt, **WISHES})
    assert out.result["ok"] is False and out.result["status"] == status and s.stage == IDENTIFY
    assert s.card.caller is None
    assert prefs_of(s) == WISHES


def test_wishes_from_failed_tries_are_used_once_the_caller_is_found(clinic):
    s = new_call(clinic)
    step(s, "start_booking", {"full_name": "James Wilson", "returning": True, "date_of_birth": WRONG_DOB,
                              "days": ["Thursday"], "visit_description": "knee MRI"})
    step(s, "start_booking", {"full_name": "James Wilson", "returning": True, "date_of_birth": WRONG_DOB,
                              "place": "Downtown", "near": True})
    out = step(s, "start_booking", dict(JAMES))
    assert out.result["ok"] is True and s.stage == VISIT_TYPE
    p = s.card.preferences
    assert p.days == ["Thursday"] and p.visit_description == "knee MRI" and (p.location_hint, p.near) == ("Downtown", True)
    step(s, "choose_visit_type", {"visit_type_id": KNEE_MRI})
    assert offered(s) and all(st.weekday() == 3 for *_, st in offered(s))


BAD_ON_A_TRY = [
    ("day with a time", {"days": ["Thursday morning"], "visit_description": "knee MRI"}),
    ("two languages", {"language": "Spanish French", "days": ["Thursday"]}),
    ("someone else", {"doctor_name": "someone else", "days": ["Thursday"]}),
    ("near without a place", {"near": True, "days": ["Thursday"]}),
    ("unknown specialty", {"specialty": "Astrology", "days": ["Thursday"]}),
    ("unknown field", {"doctor": "Dr. Kim", "days": ["Thursday"]}),
]


@pytest.mark.parametrize("label,bad", BAD_ON_A_TRY, ids=[b[0] for b in BAD_ON_A_TRY])
def test_a_refused_value_on_a_failed_try_records_nothing(clinic, label, bad):
    s = new_call(clinic)
    # A first miss, so a try is already counted; the refused one must not count another or record wishes.
    step(s, "start_booking", {"full_name": "James Wilson", "returning": True, "date_of_birth": WRONG_DOB})
    refused_unchanged(s, "start_booking", {"full_name": "James Wilson", "returning": True,
                                           "date_of_birth": WRONG_DOB, **bad})
    assert s.card.preferences.days == [] and s.card.preferences.visit_description == ""


# ================================================================== the card's visit description
def test_accepted_visit_type_becomes_the_cards_visit_description(clinic):
    s = to_visit_type(clinic, NEW, visit_description="skin check")
    assert step(s, "choose_visit_type", {"visit_type_id": SKIN_CHECK}).result["ok"] is True
    assert s.card.preferences.visit_description == VT[SKIN_CHECK]["name"]
    assert "skin check" not in s.fill("{booking_card}")


def test_refused_visit_type_leaves_the_visit_description(clinic):
    s = to_visit_type(clinic, NEW, visit_description="knee MRI")
    assert step(s, "choose_visit_type", {"visit_type_id": KNEE_MRI}).result["ok"] is False
    assert s.card.preferences.visit_description == "knee MRI"


def test_wishes_sent_with_a_visit_the_caller_cant_book_still_count(clinic):
    # Decision 54: the visit can't be booked, but the day the caller said is still their wish.
    s = to_visit_type(clinic, NEW)
    out = step(s, "choose_visit_type", {"visit_type_id": KNEE_MRI, "days": ["Thursday"], "language": "Spanish"})
    assert out.result["ok"] is False and s.stage == VISIT_TYPE and not s.card.offered_options
    assert s.card.preferences.days == ["Thursday"] and s.card.preferences.language == "Spanish"
    assert s.card.choices.visit_type_id == ""


def test_a_bad_value_with_a_visit_the_caller_cant_book_records_nothing(clinic):
    s = to_visit_type(clinic, NEW)
    before = snapshot(s)
    out = step(s, "choose_visit_type", {"visit_type_id": KNEE_MRI, "days": ["Thursday morning"]})
    assert out.result["ok"] is False and snapshot(s) == before
