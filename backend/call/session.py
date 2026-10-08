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
    BookingCard, Catalog, Note, OptionsResult, PatientDirectory, Schedule,
    clinic_now, find_options, spoken_time,
)
from clinic.options import BAD_INPUT

BACKEND_DIR = Path(__file__).resolve().parent.parent
BOOKINGS_FILE = BACKEND_DIR / "bookings.jsonl"   # not committed (.gitignore)
CALL_LOG_DIR = BACKEND_DIR / "call_logs"         # not committed (.gitignore)

# The placeholders stage instructions may contain, and what each is filled with.
PLACEHOLDERS = {
    "today": "today's date and the time at the clinics",
    "booking_card": "the booking card: who is calling, what they asked for, what's agreed",
    "specialties": "the names of all our specialties",
    "options": "the notes and options on offer, from the latest search",
    "outcome": "what the end stage should tell the caller (booked, or handed to staff)",
}
PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")

# Note kinds that are for the AI only (resend a value), never read to the caller.
FOR_THE_AI_ONLY = {BAD_INPUT}


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
        try:
            record = json.loads(line)
            provider_id, start, duration = record["provider_id"], record["start"], record["duration_min"]
            if provider_id not in catalog.providers:
                raise ValueError(f"unknown doctor id {provider_id!r}")
            booked.append((provider_id, datetime.fromisoformat(start), int(duration)))
        except (ValueError, KeyError, TypeError) as e:
            raise BookingsFileError(f"{path.name}, line {number}: can't use this booking ({e}).") from e
    return booked


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
        return f"{spoken_time(now)} (clinic time, San Francisco)"

    def _fill_booking_card(self) -> str:
        return self.card.summary(self.catalog)

    def _fill_specialties(self) -> str:
        return ", ".join(self.catalog.specialties())

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

