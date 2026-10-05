"""Fake patient records and the "caller" the rules check against.

Anyone we can't find is a new patient with no referrals on file.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .catalog import DATA_DIR
from .fuzzy import normalize, person_name_score


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
    """Outcome of looking a caller up by name."""

    status: str  # "found" | "not_found" | "several" (need date of birth to tell apart)
    caller: Optional[Caller] = None
    candidates: list = field(default_factory=list)  # names, when several match


class PatientDirectory:
    def __init__(self, records: list):
        self.records = records

    @classmethod
    def load(cls, data_dir: Path = DATA_DIR) -> "PatientDirectory":
        raw = json.loads((Path(data_dir) / "patients.json").read_text(encoding="utf-8"))
        return cls(raw["patients"])

    def lookup(self, name: str, date_of_birth: Optional[str] = None) -> LookupResult:
        """Find a returning patient by (possibly misheard) full name.

        Needs the first AND last name to match (forgivingly). If several records
        match, the date of birth (YYYY-MM-DD) tells them apart.
        """
        matches = []
        for r in self.records:
            score = person_name_score(name, r["name"])
            # A single word ("Wilson") is too weak to identify a patient.
            if score >= 0.8 and len(normalize(name).split()) >= 2:
                matches.append(r)
        if date_of_birth:
            matches = [r for r in matches if r.get("date_of_birth") == date_of_birth]
        if not matches:
            return LookupResult(status="not_found")
        if len(matches) > 1:
            return LookupResult(status="several", candidates=[r["name"] for r in matches])
        r = matches[0]
        return LookupResult(
            status="found",
            caller=Caller(
                name=r["name"], patient_id=r["id"], is_new_patient=False,
                referrals_on_file=list(r.get("referrals_on_file", [])),
            ),
        )
