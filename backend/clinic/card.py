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
from .fuzzy import looks_like_a_sentence, means_no_preference
from .patients import Caller, IdentityCheck
from .slots import spoken_time

# Stage names (the agent graph uses the same names).
IDENTIFY = "identify"
VISIT_TYPE = "visit_type"
BOOKING = "booking"
END = "end"

# The kinds of wish a caller can have. card.py and options.py both use these names,
# so "the latest change" always means the same thing in both. (Round 2 found a bug
# where one file said "location" and the other "place".)
DOCTOR, LOCATION, TIME, LANGUAGE = "doctor", "location", "time", "language"
VISIT = "visit_type"

CHANGEABLE = {
    "visit_type": VISIT, "visit": VISIT, "reason": VISIT, "service": VISIT, "appointment_type": VISIT,
    "doctor": DOCTOR, "provider": DOCTOR,
    "location": LOCATION, "place": LOCATION, "clinic": LOCATION,
    "time": TIME, "day": TIME, "date": TIME, "slot": TIME,
    "language": LANGUAGE,
}
TIMES_OF_DAY = ("morning", "afternoon")
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
    days: list = field(default_factory=list)  # each one of: "Thursday", "today", "tomorrow", "2026-10-13"
    time_of_day: str = ""              # "morning" (before 12:00) | "afternoon" (12:00 or later) | ""
    soonest: bool = False              # rank by earliest time even when a place was named
    language: str = ""                 # a language the doctor should speak
    not_provider_ids: list = field(default_factory=list)  # doctors the caller turned down (turn_down_doctors)
    latest: str = ""                   # the last thing changed: DOCTOR | LOCATION | TIME | LANGUAGE | ""


@dataclass
class Choices:
    specialty: str = ""
    visit_type_id: str = ""
    provider_id: str = ""
    location_id: str = ""
    slot: Optional[datetime] = None


def turned_down_ids(catalog: Catalog, prefs: Preferences) -> set:
    """The doctors the caller turned down and hasn't asked for again since.

    Asking for a turned-down doctor by a name that picks out that one doctor
    ("Dr. Daniel Chen") brings them back. A name that fits several different doctors
    ("Dr. Chen") doesn't: the caller may well mean one of the others. Two doctors
    who share the exact same name are treated as one name. Unknown ids are ignored.
    """
    down = {i for i in prefs.not_provider_ids or [] if i in catalog.providers}
    heard = " ".join(str(prefs.doctor_name_heard or "").split())
    if down and heard and not means_no_preference(heard) and not looks_like_a_sentence(heard):
        matches = catalog.match_providers(heard)
        if len({m.provider.name for m in matches}) == 1:
            down -= {m.provider.id for m in matches}
    return down


@dataclass
class BookingCard:
    caller: Optional[Caller] = None
    preferences: Preferences = field(default_factory=Preferences)
    choices: Choices = field(default_factory=Choices)
    status: str = "in_progress"
    offered_options: list = field(default_factory=list)  # options currently on offer (list of Option)
    next_option_number: int = 1  # option numbers keep counting up through the call
    identity: IdentityCheck = field(default_factory=IdentityCheck)  # tries so far at finding the caller

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

    def choose_option(self, option_id) -> object:
        """The caller picked an option on offer: put its doctor, place and time on the
        card. A doctor they pick is no longer turned down, from this moment on (even if
        they turned that doctor down earlier and were offered them because nobody else
        could do it). Raises ValueError if that option isn't on offer."""
        option = self.offered(option_id)
        if option is None:
            on_offer = ", ".join(o.option_id for o in self.offered_options) or "none"
            raise ValueError(f"Option {option_id} isn't on offer (on offer now: {on_offer}).")
        c = self.choices
        c.provider_id, c.location_id, c.slot = option.provider_id, option.location_id, option.start
        self._no_longer_turned_down(option.provider_id)
        return option

    # ---- changing a choice -------------------------------------------------
    def change_choice(self, what: str, new_value: str = "", days: Optional[list] = None,
                      time_of_day: Optional[str] = None) -> str:
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

        What new_value means for each kind:
        - doctor: the doctor's name ("Dr. Daniel Chen"), or "" for no doctor wish.
          It is never read as an instruction: turning doctors down is its own
          method, turn_down_doctors. Naming a doctor who was turned down brings them
          back if the name picks out that one doctor (see turned_down_ids).
        - location: the caller's place words ("the Midtown one", "near Union Square").
        - time: plain values, never a phrase. `days` is a list where each entry is one
          weekday name, "today", "tomorrow" or a date (YYYY-MM-DD); [] clears the day
          wish. `time_of_day` is "morning", "afternoon", or "" to clear it. Leaving
          either out (None) keeps it, so time_of_day="afternoon" alone keeps an earlier
          "Thursday". new_value, if given, is one day (the same as days=[new_value]).
          The AI turns "this afternoon" into days=["today"], time_of_day="afternoon".
          Values are checked when options are searched (find_options refuses anything
          else with a note saying how to pass it).
        - language: one language name ("Spanish"), or "" to clear it.

        "No preference" words ("don't mind", "any") count as "" for every kind.
        """
        kind = CHANGEABLE.get(str(what).lower().strip().replace(" ", "_"))
        if kind is None:
            raise ValueError(f"Can't change {what!r}; choose visit type, doctor, location, time or language.")
        said = " ".join(str(new_value or "").split())
        if kind == TIME and said and days is not None:
            raise ValueError("Pass the day either as new_value or in days, not both.")
        prefs = self.preferences
        self._start_change(kind)

        if kind == VISIT:
            if new_value:
                prefs.visit_description = new_value
            prefs.latest, prefs.not_provider_ids = "", []
            self.choices = Choices()
            return VISIT_TYPE

        if kind == DOCTOR:
            prefs.doctor_name_heard, prefs.preferred_provider_id = said, ""
        elif kind == LOCATION:
            prefs.location_hint, prefs.preferred_location_id = said, ""
        elif kind == LANGUAGE:
            prefs.language = said
        elif kind == TIME:
            if said:
                days = [said]
            if days is not None:
                entries = [" ".join(str(d or "").split()) for d in days]
                prefs.days = [d for d in entries if d and not means_no_preference(d)]
            if time_of_day is not None:
                tod = " ".join(str(time_of_day).split()).lower()
                prefs.time_of_day = "" if means_no_preference(tod) else tod
            prefs.soonest = False
        return self._finish_change(kind)

    def turn_down_doctors(self, catalog: Catalog, provider_ids=(), on_offer: bool = False,
                          current: bool = False) -> str:
        """The caller doesn't want certain doctors ("someone else, please", "not Dr. Chen").

        The AI decides who the caller meant and says so exactly; this method never
        reads the caller's words. Any mix of:
        - provider_ids: these doctors (the tool layer turns a name into ids, and asks
          the caller "which one?" if the name fits several doctors);
        - on_offer: every doctor in the options currently on offer;
        - current: the doctor chosen, or if none, the one carried over from earlier.

        They're left out of later searches for the rest of the call, unless nobody
        else can do the visit (find_options says so), the caller names one of them
        again, or the caller picks one of them anyway (choose_option). A change of visit type starts
        the list again. Counts as a doctor change (see change_choice) and returns the
        stage to go to. Raises ValueError, changing nothing, if the instruction can't
        be followed.
        """
        if isinstance(provider_ids, str):  # one id on its own, not a list
            provider_ids = [provider_ids]
        ids = [str(i).strip() for i in (provider_ids or []) if str(i).strip()]
        unknown = [i for i in ids if i not in catalog.providers]
        if unknown:
            raise ValueError(f"No doctor has the id {', '.join(unknown)}. Use ids from the options or the catalog.")
        if on_offer:
            offered = [getattr(o, "provider_id", "") for o in self.offered_options]
            if not any(offered):
                raise ValueError("No options are on offer, so there are no doctors on offer to turn down.")
            ids += offered
        if current:
            doctor = self.choices.provider_id or self.preferences.preferred_provider_id
            if not doctor:
                raise ValueError("No doctor is chosen or carried over, so there is no current doctor to turn down.")
            ids.append(doctor)
        ids = {i for i in ids if i}
        if not ids:
            raise ValueError("Say which doctors to turn down: provider_ids, on_offer or current.")

        prefs = self.preferences
        self._start_change(DOCTOR)
        prefs.not_provider_ids = sorted(set(prefs.not_provider_ids) | ids)
        prefs.doctor_name_heard, prefs.preferred_provider_id = "", ""
        return self._finish_change(DOCTOR)

    def _start_change(self, kind: str) -> None:
        """Common start of every change: nothing is on offer any more, and what was
        chosen becomes a weaker wish, unless it's the thing being changed."""
        c, prefs = self.choices, self.preferences
        self.offered_options = []
        if c.provider_id:
            # A chosen doctor isn't turned down (choose_option already did this; this
            # covers a card whose choices were filled in directly).
            self._no_longer_turned_down(c.provider_id)
        if c.provider_id and kind != DOCTOR:
            prefs.preferred_provider_id, prefs.doctor_name_heard = c.provider_id, ""
        if c.location_id and kind != LOCATION:
            prefs.preferred_location_id, prefs.location_hint = c.location_id, ""

    def _no_longer_turned_down(self, provider_id: str) -> None:
        prefs = self.preferences
        prefs.not_provider_ids = [i for i in prefs.not_provider_ids if i != provider_id]

    def _finish_change(self, kind: str) -> str:
        c = self.choices
        self.preferences.latest = kind
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
        # The chosen doctor is never listed: picking them is the newest thing the caller did.
        turned_down = sorted(catalog.providers[i].name for i in turned_down_ids(catalog, p) - {self.choices.provider_id})
        if turned_down:
            wishes.append("not: " + ", ".join(turned_down))
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
