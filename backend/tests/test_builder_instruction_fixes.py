"""Builder tests for decisions 82 and 83: two instruction fixes from Farhaan's 22:50 call (Sun 11).

82: the agent said "Thank you, Perhan" (a mishearing) before the name was spelled.
83: the caller asked for "around 11:00 a.m."; the agent said "Let me check ... around eleven"
    and offered 9:00 and 8:30 without saying it can only search mornings or afternoons.
"""

import json

AGENT_FILE = "clinic_agent.json"


def instructions(stage: str) -> str:
    agent = json.load(open(AGENT_FILE, encoding="utf-8"))
    return next(n for n in agent["nodes"] if n["name"] == stage)["task_messages"][0]["content"]


def test_the_name_is_not_said_back_before_it_is_saved():
    identify = instructions("identify")
    assert "Don't say their name back to them yet, not even to thank them" in identify
    assert identify.index("not even to thank them") < identify.index("confirm the spelling of each name")
    assert "by first name" in instructions("visit_type"), "the thank-you by name happens once it's saved"


def test_an_exact_time_is_searched_as_a_part_of_the_day_and_the_caller_is_told():
    booking = instructions("booking")
    rule = booking.split("Searches go by part of the day", 1)[1]
    assert "not by exact time" in rule and '"around 11"' in rule
    assert "tell them you're looking at mornings (or afternoons)" in rule
    assert "offer the closest times found" in rule
