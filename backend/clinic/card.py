"""The booking card: the small record the code keeps for each call.

The AI never edits it directly; it can only change it through tools, and the
code checks every change. Because conversation history is wiped on every stage
move, anything the caller said that matters later lives here.

Sections:
- caller       who is calling (new or returning, referrals on file)
- preferences  what they ASKED for, in their words; kept across stage moves
- choices      what the code has ACCEPTED; only filled when the rules pass
- status       in_progress | booked | handed_off
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Optional

from .catalog import Catalog
from .patients import Caller
from .slots import spoken_time

# Stage names (the agent graph uses the same names).
IDENTIFY = "identify"
VISIT_TYPE = "visit_type"
BOOKING = "booking"
END = "end"


@dataclass
class Preferences:
    visit_description: str = ""        # "knee MRI", "skin check"
    doctor_name_heard: str = ""        # "Dr. Garsha"
    preferred_provider_id: str = ""    # set when a doctor was chosen, then another part changed
    location_hint: str = ""            # "near Downtown"
    preferred_location_id: str = ""    # set when a location was chosen, then another part changed
    days: list = field(default_factory=list)  # weekday names ("Tuesday") or dates ("2026-10-13")
    time_of_day: str = ""              # "morning" | "afternoon" | ""
    soonest: bool = False
    language: str = ""                 # a language the doctor should speak


@dataclass
class Choices:
    specialty: str = ""
    visit_type_id: str = ""
    provider_id: str = ""
    location_id: str = ""
    slot: Optional[datetime] = None


@dataclass
class BookingCard:
    caller: Optional[Caller] = None
    preferences: Preferences = field(default_factory=Preferences)
    choices: Choices = field(default_factory=Choices)
    status: str = "in_progress"
    offered_options: list = field(default_factory=list)  # last options offered (list of Option)
    booking_id: str = ""

    # ---- changing a choice -------------------------------------------------
    def change_choice(self, what: str, new_value: str = "", days: Optional[list] = None,
                      time_of_day: str = "") -> str:
        """The caller changed their mind about one part of the booking.

        Clears that choice AND everything that depended on it, records the new
        wish as a preference, and returns the stage to go to. (From Farhaan's
        catch on the baseline call: switching from a skin check to a knee MRI
        must not silently keep, or silently drop, Dr. Garcia.)

        | change      | cleared                               | goes to  |
        | visit type  | specialty, visit type, doctor, location, time | visit_type |
        | doctor      | doctor, time (location kept as a wish) | booking |
        | location    | location, time (doctor kept as a wish) | booking |
        | time        | time (doctor + location kept as wishes) | booking |

        The doctor/location "kept as a wish" are honoured by the next search if
        they still fit, and reported if they don't.
        """
        c, prefs = self.choices, self.preferences
        what = what.lower().strip().replace(" ", "_")
        self.offered_options = []

        if what in ("visit_type", "visit", "reason", "service", "appointment_type"):
            if new_value:
                prefs.visit_description = new_value
            # Doctor/location wishes tied to the old visit are dropped as choices but
            # remembered as preferences, so the next search can say honestly whether they fit.
            if c.provider_id:
                prefs.preferred_provider_id = c.provider_id
            if c.location_id:
                prefs.preferred_location_id = c.location_id
            self.choices = Choices()
            return VISIT_TYPE

        if what in ("doctor", "provider"):
            if c.location_id:
                prefs.preferred_location_id = c.location_id
            prefs.doctor_name_heard = new_value
            prefs.preferred_provider_id = ""
            c.provider_id, c.location_id, c.slot = "", "", None
            return BOOKING if c.visit_type_id else VISIT_TYPE

        if what in ("location", "place", "clinic"):
            if c.provider_id:
                prefs.preferred_provider_id = c.provider_id
            prefs.location_hint = new_value
            prefs.preferred_location_id = ""
            c.provider_id, c.location_id, c.slot = "", "", None
            return BOOKING if c.visit_type_id else VISIT_TYPE

        if what in ("time", "day", "date", "slot"):
            if c.provider_id:
                prefs.preferred_provider_id = c.provider_id
            if c.location_id:
                prefs.preferred_location_id = c.location_id
            if days is not None:
                prefs.days = list(days)
            if time_of_day:
                prefs.time_of_day = time_of_day
            prefs.soonest = False
            c.provider_id, c.location_id, c.slot = "", "", None
            return BOOKING if c.visit_type_id else VISIT_TYPE

        raise ValueError(f"Unknown thing to change: {what!r}")

    # ---- views -------------------------------------------------------------
    def to_dict(self) -> dict:
        d = asdict(self)
        if self.choices.slot:
            d["choices"]["slot"] = self.choices.slot.isoformat()
        d["offered_options"] = [o.to_dict() if hasattr(o, "to_dict") else o for o in self.offered_options]
        return d

    def summary(self, catalog: Catalog) -> str:
        """Short plain-text view pasted into a stage's instructions ({booking_card})."""
        lines = []
        if self.caller:
            who = "new patient" if self.caller.is_new_patient else "returning patient"
            refs = ", ".join(self.caller.referrals_on_file) or "none"
            lines.append(f"Caller: {self.caller.name} ({who}; referrals on file: {refs})")
        p = self.preferences
        wishes = []
        if p.visit_description: wishes.append(f"visit: {p.visit_description}")
        if p.doctor_name_heard: wishes.append(f"doctor: {p.doctor_name_heard}")
        if p.preferred_provider_id: wishes.append(f"doctor: {catalog.providers[p.preferred_provider_id].name}")
        if p.location_hint: wishes.append(f"place: {p.location_hint}")
        if p.preferred_location_id: wishes.append(f"place: {catalog.locations[p.preferred_location_id].name}")
        if p.days: wishes.append("days: " + ", ".join(p.days))
        if p.time_of_day: wishes.append(f"time: {p.time_of_day}")
        if p.soonest: wishes.append("as soon as possible")
        if p.language: wishes.append(f"language: {p.language}")
        if wishes:
            lines.append("Caller asked for: " + "; ".join(wishes))
        c = self.choices
        agreed = []
        if c.visit_type_id: agreed.append(catalog.visit_types[c.visit_type_id].name)
        if c.provider_id: agreed.append(catalog.providers[c.provider_id].name)
        if c.location_id: agreed.append(catalog.locations[c.location_id].name)
        if c.slot: agreed.append(spoken_time(c.slot))
        if agreed:
            lines.append("Agreed so far: " + ", ".join(agreed))
        return "\n".join(lines) or "Nothing known yet."

    def read_back(self, catalog: Catalog) -> str:
        """The confirmation sentence, built from the card (never from the AI's memory),
        so what the caller hears always matches what gets saved."""
        c = self.choices
        vt = catalog.visit_types[c.visit_type_id]
        p = catalog.providers[c.provider_id]
        loc = catalog.locations[c.location_id]
        return (
            f"{vt.name} with {p.name} at {loc.name}, {loc.address}, "
            f"on {spoken_time(c.slot)}. It takes about {vt.duration_min} minutes."
        )
