"""One phone call's working state, and the clinic data every call shares.

Plain Python, no Pipecat. The voice agent (through agent_builder) and the typed
test loop both drive a call through this, so they run the same code (decision 22).

- Clinic       loaded once: catalog, patients, the schedule (with every saved
               booking), where bookings are saved and where call logs go.
- CallSession  one call: the booking card, the options on offer, the stage the
               call is in, what the end stage should say, and the call log.

Stage instructions can contain placeholders, filled at the moment of a stage move
(see PLACEHOLDERS). The call log is one JSON line per stage move and per tool call
(decision 45); the editor's inspector panel will read the same lines.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from clinic import (
    BookingCard, Catalog, Note, OptionsResult, PatientDirectory, Schedule, can_book_visit_type, clinic_now,
    find_options, spoken_time,
)
from clinic.options import BAD_INPUT, PLACE_UNKNOWN

BACKEND_DIR = Path(__file__).resolve().parent.parent
BOOKINGS_FILE = BACKEND_DIR / "bookings.jsonl"   # not committed (.gitignore)
CALL_LOG_DIR = BACKEND_DIR / "call_logs"         # not committed (.gitignore)

# The placeholders stage instructions may contain, and what each is filled with.
PLACEHOLDERS = {
    "today": "today's date and the time at the clinics",
    "just_happened": "one sentence from the code saying why this stage started (e.g. the caller changed the visit)",
    "booking_card": "the booking card: who is calling, what they asked for, what's agreed",
    "specialties": "the names of all our specialties",
    "visit_types": "the visit types of the specialty already picked (if any), each marked bookable or not",
    "options": "the notes and options on offer, from the latest search",
    "outcome": "what the end stage should tell the caller (booked, or handed to staff)",
}
# Anything in braces counts as a placeholder, so a typo ("{Options}", "{booking card}")
# is caught when the agent file loads instead of reaching the AI as raw text.
PLACEHOLDER = re.compile(r"\{([^{}]*)\}")

# Note kinds that are for the AI only (resend a value), never read to the caller.
FOR_THE_AI_ONLY = {BAD_INPUT, PLACE_UNKNOWN}


class BookingsFileError(ValueError):
    """The saved bookings file has a line the code can't use."""


def read_bookings(path: Path, catalog: Catalog) -> list:
    """Every saved booking as (provider_id, start, duration_min), for the Schedule.
    A line that can't be used stops start-up with its line number, rather than being
    skipped: a skipped booking could be offered to someone else."""
    path = Path(path)
    if not path.exists():
        return []
    booked = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        problem = _booking_problem(line, catalog)
        if problem:
            raise BookingsFileError(f"{path.name}, line {number}: can't use this booking ({problem}).")
        record = json.loads(line)
        booked.append((record["provider_id"], datetime.fromisoformat(record["start"]), int(record["duration_min"])))
    return booked


def _booking_problem(line: str, catalog: Catalog) -> str:
    try:
        record = json.loads(line)
    except ValueError:
        return "not a JSON record"
    if not isinstance(record, dict):
        return "not a JSON record"
    missing = [k for k in ("provider_id", "start", "duration_min") if k not in record]
    if missing:
        return f"missing {', '.join(missing)}"
    if record["provider_id"] not in catalog.providers:
        return f"unknown doctor id {record['provider_id']!r}"
    try:
        datetime.fromisoformat(record["start"])
    except (TypeError, ValueError):
        return f"start {record['start']!r} isn't a date and time"
    try:
        int(record["duration_min"])
    except (TypeError, ValueError):
        return f"duration_min {record['duration_min']!r} isn't a number of minutes"
    return ""


class Clinic:
    """The data every call shares. One per running agent."""

    def __init__(self, catalog: Catalog, patients: PatientDirectory, schedule: Schedule,
                 bookings_file: Optional[Path] = None, log_dir: Optional[Path] = None):
        self.catalog = catalog
        self.patients = patients
        self.schedule = schedule
        self.bookings_file = Path(bookings_file) if bookings_file else None  # None: don't save (tests)
        self.log_dir = Path(log_dir) if log_dir else None                    # None: no call log

    @classmethod
    def load(cls, bookings_file: Optional[Path] = BOOKINGS_FILE, log_dir: Optional[Path] = CALL_LOG_DIR) -> "Clinic":
        catalog = Catalog.load()
        booked = read_bookings(bookings_file, catalog) if bookings_file else []
        return cls(catalog, PatientDirectory.load(), Schedule(catalog, booked), bookings_file, log_dir)

    def new_call(self, clock: Callable[[], datetime] = clinic_now) -> "CallSession":
        log_path = None
        if self.log_dir:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            log_path = self.log_dir / f"{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}.jsonl"
        return CallSession(self, clock, log_path)

    def save_booking(self, record: dict) -> None:
        if self.bookings_file:
            with self.bookings_file.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")


class CallSession:
    def __init__(self, clinic: Clinic, clock: Callable[[], datetime] = clinic_now, log_path: Optional[Path] = None):
        self.clinic = clinic
        self.clock = clock              # clinic time; tests pass a fixed clock
        self.card = BookingCard()
        self.stage = ""                 # set by enter_stage
        self.offer: Optional[OptionsResult] = None  # the latest search, shown in {options}
        self.outcome = ""               # what the end stage says; set by confirm_booking or hand_off
        self.listed_specialty: Optional[str] = None  # specialty whose visit types show in {visit_types}
        self.just_happened = "The call has just started."  # set by the tool that moves the call
        self.log_path = log_path

    @property
    def catalog(self) -> Catalog:
        return self.clinic.catalog

    def now(self) -> datetime:
        return self.clock()

    # ---- options -----------------------------------------------------------
    def refresh_options(self, first_note: Optional[Note] = None) -> OptionsResult:
        """Search again with what's on the card, and put the result on offer."""
        c = self.card
        result = find_options(self.catalog, self.clinic.schedule, c.caller, c.choices.visit_type_id,
                              c.preferences, self.now(), first_option_number=c.next_option_number)
        if first_note:
            result.notes.insert(0, first_note)
        c.remember_offer(result.options)
        self.offer = result
        return result

    def visit_types_for(self, specialty: str) -> list:
        """Every visit type in one specialty, marked whether THIS caller can book it, and why not."""
        types = []
        for vt in self.catalog.visit_types_in(specialty):
            b = can_book_visit_type(self.catalog, self.card.caller, vt.id)
            types.append({"id": vt.id, "name": vt.name, "minutes": vt.duration_min,
                          "needs_referral": vt.requires_referral, "open_to_new_patients": vt.new_patients_allowed,
                          "can_book": b.bookable, "why_not": b.reasons})
        return types

    # ---- placeholders ------------------------------------------------------
    def fill(self, text: str) -> str:
        """Fill the placeholders in a stage's instructions. Unknown ones are an error
        (the builder also checks them when the agent file loads)."""
        def value(m: re.Match) -> str:
            name = m.group(1)
            if name not in PLACEHOLDERS:
                raise ValueError(f"Unknown placeholder {{{name}}}; known: {', '.join(PLACEHOLDERS)}.")
            return getattr(self, f"_fill_{name}")()
        return PLACEHOLDER.sub(value, text)

    def _fill_today(self) -> str:
        now = self.now()
        clock = spoken_time(now).rsplit(" at ", 1)[1]  # "9 AM", said the same way as every time we offer
        return f"{now:%A} {now.day} {now:%B %Y} at {clock} (clinic time, San Francisco)"

    def _fill_just_happened(self) -> str:
        return self.just_happened

    def _fill_booking_card(self) -> str:
        return self.card.summary(self.catalog)

    def _fill_specialties(self) -> str:
        return ", ".join(self.catalog.specialties())

    def _fill_visit_types(self) -> str:
        if not self.listed_specialty:
            return "Not looked up yet: call list_visit_types with the specialty that fits."
        lines = [f"{self.listed_specialty} visit types for this caller (send the id to choose_visit_type):"]
        for t in self.visit_types_for(self.listed_specialty):
            if t["can_book"]:
                lines.append(f"- {t['id']}: {t['name']} ({t['minutes']} min): can book")
            else:
                lines.append(f"- {t['id']}: {t['name']}: can't book ({' '.join(t['why_not'])})")
        lines.append("If none of these fits what the caller wants, call list_visit_types for another specialty.")
        return "\n".join(lines)

    def _fill_options(self) -> str:
        r = self.offer
        if r is None:
            raise ValueError("{options} is used before any search: a stage that shows options must be "
                             "reached through a tool that searches.")
        lines = []
        for_ai = [n.say for n in r.notes if n.kind in FOR_THE_AI_ONLY]
        for_caller = [n.say for n in r.notes if n.kind not in FOR_THE_AI_ONLY]
        if for_ai:
            lines.append("Fix first (don't read this to the caller; ask them if you need to, then call "
                         "change_choice with corrected values):")
            lines += [f"- {s}" for s in for_ai]
        if for_caller:
            lines.append("Tell the caller first:")
            lines += [f"- {s}" for s in for_caller]
        if not r.bookable:
            lines.append("This visit can't be booked for this caller, so there are no options.")
        elif r.options:
            lines.append("Options on offer (offer only these; pass the option number to choose_option):")
            lines += [f"- Option {o.option_id}: {o.spoken}" for o in r.options]
        else:
            lines.append("No options are on offer with these wishes.")
        return "\n".join(lines)

    def _fill_outcome(self) -> str:
        if not self.outcome:
            raise ValueError("{outcome} is used before the call has an outcome (confirm_booking or hand_off).")
        return self.outcome

    # ---- call log ----------------------------------------------------------
    def enter_stage(self, stage: str, instructions: list) -> None:
        self.stage = stage
        self.log({"event": "stage", "stage": stage, "instructions": instructions})

    def log(self, entry: dict) -> None:
        if self.log_path is None:
            return
        line = {"at": datetime.now().isoformat(timespec="seconds"), **entry, "card": self.card.to_dict()}
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(line) + "\n")

