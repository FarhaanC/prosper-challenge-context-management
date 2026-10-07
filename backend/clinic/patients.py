"""Fake patient records, the identity check, and the "caller" the rules check against.

How a returning caller is identified (Farhaan's decisions, 6 Oct):

1. The agent asks for full name AND date of birth. Nothing is looked up until it
   has both, so the reply never depends on the name alone. (Otherwise anyone could
   say a neighbour's name and learn from the reply whether they're a patient.)
2. If no record matches, the agent says the same thing whatever was wrong
   ("Sorry, I couldn't find you") and asks once more.
3. If that fails too, it asks the caller to spell their last name, and tries again.
4. If that fails, it offers a choice: register as a new patient, or speak to staff.
   A returning caller is never quietly treated as new: they're told and they choose.
   Correct details are accepted at any step, and nobody is asked forever: after
   three unusable answers in a row (say, a one-word name), the same choice is offered.

Two patients with the same name are told apart by date of birth. If two share the
name AND the birthday, the code doesn't guess: the call goes to staff.

Name matching forgives mishearing, but only by spelling (at least 75% alike per
word), never by "sounds alike" alone, so "Ahmad Kim" can't become Ahmed Khan. A
spelled last name may be one letter out, because letters get misheard too (B/D, M/N).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional

from .catalog import DATA_DIR, CatalogError
from .fuzzy import letters_apart, name_tokens, normalize, person_match

DATE_FORMAT = re.compile(r"\d{4}-\d{2}-\d{2}")


def _is_iso_date(text: str) -> bool:
    """A real date written YYYY-MM-DD ("1984-03-12"; not "12/03/1984" or "1984-02-30")."""
    if not DATE_FORMAT.fullmatch(text):
        return False
    try:
        date.fromisoformat(text)
        return True
    except ValueError:
        return False
# Spelling similarity per spoken name word: "Kahn" finds Khan (0.75) and "Willson"
# finds Wilson, but "Tyler" doesn't find Taylor (0.73) and "Kim" doesn't find Khan.
PATIENT_NAME_SPELLING = 0.75
# A spelled-out last name may be this many letters out (one misheard letter).
SPELLED_LETTERS_ALLOWED = 1

# What the agent says at each step. One wording for every "not found", whatever was wrong.
SAY_NEED_BOTH = "Could I have your full name and date of birth, please?"
SAY_TRY_AGAIN = "Sorry, I couldn't find you. Could you tell me your full name and date of birth once more?"
SAY_SPELL = "Sorry, I still couldn't find you. Could you spell your last name for me, and give your date of birth again?"
SAY_OFFER = ("I'm sorry, I couldn't find your details. Would you like to register as a new patient, "
             "or shall I put you through to a member of staff?")
SAY_STAFF = "Let me put you through to a member of staff who can find your details."
# Answers we can't use at all (a one-word name, no date of birth) in a row before the
# agent stops asking and offers the same choice: register as new, or staff.
UNUSABLE_LIMIT = 3


@dataclass
class Caller:
    name: str
    patient_id: Optional[str] = None
    is_new_patient: bool = True
    referrals_on_file: list = field(default_factory=list)  # specialty names

    def has_referral_for(self, specialty: str) -> bool:
        return normalize(specialty) in {normalize(r) for r in self.referrals_on_file}


@dataclass
class LookupResult:
    """status: found | not_found | incomplete | same_name_and_birthday."""

    status: str
    caller: Optional[Caller] = None

    def to_dict(self) -> dict:
        return {"status": self.status, "caller": _caller_dict(self.caller)}


def _caller_dict(caller: Optional[Caller]) -> Optional[dict]:
    if caller is None:
        return None
    return {"name": caller.name, "is_new_patient": caller.is_new_patient,
            "referrals_on_file": list(caller.referrals_on_file)}


class PatientDirectory:
    def __init__(self, records: list):
        """Checks every record first and lists every problem at once, like the catalog."""
        if not isinstance(records, list):
            raise CatalogError("The patient data should be a list of patient records.")
        problems, seen, repeated = [], set(), set()
        for i, r in enumerate(records):
            if not isinstance(r, dict):
                problems.append(f"Patient entry #{i} isn't a record.")
                continue
            label = r.get("id").strip() if isinstance(r.get("id"), str) and r.get("id").strip() else f"#{i}"
            if label in seen and label not in repeated:  # said once, however many copies
                repeated.add(label)
                problems.append(f"Patient id {label} appears more than once.")
            seen.add(label)
            missing = [k for k in ("id", "name", "date_of_birth") if not r.get(k)]
            if missing:
                problems.append(f"Patient {label} is missing {', '.join(missing)}.")
            wrong = [k for k in ("id", "name", "date_of_birth") if r.get(k) and not isinstance(r[k], str)]
            dob = r.get("date_of_birth")
            if isinstance(dob, str) and dob and not _is_iso_date(dob):
                problems.append(f"Patient {label}: date_of_birth {dob!r} should be a real date written YYYY-MM-DD "
                                "(otherwise the patient could never be found).")
            refs = r.get("referrals_on_file", [])
            if not (isinstance(refs, list) and all(isinstance(x, str) for x in refs)):
                wrong.append("referrals_on_file")  # text here would be read letter by letter
            if wrong:
                problems.append(f"Patient {label}: {', '.join(wrong)} "
                                f"{'has' if len(wrong) == 1 else 'have'} the wrong kind of value.")
        if problems:
            raise CatalogError("The patient data has problems:\n- " + "\n- ".join(problems))
        self.records = records

    @classmethod
    def load(cls, data_dir: Path = DATA_DIR) -> "PatientDirectory":
        raw = json.loads((Path(data_dir) / "patients.json").read_text(encoding="utf-8"))
        return cls(raw["patients"])

    def lookup(self, name, date_of_birth, spelled_last_name: Optional[str] = None) -> LookupResult:
        """Find one returning patient by full name AND date of birth (YYYY-MM-DD).

        Gives the same `not_found` whether the name or the date was wrong, and
        `incomplete` (without looking anything up) if either is missing.
        """
        dob = str(date_of_birth or "").strip()
        spelled = str(spelled_last_name or "").strip() or None
        enough_name = len(name_tokens(name)) >= (1 if spelled else 2)  # a spelled surname + first name is enough
        if not enough_name or not DATE_FORMAT.fullmatch(dob):
            return LookupResult("incomplete")
        matches = [r for r in self.records
                   if r["date_of_birth"] == dob and self._same_person(name, r["name"], spelled)]
        if not matches:
            return LookupResult("not_found")
        if len(matches) > 1:
            return LookupResult("same_name_and_birthday")
        r = matches[0]
        return LookupResult("found", Caller(
            name=r["name"], patient_id=r["id"], is_new_patient=False,
            referrals_on_file=list(r.get("referrals_on_file", [])),
        ))

    @staticmethod
    def _same_person(heard_name, record_name: str, spelled_last_name: Optional[str]) -> bool:
        if spelled_last_name:
            heard_first = name_tokens(heard_name)[0]
            record_t = name_tokens(record_name)
            first_ok = person_match(heard_first, record_t[0], allow_sounds_like=False,
                                    close_at=PATIENT_NAME_SPELLING).whole_name
            return bool(first_ok) and letters_apart(spelled_last_name, record_t[-1]) <= SPELLED_LETTERS_ALLOWED
        rank = person_match(heard_name, record_name, allow_sounds_like=False, close_at=PATIENT_NAME_SPELLING)
        return bool(rank.whole_name)


@dataclass
class IdentityStep:
    """What happened on one try, and what the agent should say next.

    status:
      found                 identified; `caller` is set
      need_both             name or date of birth missing or unusable; ask again
      try_again             not found on the first try; ask once more
      spell_last_name       not found twice; ask them to spell their last name
      offer_new_or_staff    not found after spelling (or too many unusable answers):
                            offer to register as a new patient, or staff
      hand_to_staff         two patients share this name and birthday; don't guess
    """

    status: str
    say: str
    caller: Optional[Caller] = None

    def to_dict(self) -> dict:
        return {"status": self.status, "say": self.say, "caller": _caller_dict(self.caller)}


@dataclass
class IdentityCheck:
    """Counts the tries for one call, so the agent follows the steps in order.

    Every try is looked up, so correct details are accepted at any step. A miss
    moves one step on: try again, then spell the last name, then the choice. Once
    the choice is offered it stays offered. Unusable answers don't count as misses,
    but after UNUSABLE_LIMIT in a row the agent offers the choice too.
    """

    failed_tries: int = 0
    unusable_in_a_row: int = 0
    offered_choice: bool = False

    def attempt(self, directory: PatientDirectory, name, date_of_birth,
                spelled_last_name: Optional[str] = None) -> IdentityStep:
        spelled = str(spelled_last_name or "").strip() or None
        result = directory.lookup(name, date_of_birth, spelled)
        if result.status == "found":
            first = result.caller.name.split()[0]
            return IdentityStep("found", f"Thank you, {first}. I've found your details.", result.caller)
        if result.status == "same_name_and_birthday":
            return IdentityStep("hand_to_staff", SAY_STAFF)
        if result.status == "incomplete":
            self.unusable_in_a_row += 1
            if self.offered_choice or self.unusable_in_a_row >= UNUSABLE_LIMIT:
                self.offered_choice = True
                return IdentityStep("offer_new_or_staff", SAY_OFFER)
            return IdentityStep("need_both", SAY_NEED_BOTH)
        self.unusable_in_a_row = 0
        if self.offered_choice:
            return IdentityStep("offer_new_or_staff", SAY_OFFER)
        if self.failed_tries >= 2 and not spelled:
            return IdentityStep("spell_last_name", SAY_SPELL)  # the third try must be spelled
        self.failed_tries += 1
        if self.failed_tries == 1:
            return IdentityStep("try_again", SAY_TRY_AGAIN)
        if self.failed_tries == 2:
            return IdentityStep("spell_last_name", SAY_SPELL)
        self.offered_choice = True
        return IdentityStep("offer_new_or_staff", SAY_OFFER)
