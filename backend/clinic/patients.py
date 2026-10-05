"""Fake patient records, identity checks, and the "caller" the rules check against.

Identity rule (Farhaan's decision, 6 Oct): a returning patient is identified by
full name AND date of birth, as real clinics do.

- The name may be misheard, so it's matched forgivingly, but only by spelling
  (at least 75% alike per word), never by "sounds alike" alone: "Ahmad Kim" must
  not become Ahmed Khan.
- A surname alone ("Mr. Wilson") never identifies anyone.
- The date of birth must match exactly. If it doesn't, the result says so
  (`dob_mismatch`), so the agent asks again. A returning caller is never quietly
  treated as a new patient.
- Anyone whose name matches no record is a new patient with no referrals.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .catalog import DATA_DIR, CatalogError
from .fuzzy import name_tokens, normalize, person_match

DATE_FORMAT = re.compile(r"\d{4}-\d{2}-\d{2}")
# Spelling similarity per name word for patient names. Looser than for doctors
# (0.8) so two swapped letters in a short surname ("Kahn"/"Khan", 0.75) still
# match, but different names ("Tyler"/"Taylor" 0.73, "Kim"/"Khan" 0.29) don't.
# Safe because the date of birth must then match exactly.
PATIENT_NAME_SPELLING = 0.75


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
    """Outcome of identifying a caller.

    status:
      found                 name and date of birth match one record (caller is set)
      need_date_of_birth    the name matches a record; ask for the date of birth
      dob_mismatch          the name matches but the date of birth doesn't; ask again
      invalid_date_of_birth the date wasn't given as YYYY-MM-DD
      several               two records share this name AND date of birth (shouldn't happen)
      not_found             no record has this name: a new patient
    """

    status: str
    caller: Optional[Caller] = None
    message: str = ""

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "message": self.message,
            "caller": None if not self.caller else {
                "name": self.caller.name, "is_new_patient": self.caller.is_new_patient,
                "referrals_on_file": list(self.caller.referrals_on_file),
            },
        }


class PatientDirectory:
    def __init__(self, records: list):
        for r in records:
            missing = [k for k in ("id", "name", "date_of_birth") if not r.get(k)]
            if missing:
                raise CatalogError(f"Patient record {r!r} is missing {', '.join(missing)}.")
        self.records = records

    @classmethod
    def load(cls, data_dir: Path = DATA_DIR) -> "PatientDirectory":
        raw = json.loads((Path(data_dir) / "patients.json").read_text(encoding="utf-8"))
        return cls(raw["patients"])

    def _name_matches(self, name) -> list:
        if len(name_tokens(name)) < 2:  # counted AFTER removing titles: "Mr. Wilson" is one word
            return []
        matches = []
        for r in self.records:
            rank, _quality, first_and_last_matched = person_match(
                name, r["name"], allow_sounds_like=False, close_at=PATIENT_NAME_SPELLING)
            if rank and first_and_last_matched:
                matches.append(r)
        return matches

    def lookup(self, name, date_of_birth: Optional[str] = None) -> LookupResult:
        matches = self._name_matches(name)
        if not matches:
            return LookupResult("not_found", message="No patient record with this name: treat as a new patient.")
        if not date_of_birth or not str(date_of_birth).strip():
            return LookupResult("need_date_of_birth", message="Ask for the caller's date of birth to confirm who they are.")
        dob = str(date_of_birth).strip()
        if not DATE_FORMAT.fullmatch(dob):
            return LookupResult("invalid_date_of_birth", message="Pass the date of birth as YYYY-MM-DD.")
        exact = [r for r in matches if r["date_of_birth"] == dob]
        if not exact:
            return LookupResult("dob_mismatch", message="That date of birth doesn't match our records for this name. "
                                                         "Ask the caller to repeat their name and date of birth.")
        if len(exact) > 1:
            return LookupResult("several", message="More than one record matches; transfer to staff.")
        r = exact[0]
        return LookupResult("found", caller=Caller(
            name=r["name"], patient_id=r["id"], is_new_patient=False,
            referrals_on_file=list(r.get("referrals_on_file", [])),
        ))
