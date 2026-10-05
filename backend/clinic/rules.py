"""The booking rules, checked by code. The AI asks; this module says yes or no.

The catalog's 6 rules:
1. A doctor can only be booked at a location they work at.
2. A doctor can only be booked for visit types they offer.
3. Visit types needing equipment only at locations that have it.
4. Visit types needing a referral need one on file first.
5. New patients: only visit types that allow them, only doctors accepting them.
6. A doctor at several sites: the location must be settled before booking.
   Built into the design: every option offered is doctor + location + time
   together, and the final check refuses a booking with no location.

Each rule is written ONCE, in `visit_type_problems` (rules 4 and 5, visit-type
half) or `pair_problems` (rules 1, 2, 3 and 5, doctor half). Everything else
(can-book checks, the final check, explanations in options.py) uses these two
functions, so the rules can't drift apart. Every "no" is a plain sentence the
agent can say out loud.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from .catalog import Catalog, Location, Provider, VisitType
from .patients import Caller
from .slots import Schedule

# Specialties whose doctors can see a patient first and decide whether a
# referral is needed. Used for the alternative offered when a visit is refused.
PRIMARY_CARE = ("General", "Family Medicine", "Internal Medicine")


@dataclass(frozen=True)
class RuleProblem:
    rule: int     # the catalog rule number, 1-6
    reason: str   # a sentence the agent can say


def visit_type_problems(caller: Caller, vt: VisitType) -> list:
    """Rules about the caller and the visit type alone (4, and the visit-type half of 5)."""
    out = []
    if caller.is_new_patient and not vt.new_patients_allowed:
        out.append(RuleProblem(5, f"{vt.name} is only for existing patients."))
    if vt.requires_referral and not caller.has_referral_for(vt.specialty):
        out.append(RuleProblem(4, f"{vt.name} needs a referral to {vt.specialty}, and there isn't one on file."))
    return out


def pair_problems(caller: Caller, vt: VisitType, p: Provider, loc: Location) -> list:
    """Rules about one doctor at one location (1, 2, 3, and the doctor half of 5)."""
    out = []
    if loc.id not in p.location_ids:
        out.append(RuleProblem(1, f"{p.name} doesn't work at {loc.name}."))
    if vt.id not in p.appointment_type_ids:
        out.append(RuleProblem(2, f"{p.name} doesn't offer {vt.name}."))
    if vt.required_capability and vt.required_capability not in loc.capabilities:
        out.append(RuleProblem(3, f"{loc.name} doesn't have the {vt.required_capability} equipment {vt.name} needs."))
    if caller.is_new_patient and not p.accepting_new_patients:
        out.append(RuleProblem(5, f"{p.name} isn't taking new patients."))
    return out


def valid_pairs(catalog: Catalog, caller: Caller, vt: VisitType) -> list:
    """Every (doctor, location) that breaks none of rules 1, 2, 3, 5 for this visit type."""
    out = []
    for p in catalog.providers_offering(vt.id):
        for loc_id in p.location_ids:
            loc = catalog.locations[loc_id]
            if not pair_problems(caller, vt, p, loc):
                out.append((p, loc))
    return out


@dataclass
class Bookability:
    """Can THIS caller book THIS visit type at all? (Time slots are checked later.)"""

    bookable: bool
    reasons: list = field(default_factory=list)      # why not, as sentences
    valid_pairs: list = field(default_factory=list)  # [(Provider, Location)] that pass every rule

    def to_dict(self) -> dict:
        return {"bookable": self.bookable, "reasons": list(self.reasons)}


def can_book_visit_type(catalog: Catalog, caller: Caller, visit_type_id) -> Bookability:
    vt = catalog.visit_types.get(visit_type_id) if isinstance(visit_type_id, str) else None
    if vt is None:
        return Bookability(False, [f"'{visit_type_id}' isn't a visit type in the catalog."])

    reasons = []
    offering = catalog.providers_offering(vt.id)
    if not offering:
        reasons.append(f"No doctor here currently offers {vt.name}.")
    reasons += [p.reason for p in visit_type_problems(caller, vt)]

    pairs = valid_pairs(catalog, caller, vt)
    if offering and not pairs:
        if caller.is_new_patient and not any(p.accepting_new_patients for p in offering):
            reasons.append(f"No doctor who offers {vt.name} is taking new patients right now.")
        else:
            reasons.append(f"No location has both a doctor for {vt.name} and the equipment it needs.")
    if reasons:
        return Bookability(False, reasons)
    return Bookability(True, [], pairs)


def alternatives_for(catalog: Catalog, caller: Caller, visit_type_id: str, limit: int = 1) -> list:
    """What to offer when a visit type is refused: a primary-care visit this caller CAN book
    (a new-patient visit for new patients, a follow-up for returning ones). The agent must
    not promise that this visit produces a referral."""
    candidates = [vt for vt in catalog.visit_types.values()
                  if vt.specialty in PRIMARY_CARE and vt.id != visit_type_id
                  and can_book_visit_type(catalog, caller, vt.id).bookable]
    candidates.sort(key=lambda vt: vt.new_patients_allowed != caller.is_new_patient)  # best fit first, stable
    return candidates[:limit]


def check_booking(
    catalog: Catalog,
    schedule: Schedule,
    caller: Caller,
    visit_type_id: Optional[str],
    provider_id: Optional[str],
    location_id: Optional[str],
    start: Optional[datetime],
    now: datetime,
) -> list:
    """The final full check before saving. Returns the problems as sentences (empty = OK)."""
    if visit_type_id not in catalog.visit_types:
        return ["No valid visit type has been chosen."]
    if provider_id not in catalog.providers:
        return ["No valid doctor has been chosen."]
    if location_id not in catalog.locations:
        return ["No location has been chosen."]  # rule 6
    if not start:
        return ["No appointment time has been chosen."]

    vt = catalog.visit_types[visit_type_id]
    p = catalog.providers[provider_id]
    loc = catalog.locations[location_id]
    problems = [x.reason for x in visit_type_problems(caller, vt) + pair_problems(caller, vt, p, loc)]
    if not problems and not schedule.is_open(provider_id, location_id, vt.duration_min, start, now):
        problems.append("That time is no longer available.")
    return problems
