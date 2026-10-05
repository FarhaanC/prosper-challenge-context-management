"""Clinic catalog, booking rules and booking card, in plain Python.

Nothing here knows about Pipecat or voice. The voice agent and the typed test
harness both call this same code, so what we test is what runs.

    catalog.py   the catalog and search (specialties, doctor names, places)
    patients.py  fake returning patients; the caller being checked
    slots.py     fake, repeatable open times
    rules.py     the booking rules, with plain-English reasons
    options.py   up to 3 valid doctor + location + time options, with notes
    card.py      the booking card, and what changing one choice clears
    facts.py     small factual answers (answer_question)
"""

from .card import BOOKING, END, IDENTIFY, VISIT_TYPE, BookingCard, Choices, Preferences
from .catalog import Catalog
from .facts import answer_question
from .options import Option, OptionsResult, find_options
from .patients import Caller, PatientDirectory
from .rules import Bookability, can_book_visit_type, check_booking
from .slots import Schedule, spoken_time

__all__ = [
    "BOOKING", "END", "IDENTIFY", "VISIT_TYPE", "BookingCard", "Choices", "Preferences",
    "Catalog", "answer_question", "Option", "OptionsResult", "find_options",
    "Caller", "PatientDirectory", "Bookability", "can_book_visit_type", "check_booking",
    "Schedule", "spoken_time",
]
