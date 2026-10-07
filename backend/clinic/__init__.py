"""Clinic catalog, booking rules and booking card, in plain Python.

Nothing here knows about Pipecat or voice. The voice agent and the typed test
harness both call this same code, so what we test is what runs.

The rule for what comes in from the AI (plan decision 23, as settled in review
rounds 4-7): names (doctors, places, languages) are matched forgivingly against
our own records, because the AI doesn't know them. Two fixed word lists are read:
"no preference" words (treated as empty) and words no name has, like "not" or
"another" (refused, with a note saying how to send the value). Everything else
is a plain instruction (ids, yes/no, a weekday or a date, "morning" or
"afternoon"), and anything that isn't one of those is refused, never guessed.

    catalog.py   the catalog, checked at load; search (specialties, doctor names, places)
    fuzzy.py     forgiving name matching that reports how close a match is
    patients.py  fake returning patients; the step-by-step identity check
    slots.py     fake, repeatable open times, in San Francisco clinic time
    rules.py     the 6 booking rules, each written once, with plain-English reasons
    options.py   up to 3 valid doctor + location + time options, with true notes
    card.py      the booking card, and what changing one choice clears
    facts.py     small factual answers (answer_question)
"""

from .card import BOOKING, END, IDENTIFY, VISIT_TYPE, BookingCard, Choices, Preferences, turned_down_ids
from .catalog import Catalog, CatalogError, PlaceMatch, ProviderMatch
from .facts import answer_question
from .options import Note, Option, OptionsResult, find_options
from .patients import Caller, IdentityCheck, IdentityStep, LookupResult, PatientDirectory
from .rules import Bookability, alternatives_for, can_book_visit_type, check_booking
from .slots import Schedule, SlotTaken, clinic_now, spoken_time

__all__ = [
    "BOOKING", "END", "IDENTIFY", "VISIT_TYPE", "BookingCard", "Choices", "Preferences", "turned_down_ids",
    "Catalog", "CatalogError", "PlaceMatch", "ProviderMatch", "answer_question",
    "Note", "Option", "OptionsResult", "find_options",
    "Caller", "IdentityCheck", "IdentityStep", "LookupResult", "PatientDirectory",
    "Bookability", "alternatives_for", "can_book_visit_type", "check_booking",
    "Schedule", "SlotTaken", "clinic_now", "spoken_time",
]
