"""The six caller scenarios, and one extra check (decision 87).

Each scenario is a persona and goal for the AI-played caller, plus the expected outcome,
which the scoring checks in code against what was actually saved.

The expected answers were worked out by hand from the raw catalog
(backend/data/catalog.json) and the fake patients (backend/data/patients.json), not
from our code's output, so a bug in our code can't make its own test pass:

- Skin checks: Skin Cancer Screening (appt_027) and Full Body Skin Exam (appt_028) need
  no referral and allow new patients. The doctors offering them are prov_001 Daniel Chen,
  prov_027 Kenji Kim, prov_035 Daniel Smith (taking new patients) and prov_048 Wei Sato
  (not taking new patients). No Garcia offers them: the three Garcias are a children's
  doctor (prov_002) and two family doctors (prov_003, prov_008).
- Knee MRI (appt_065): needs a referral, existing patients only, and imaging equipment.
  It's offered by prov_014 Linda Ramirez (Mission Bay loc_000, Downtown loc_004) and
  prov_015 Hannah Nguyen (Mission Bay loc_000, Midtown loc_005). Mission Bay has no
  imaging, so the only valid pairs are Ramirez at Downtown and Nguyen at Midtown.
  James Wilson (pat_001, born 1984-03-12) has a Radiology referral on file.
- Dr. Maria Garcia: prov_002 (Pediatrics, Mission Bay) and prov_003 (Family Medicine,
  North Beach, Midtown, Richmond). Both take new patients. prov_003's check-up visits that
  allow new patients: New Patient Consultation (appt_000), New Patient Visit (appt_001),
  Annual Physical (appt_002), Annual Wellness Visit (appt_003).
- OB/GYN: one doctor, prov_036 Linda Nguyen, not taking new patients, so no new patient
  can book any OB/GYN visit.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

BOOKED, NOT_BOOKED, HANDED_OFF = "booked", "not_booked", "handed_off"


@dataclass(frozen=True)
class Expected:
    outcome: str                         # booked | not_booked | handed_off
    visit_types: frozenset = frozenset()  # booked: the visit must be one of these
    providers: frozenset = frozenset()    # booked: the doctor must be one of these
    pairs: frozenset = frozenset()        # booked: (doctor, location) must be one of these, if given


@dataclass(frozen=True)
class Scenario:
    id: str
    title: str
    persona: str
    expected: Expected
    patient_id: Optional[str] = None   # the real caller, for scoring: a returning patient's id...
    new_patient_name: str = ""         # ...or a new patient's name
    check_in_after_read_back: bool = False  # the extra check of decision 71


SKIN_CHECKS = frozenset({"appt_027", "appt_028"})
DERMATOLOGISTS_FOR_NEW = frozenset({"prov_001", "prov_027", "prov_035"})
KNEE_MRI = frozenset({"appt_065"})
KNEE_MRI_PAIRS = frozenset({("prov_014", "loc_004"), ("prov_015", "loc_005")})
MARIA_GARCIA_FAMILY = frozenset({"prov_003"})
CHECK_UPS = frozenset({"appt_000", "appt_001", "appt_002", "appt_003"})

_JAMES = ("Your name is James Wilson, and you've been a patient here before. Your date of birth is "
          "March 12th, 1984. ")
_THEN_BOOK = ("When asked whether to book it, say yes. Then thank them and say goodbye.")

SCENARIOS = [
    Scenario(
        "garcia_skin_check", "New patient: a skin check with Dr. Garcia (no Garcia does skin checks)",
        "Your name is Lena Park (spelled L, E, N, A and P, A, R, K). You have never been a patient here. You'd "
        "like a skin check for a couple of moles, and a friend recommended Dr. Garcia, so you ask for Dr. "
        "Garcia. If you're told Dr. Garcia can't do it, you're happy with one of the other doctors offered. If "
        "asked which kind of skin visit, say you just want your moles checked and you don't mind which. Any day "
        "in the next two weeks is fine: accept the first time offered. " + _THEN_BOOK,
        Expected(BOOKED, SKIN_CHECKS, DERMATOLOGISTS_FOR_NEW), new_patient_name="Lena Park"),
    Scenario(
        "knee_mri_new_patient", "New patient: a knee MRI (needs a referral; existing patients only)",
        "Your name is Omar Haddad (spelled O, M, A, R and H, A, D, D, A, D). You have never been a patient "
        "here. Your knee has been hurting and you want to book a knee MRI. You don't have a referral. If you're "
        "told you can't book it, ask once whether there's anything else you can do, listen, then say you'll "
        "sort it out with your own doctor first, thank them and say goodbye. Don't book anything else.",
        Expected(NOT_BOOKED), new_patient_name="Omar Haddad"),
    Scenario(
        "james_knee_mri_downtown", "James Wilson: a knee MRI near Downtown (only 2 valid doctor-place pairs)",
        _JAMES + "Your doctor referred you for a knee MRI, and you'd like it somewhere near Downtown. Any day is "
        "fine: accept the first option offered. " + _THEN_BOOK,
        Expected(BOOKED, KNEE_MRI, pairs=KNEE_MRI_PAIRS), patient_id="pat_001"),
    Scenario(
        "james_changes_to_mri", "James Wilson: a Garcia skin check, then 'actually, a knee MRI'",
        _JAMES + "Start by asking for a skin check with Dr. Garcia. Once the agent has started on that (it has "
        "told you something about doctors, visit types or times for the skin check), change your mind: say the "
        "skin check can wait, and what you really need is a knee MRI, which your doctor referred you for. Any "
        "day and any location is fine: accept the first option offered. " + _THEN_BOOK,
        Expected(BOOKED, KNEE_MRI, pairs=KNEE_MRI_PAIRS), patient_id="pat_001"),
    Scenario(
        "maria_garcia_checkup", "New patient: a check-up with Dr. Maria Garcia (there are two)",
        "Your name is Priya Nair (spelled P, R, I, Y, A and N, A, I, R). You're an adult and have never been a "
        "patient here. You'd like a yearly check-up with Dr. Maria Garcia, whom a colleague recommended. If "
        "you're asked which Dr. Maria Garcia, say the family medicine one, not the children's doctor. If you're "
        "offered more than one Dr. Maria Garcia, choose the family medicine one. If asked what kind of check-up, "
        "say a yearly physical, and you don't mind which of the similar ones. Any day is fine: accept the first "
        "option with the family medicine Dr. Maria Garcia. " + _THEN_BOOK,
        Expected(BOOKED, CHECK_UPS, MARIA_GARCIA_FAMILY), new_patient_name="Priya Nair"),
    Scenario(
        "obgyn_new_then_person", "New patient: an OB/GYN visit (no OB/GYN takes new patients), then 'a person'",
        "Your name is Sofia Reyes (spelled S, O, F, I, A and R, E, Y, E, S). You have never been a patient "
        "here. You'd like an annual well-woman exam with an OB/GYN. If you're told that can't be booked for "
        "you, ask to speak to a person about it. Once they tell you someone will call you back, thank them and "
        "say goodbye.",
        Expected(HANDED_OFF), new_patient_name="Sofia Reyes"),
]

# Decision 71: a "Yes" to "Are you still there?" after the read-back only means the caller is
# still there. The loop says the check-in right after the read-back, as the silence watch would.
CHECK_IN_SCENARIO = Scenario(
    "check_in_after_read_back", "James Wilson's knee MRI, with 'Are you still there?' after the read-back",
    _JAMES + "Your doctor referred you for a knee MRI. Any day and any location is fine: accept the first option "
    "offered. If the agent asks \"Are you still there?\", answer only \"Yes.\" and nothing else. " + _THEN_BOOK,
    Expected(BOOKED, KNEE_MRI, pairs=KNEE_MRI_PAIRS), patient_id="pat_001", check_in_after_read_back=True)

BY_ID = {s.id: s for s in SCENARIOS + [CHECK_IN_SCENARIO]}
