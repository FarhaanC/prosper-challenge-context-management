"""The booking card: the small record the code keeps for each call.

The AI never edits it directly; it can only change it through tools, and the
code checks every change. Because conversation history is wiped on every stage
move, anything the caller said that matters later lives here.

Sections:
- caller       who is calling (new or returning, referrals on file)
- preferences  what they ASKED for; kept across stage moves
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

CHANGEABLE = {
    "visit_type": "visit_type", "visit": "visit_type", "reason": "visit_type", "service": "visit_type",
    "appointment_type": "visit_type",
    "doctor": "doctor", "provider": "doctor",
    "location": "location", "place": "location", "clinic": "location",
    "time": "time", "day": "time", "date": "time", "slot": "time",
}
CLEAR_WORDS = {"any", "anytime", "any time", "any day", "whenever", "no preference"}


@dataclass
class Preferences:
    """What the caller asked for.

    Each kind of wish has two forms, and at most one is set at a time:
    - what the caller SAID (doctor_name_heard, location_hint), and
    - a choice carried over from earlier in the call (preferred_provider_id,
      preferred_location_id), kept when the caller changed something else.
    find_options treats what the caller said as stronger than what was carried over,
    and the most recent change (`latest`) as strongest of all.
    """

    visit_description: str = ""        # "knee MRI", "skin check"
    doctor_name_heard: str = ""        # "Dr. Garsha"
    preferred_provider_id: str = ""
    location_hint: str = ""            # "near Downtown", "the Midtown one"
    preferred_location_id: str = ""
    days: list = field(default_factory=list)  # "Thursday", "today", "tomorrow" or "2026-10-13"
    time_of_day: str = ""              # "morning" (before 12:00) | "afternoon" (12:00 or later) | ""
    soonest: bool = False              # rank by earliest time even when a place was named
    language: str = ""                 # a language the doctor should speak
    latest: str = ""                   # the last thing the caller changed: doctor | location | time | ""


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
    offered_options: list = field(default_factory=list)  # options currently on offer (list of Option)
    next_option_number: int = 1  # option numbers keep counting up through the call
    booking_id: str = ""

    # ---- options on offer --------------------------------------------------
    def remember_offer(self, options: list) -> None:
        """Record what was just offered. Older options are no longer on offer, and
        their numbers are never reused, so a stale "option 2" can't book the wrong slot."""
        self.offered_options = list(options)
        if options:
            self.next_option_number = max(int(o.option_id) for o in options) + 1

    def offered(self, option_id) -> Optional[object]:
        """The option with this number if it's currently on offer, else None."""
        return next((o for o in self.offered_options if o.option_id == str(option_id).strip()), None)

    # ---- changing a choice -------------------------------------------------
    def change_choice(self, what: str, new_value: str = "", days: Optional[list] = None,
                      time_of_day: str = "") -> str:
        """The caller changed their mind about one part of the booking.

        Clears that choice and everything that depended on it, records the new wish,
        marks it as the latest change, and returns the stage to go to. (From
        Farhaan's catch on the baseline call: switching from a skin check to a knee
        MRI must not silently keep, or silently drop, Dr. Garcia.)

        | change     | cleared                                   | carried over as a weaker wish | goes to    |
        | visit type | specialty, visit type, doctor, place, time | doctor, place                 | visit_type |
        | doctor     | doctor, place, time                        | place                         | booking    |
        | location   | doctor, place, time                        | doctor                        | booking    |
        | time       | doctor, place, time                        | doctor, place                 | booking    |

        Doctor, place and time are cleared together because one option is always the
        three together. Without a chosen visit type, every change goes to visit_type.
        """
        kind = CHANGEABLE.get(str(what).lower().strip().replace(" ", "_"))
        if kind is None:
            raise ValueError(f"Can't change {what!r}; choose visit type, doctor, location or time.")
        c, prefs = self.choices, self.preferences
        self.offered_options = []

        # What was chosen becomes a weaker wish, unless it's the thing being changed.
        if c.provider_id and kind != "doctor":
            prefs.preferred_provider_id, prefs.doctor_name_heard = c.provider_id, ""
        if c.location_id and kind != "location":
            prefs.preferred_location_id, prefs.location_hint = c.location_id, ""

        if kind == "visit_type":
            if new_value:
                prefs.visit_description = new_value
            prefs.latest = ""
            self.choices = Choices()
            return VISIT_TYPE

        if kind == "doctor":
            prefs.doctor_name_heard, prefs.preferred_provider_id = new_value, ""
        elif kind == "location":
            prefs.location_hint, prefs.preferred_location_id = new_value, ""
        elif kind == "time":
            wished = list(days) if days is not None else ([new_value] if new_value else [])
            prefs.days = [] if any(str(d).lower().strip() in CLEAR_WORDS for d in wished) else wished
            if time_of_day:
                prefs.time_of_day = "" if time_of_day.lower().strip() in CLEAR_WORDS else time_of_day
            prefs.soonest = False
        prefs.latest = kind
        c.provider_id, c.location_id, c.slot = "", "", None
        return BOOKING if c.visit_type_id else VISIT_TYPE

    # ---- views -------------------------------------------------------------
    def to_dict(self) -> dict:
        d = asdict(self)
        if self.choices.slot:
            d["choices"]["slot"] = self.choices.slot.isoformat()
        d["offered_options"] = [o.to_dict() for o in self.offered_options]
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
        if p.visit_description:
            wishes.append(f"visit: {p.visit_description}")
        doctor = catalog.providers[p.preferred_provider_id].name if p.preferred_provider_id else p.doctor_name_heard
        if doctor:
            wishes.append(f"doctor: {doctor}")
        place = catalog.locations[p.preferred_location_id].name if p.preferred_location_id else p.location_hint
        if place:
            wishes.append(f"place: {place}")
        if p.days:
            wishes.append("days: " + ", ".join(p.days))
        if p.time_of_day:
            wishes.append(f"time: {p.time_of_day}")
        if p.soonest:
            wishes.append("as soon as possible")
        if p.language:
            wishes.append(f"language: {p.language}")
        if wishes:
            lines.append("Caller asked for: " + "; ".join(wishes))
        c = self.choices
        agreed = []
        if c.visit_type_id:
            agreed.append(catalog.visit_types[c.visit_type_id].name)
        if c.provider_id:
            agreed.append(catalog.providers[c.provider_id].name)
        if c.location_id:
            agreed.append(catalog.locations[c.location_id].name)
        if c.slot:
            agreed.append(spoken_time(c.slot))
        if agreed:
            lines.append("Agreed so far: " + ", ".join(agreed))
        return "\n".join(lines) or "Nothing known yet."

    def read_back(self, catalog: Catalog) -> str:
        """The confirmation sentence, built from the card (never from the AI's memory),
        so what the caller hears always matches what gets saved."""
        c = self.choices
        if not (c.visit_type_id and c.provider_id and c.location_id and c.slot):
            raise ValueError("The booking card isn't complete yet: choose an option first.")
        vt = catalog.visit_types[c.visit_type_id]
        p = catalog.providers[c.provider_id]
        loc = catalog.locations[c.location_id]
        return (
            f"{vt.name} with {p.name} at {loc.name}, {loc.address}, "
            f"on {spoken_time(c.slot)}. It takes about {vt.duration_min} minutes."
        )
