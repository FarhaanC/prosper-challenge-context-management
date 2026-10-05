"""Find up to 3 bookable options (doctor + location + time) for this caller.

Only options that already pass every rule are returned, so the AI can't pick
an impossible one. Wishes that can't be met are not silently dropped: each
becomes a short plain-English note the agent says out loud, e.g.

  "None of the doctors called Garcia offer Skin Cancer Screening. ..."
  "There are 2 doctors called Maria Garcia who offer this: ..."

How the 3 options are picked:
- If the caller named a place, valid options are ranked by distance from it.
- Otherwise by soonest time.
- Options are spread across different doctor/location pairs first, then extra
  times, so the caller gets a real choice rather than three slots in a row.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from .card import Preferences
from .catalog import Catalog, distance_miles
from .patients import Caller
from .rules import can_book_visit_type
from .slots import Schedule, spoken_time

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


@dataclass
class Option:
    option_id: str
    provider_id: str
    provider_name: str
    location_id: str
    location_name: str
    start: datetime
    spoken: str
    distance_miles: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "option_id": self.option_id, "provider_id": self.provider_id,
            "provider_name": self.provider_name, "location_id": self.location_id,
            "location_name": self.location_name, "start": self.start.isoformat(),
            "spoken": self.spoken, "distance_miles": self.distance_miles,
        }


@dataclass
class OptionsResult:
    options: list = field(default_factory=list)  # [Option], at most `limit`
    notes: list = field(default_factory=list)    # wishes we couldn't meet, ambiguities, refusals
    bookable: bool = True

    def to_dict(self) -> dict:
        return {"bookable": self.bookable, "notes": self.notes, "options": [o.to_dict() for o in self.options]}


def _matches_day(start: datetime, days: list, now: datetime) -> bool:
    if not days:
        return True
    for d in days:
        d = str(d).strip().lower()
        if d == "today" and start.date() == now.date():
            return True
        if d == "tomorrow" and start.date() == (now + timedelta(days=1)).date():
            return True
        if d[:3] in [w[:3] for w in WEEKDAYS] and WEEKDAYS[start.weekday()].startswith(d[:3]):
            return True
        if d == start.date().isoformat():
            return True
    return False


def _matches_time(start: datetime, time_of_day: str) -> bool:
    t = (time_of_day or "").lower()
    if t == "morning":
        return start.hour < 12
    if t == "afternoon":
        return start.hour >= 12
    if t == "evening":
        return start.hour >= 15
    return True


def _doctor_list(providers, catalog: Catalog, limit: int = 3) -> str:
    seen, out = set(), []
    for p in providers:
        if p.id not in seen:
            seen.add(p.id)
            out.append(p.name)
    more = f" and {len(out) - limit} more" if len(out) > limit else ""
    return ", ".join(out[:limit]) + more


def _why_doctors_cant(caller: Caller, vt, doctors) -> str:
    """One short sentence on why none of these doctors fits, grouped by reason."""
    groups = {}
    for p in doctors:
        if vt.id not in p.appointment_type_ids:
            groups.setdefault(f"don't offer {vt.name}", []).append(f"{p.name} ({p.specialty})")
        elif caller.is_new_patient and not p.accepting_new_patients:
            groups.setdefault("aren't taking new patients", []).append(p.name)
        else:
            groups.setdefault(f"don't work at a location with the {vt.required_capability or 'right'} equipment",
                              []).append(p.name)
    parts = []
    for reason, names in groups.items():
        if len(names) == 1:
            reason = reason.replace("don't", "doesn't").replace("aren't", "isn't")
        joined = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
        parts.append(f"{joined} {reason}")
    return "; ".join(parts)


def find_options(
    catalog: Catalog,
    schedule: Schedule,
    caller: Caller,
    visit_type_id: str,
    prefs: Preferences,
    now: datetime,
    limit: int = 3,
) -> OptionsResult:
    vt = catalog.visit_types[visit_type_id]
    b = can_book_visit_type(catalog, caller, visit_type_id)
    if not b.bookable:
        return OptionsResult(bookable=False, notes=list(b.reasons))

    notes: list = []
    pairs = list(b.valid_pairs)  # [(Provider, Location)], all rule-checked

    # ---- doctor wish -------------------------------------------------------
    wanted, label = None, ""
    if prefs.preferred_provider_id and prefs.preferred_provider_id in catalog.providers:
        wanted = [catalog.providers[prefs.preferred_provider_id]]
        label = wanted[0].name
    elif prefs.doctor_name_heard:
        wanted = catalog.find_providers_by_name(prefs.doctor_name_heard)
        label = prefs.doctor_name_heard
        if not wanted:
            notes.append(f"I couldn't find a doctor called {label} here.")
    if wanted:
        ids = {p.id for p in wanted}
        fitting = [pr for pr in pairs if pr[0].id in ids]
        if fitting:
            pairs = fitting
            distinct = {pr[0].id for pr in fitting}
            if len(distinct) > 1:
                desc = []
                for pid in sorted(distinct):
                    p = catalog.providers[pid]
                    places = sorted({loc.name for q, loc in fitting if q.id == pid})
                    desc.append(f"{p.name}, {p.title} ({p.specialty}) at {' / '.join(places)}")
                notes.append(
                    f"There are {len(distinct)} doctors matching '{label}' who offer {vt.name}: "
                    + "; ".join(desc) + ". Ask the caller which one they mean."
                )
        else:
            notes.append(
                f"No doctor matching '{label}' can do this: {_why_doctors_cant(caller, vt, wanted)}. "
                f"{vt.specialty} doctors who can: {_doctor_list([p for p, _ in pairs], catalog)}."
            )

    # ---- language wish -----------------------------------------------------
    if prefs.language:
        lang = prefs.language.strip().lower()
        speaking = [pr for pr in pairs if lang in {l.lower() for l in pr[0].languages}]
        if speaking:
            pairs = speaking
        else:
            notes.append(f"None of the available doctors for this speaks {prefs.language}.")

    # ---- place wish --------------------------------------------------------
    point, point_label = None, ""
    if prefs.preferred_location_id and prefs.preferred_location_id in catalog.locations:
        loc = catalog.locations[prefs.preferred_location_id]
        point, point_label = (loc.lat, loc.lon), loc.name
        here = [pr for pr in pairs if pr[1].id == loc.id]
        if here:
            pairs = here
        else:
            notes.append(f"That isn't available at {loc.name}; these are the closest alternatives.")
    elif prefs.location_hint:
        place = catalog.resolve_place(prefs.location_hint)
        if place.kind == "location" and place.near:
            point, point_label = place.point, place.label
        elif place.kind == "location":
            point, point_label = place.point, place.label
            here = [pr for pr in pairs if pr[1].id == place.location_ids[0]]
            if here:
                pairs = here
            else:
                notes.append(f"{place.label} has no doctor available for {vt.name}; these are the closest alternatives.")
        elif place.kind == "landmark":
            point, point_label = place.point, place.label
        elif place.kind == "ambiguous":
            names = [catalog.locations[i].name for i in place.location_ids]
            notes.append(f"'{prefs.location_hint}' could mean {' or '.join(names)}. Ask the caller which one.")
            among = [pr for pr in pairs if pr[1].id in place.location_ids]
            if among:
                pairs = among
        else:
            notes.append(f"I don't recognise the place '{prefs.location_hint}'. Ask for a neighbourhood or one of our location names.")

    # ---- times -------------------------------------------------------------
    slots = {
        (p.id, loc.id): schedule.open_slots(p.id, loc.id, vt.duration_min, now)
        for p, loc in pairs
    }
    timed = {
        k: [s for s in v if _matches_day(s, prefs.days, now) and _matches_time(s, prefs.time_of_day)]
        for k, v in slots.items()
    }
    if (prefs.days or prefs.time_of_day) and not any(timed.values()):
        asked = " ".join(filter(None, [", ".join(prefs.days), prefs.time_of_day])).strip()
        notes.append(f"Nothing is open for '{asked}' in the next two weeks; these are the nearest other times.")
        timed = slots
    timed = {k: v for k, v in timed.items() if v}
    if not timed:
        notes.append("There are no open times for this in the next two weeks.")
        return OptionsResult(options=[], notes=notes)

    # ---- rank and pick -----------------------------------------------------
    def dist(loc_id: str) -> Optional[float]:
        return round(distance_miles(point, catalog.location_point(loc_id)), 1) if point else None

    keys = list(timed)
    if point:
        keys.sort(key=lambda k: (dist(k[1]), timed[k][0]))
    else:
        keys.sort(key=lambda k: timed[k][0])

    picked = []
    round_no = 0
    while len(picked) < limit and any(len(timed[k]) > round_no for k in keys):
        for k in keys:
            if len(picked) >= limit:
                break
            if len(timed[k]) > round_no:
                picked.append((k, timed[k][round_no]))
        round_no += 1
    if not point:
        picked.sort(key=lambda x: x[1])

    options = []
    for i, ((pid, lid), start) in enumerate(picked, 1):
        p, loc = catalog.providers[pid], catalog.locations[lid]
        d = dist(lid)
        where = f"{loc.name} ({loc.neighbourhood})" if loc.neighbourhood else loc.name
        spoken = f"{p.name} at {where}, {spoken_time(start)}"
        if d is not None and lid not in (prefs.preferred_location_id,) and d > 0.2:
            spoken += f", about {d} miles from {point_label}"
        options.append(Option(str(i), pid, p.name, lid, loc.name, start, spoken, d))
    return OptionsResult(options=options, notes=notes)
