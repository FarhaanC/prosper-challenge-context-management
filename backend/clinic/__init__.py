"""Clinic catalog, booking rules and booking card, in plain Python.

Nothing here knows about Pipecat or voice. The voice agent and the typed test
harness both call this same code, so what we test is what runs.

    catalog.py   the catalog, checked at load; search (specialties, doctor names, places)
    fuzzy.py     forgiving name matching that reports how close a match is
    patients.py  fake returning patients; identity by name + date of birth
    slots.py     fake, repeatable open times, in San Francisco clinic time
    rules.py     the 6 booking rules, each written once, with plain-English reasons
    options.py   up to 3 valid doctor + location + time options, with true notes
    card.py      the booking card, and what changing one choice clears
    facts.py     small factual answers (answer_question)
"""

from .card import BOOKING, END, IDENTIFY, VISIT_TYPE, BookingCard, Choices, Preferences
from .catalog import Catalog, CatalogError, PlaceMatch, ProviderMatch
from .facts import answer_question
from .options import Note, Option, OptionsResult, find_options
from .patients import Caller, LookupResult, PatientDirectory
from .rules import Bookability, alternatives_for, can_book_visit_type, check_booking
from .slots import Schedule, SlotTaken, clinic_now, spoken_time

__all__ = [
    "BOOKING", "END", "IDENTIFY", "VISIT_TYPE", "BookingCard", "Choices", "Preferences",
    "Catalog", "CatalogError", "PlaceMatch", "ProviderMatch", "answer_question",
    "Note", "Option", "OptionsResult", "find_options",
    "Caller", "LookupResult", "PatientDirectory",
    "Bookability", "alternatives_for", "can_book_visit_type", "check_booking",
    "Schedule", "SlotTaken", "clinic_now", "spoken_time",
]
