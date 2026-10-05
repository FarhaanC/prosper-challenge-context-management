"""The booking rules, checked by code. The AI asks; this module says yes or no.

The catalog's 6 rules:
1. A doctor can only be booked at a location they work at.
2. A doctor can only be booked for visit types they offer.
3. Visit types needing equipment only at locations that have it.
4. Visit types needing a referral need one on file first.
5. New patients: only visit types that allow them, only doctors accepting them.
6. A doctor at several sites: the location must be settled before booking.
   (Built into the design: every option we offer is doctor + location + time
   together, and the final check refuses a booking with no location.)

Every "no" comes with a plain-English reason the agent can say out loud.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from .catalog import Catalog, Location, Provider, VisitType
from .patients import Caller
from .slots import Schedule


@dataclass
class Bookability:
    """Can THIS caller book THIS visit type at all?"""

    bookable: bool
    reasons: list = field(default_factory=list)   # why not, in plain words (most important first)
    valid_pairs: list = field(default_factory=list)  # [(Provider, Location)] that pass every rule


def pair_ok(caller: Caller, vt: VisitType, p: Provider, loc: Location) -> bool:
    """Rules 1, 2, 3 and the doctor half of rule 5, for one doctor at one location."""
    if loc.id not in p.location_ids:                                        # rule 1
        return False
    if vt.id not in p.appointment_type_ids:                                 # rule 2
        return False
    if vt.required_capability and vt.required_capability not in loc.capabilities:  # rule 3
        return False
    if caller.is_new_patient and not p.accepting_new_patients:              # rule 5 (doctor)
        return False
    return True


def valid_pairs(catalog: Catalog, caller: Caller, vt: VisitType) -> list:
    """Every (doctor, location) this caller could book this visit type with."""
    out = []
    for p in catalog.providers_offering(vt.id):
        for loc_id in p.location_ids:
            loc = catalog.locations[loc_id]
            if pair_ok(caller, vt, p, loc):
                out.append((p, loc))
    return out


def can_book_visit_type(catalog: Catalog, caller: Caller, visit_type_id: str) -> Bookability:
    vt = catalog.visit_types[visit_type_id]
    reasons = []
    offering = catalog.providers_offering(vt.id)

    if not offering:
        reasons.append("No doctor here currently offers this.")
    if caller.is_new_patient and not vt.new_patients_allowed:              # rule 5 (visit type)
        reasons.append("This is only for existing patients.")
    if vt.requires_referral and not caller.has_referral_for(vt.specialty):  # rule 4
        reasons.append(f"It needs a referral to {vt.specialty}, and there isn't one on file.")

    pairs = valid_pairs(catalog, caller, vt) if offering else []
    if offering and not pairs:
        if caller.is_new_patient and not any(p.accepting_new_patients for p in offering):
            reasons.append("No doctor who offers this is taking new patients right now.")
        elif vt.required_capability:
            reasons.append(f"None of the locations with the {vt.required_capability} equipment has a doctor for this.")
        else:
            reasons.append("There's no doctor and location combination available for this.")

    return Bookability(bookable=not reasons, reasons=reasons, valid_pairs=pairs if not reasons else [])


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
    """The final full check before saving. Returns a list of problems (empty = OK)."""
    problems = []
    if not visit_type_id or visit_type_id not in catalog.visit_types:
        return ["No valid visit type has been chosen."]
    if not provider_id or provider_id not in catalog.providers:
        return ["No valid doctor has been chosen."]
    if not location_id or location_id not in catalog.locations:
        return ["No location has been chosen."]                             # rule 6
    if not start:
        return ["No appointment time has been chosen."]

    vt = catalog.visit_types[visit_type_id]
    p = catalog.providers[provider_id]
    loc = catalog.locations[location_id]

    if location_id not in p.location_ids:
        problems.append(f"{p.name} doesn't work at {loc.name}.")
    if visit_type_id not in p.appointment_type_ids:
        problems.append(f"{p.name} doesn't offer {vt.name}.")
    if vt.required_capability and vt.required_capability not in loc.capabilities:
        problems.append(f"{loc.name} doesn't have the {vt.required_capability} equipment {vt.name} needs.")
    if vt.requires_referral and not caller.has_referral_for(vt.specialty):
        problems.append(f"{vt.name} needs a referral to {vt.specialty}, and there isn't one on file.")
    if caller.is_new_patient and not vt.new_patients_allowed:
        problems.append(f"{vt.name} is only for existing patients.")
    if caller.is_new_patient and not p.accepting_new_patients:
        problems.append(f"{p.name} isn't taking new patients.")
    if not problems and not schedule.is_open(provider_id, location_id, vt.duration_min, start, now):
        problems.append("That time is no longer available.")
    return problems
