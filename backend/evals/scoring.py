"""Pass or fail, checked by code against what the call ended with (decision 20).

The AI's own account of the call is never used. What counts:
- the booking card's status and booking (ours), or what book_appointment and hand_off did (naive);
- every booking is re-checked with our final rule check, for the REAL caller of the scenario
  (not whoever the agent thought it was talking to), on a fresh schedule. One that fails is a
  "bad booking", whatever the version;
- the booking is under the caller's own name (a returning patient's record, or the name a new
  patient gave);
- a promise that staff will call or follow up, when the call wasn't handed to staff, fails the
  run (decision 87; the 22:42 call). The sentence is quoted in the results so a person can check it;
- a turn stuck in a loop, a tool failing in our code, or a call that never finished fails the run.
"""

from __future__ import annotations

import re
from datetime import datetime

from clinic import Caller, Catalog, PatientDirectory, Schedule, check_booking

from .agents import MAX_PASSES_PER_TURN
from .scenarios import BOOKED, HANDED_OFF, NOT_BOOKED, Scenario

# One sentence in which the clinic's side promises to contact the caller later:
# "A member of staff will call you back", "Someone from the clinic will contact you", "We'll get back to you",
# "I'll have someone call you", "You'll get a call from one of our staff".
# Not a question or an offer ("Would you like someone to call you back?", "...if you want"), and not about
# the caller's own doctor ("Please reach out to your doctor", "Your doctor will follow up with you").
_CONTACT = r"(?:call|contact|ring|phone|reach out|get in touch|follow up|get back|be in touch)"
STAFF_PROMISE = re.compile(
    r"^(?!.*\?\s*$)(?!.*\b(?:if you|would you like|do you want)\b).*\b(?:"
    r"(?:someone|somebody|staff|colleague|nurse|team|office|front desk|we|they)(?:\s+[\w']+){0,4}?"
    r"\s+(?:will|is going to|are going to)\s+(?:\w+\s+)?" + _CONTACT +
    r"|(?:we|they)'ll\s+(?:\w+\s+)?" + _CONTACT +
    r"|i'll\s+(?:have|ask|get)\s+(?:someone|somebody|a colleague|a nurse|staff|the office"
    r"|a member of (?:our |the )?(?:staff|team)|(?:our|the) (?:\w+ )?team)"
    r"|you'll\s+(?:get|receive)\s+a\s+(?:phone\s+)?call"
    r")",
    re.IGNORECASE)
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def real_caller(scenario: Scenario, patients: PatientDirectory) -> Caller:
    if scenario.patient_id:
        r = next(r for r in patients.records if r["id"] == scenario.patient_id)
        return Caller(name=r["name"], patient_id=r["id"], is_new_patient=False,
                      referrals_on_file=list(r.get("referrals_on_file", [])))
    return Caller(name=scenario.new_patient_name)


def booking_problems(booking: dict, caller: Caller, catalog: Catalog, now: datetime) -> list:
    """Our final rule check on one booking, on a schedule with nothing else booked."""
    try:
        start = datetime.fromisoformat(str(booking.get("start")))
    except ValueError:
        start = None
    return check_booking(catalog, Schedule(catalog), caller, booking.get("visit_type_id"),
                         booking.get("provider_id"), booking.get("location_id"), start, now)


def _agent_turns(run: dict) -> list:
    """Every agent turn that has one (a caller who hangs up with words gets no answer)."""
    return [t["agent"] for t in run["turns"] if t.get("agent")]


def score(scenario: Scenario, run: dict, catalog: Catalog, patients: PatientDirectory, now: datetime) -> dict:
    outcome = run["outcome"]
    bookings = outcome["bookings"]
    caller = real_caller(scenario, patients)
    reasons = []

    if run["ended_by"] == "turn_limit":
        reasons.append("The call didn't finish within the turn limit.")
    for turn in _agent_turns(run):
        for problem in turn.get("problems", []):
            if "failed in the code" in problem or f"More than {MAX_PASSES_PER_TURN} AI passes" in problem:
                reasons.append(problem)

    bad = 0
    for b in bookings:
        problems = booking_problems(b, caller, catalog, now)
        if problems:
            bad += 1
            reasons.append("A booking breaks the rules: " + " ".join(problems))
        booked_for = str(b.get("caller") or b.get("patient_name") or "")
        if " ".join(booked_for.split()).casefold() != caller.name.casefold():
            reasons.append(f"Booked under the name \"{booked_for}\", not \"{caller.name}\".")

    expected = scenario.expected
    if expected.outcome == BOOKED:
        if len(bookings) != 1:
            reasons.append(f"Expected one booking, found {len(bookings)}.")
        else:
            b = bookings[0]
            if expected.visit_types and b.get("visit_type_id") not in expected.visit_types:
                reasons.append(f"Booked visit type {b.get('visit_type_id')}, expected one of "
                               f"{', '.join(sorted(expected.visit_types))}.")
            if expected.providers and b.get("provider_id") not in expected.providers:
                reasons.append(f"Booked doctor {b.get('provider_id')}, expected one of "
                               f"{', '.join(sorted(expected.providers))}.")
            if expected.pairs and (b.get("provider_id"), b.get("location_id")) not in expected.pairs:
                reasons.append(f"Booked {b.get('provider_id')} at {b.get('location_id')}, expected "
                               + " or ".join(f"{p} at {loc}" for p, loc in sorted(expected.pairs)) + ".")
    elif expected.outcome == NOT_BOOKED:
        if bookings:
            reasons.append(f"Expected no booking, found {len(bookings)}.")
    elif expected.outcome == HANDED_OFF:
        if outcome["status"] != "handed_off":
            reasons.append(f"Expected the call to be handed to staff; it ended '{outcome['status']}'.")
        if bookings:
            reasons.append(f"Expected no booking, found {len(bookings)}.")

    promises = [] if outcome["status"] == "handed_off" else staff_promises(run, outcome)
    if promises:
        reasons.append(f"Promised staff would follow up, but the call wasn't handed to staff: \"{promises[0]}\"")

    if scenario.check_in_after_read_back:
        after = [t for t in run["turns"] if t.get("after_check_in")]
        if not after:
            reasons.append("The read-back (and so the check-in) was never reached.")
        elif any(x["tool"] == "confirm_booking" for x in (after[0].get("agent") or {}).get("tools", [])):
            reasons.append("A 'Yes' to 'Are you still there?' was taken as agreeing to the booking.")

    return {"passed": not reasons, "reasons": reasons, "bad_bookings": bad, "staff_promise": bool(promises)}


def staff_promises(run: dict, outcome: dict) -> list:
    """Sentences the agent said promising a staff follow-up. A new patient's name whose spelling couldn't be
    confirmed is checked by staff (decision 78), so a sentence about the spelling is a real promise."""
    found = []
    for turn in _agent_turns(run):
        for line in turn.get("said", []):
            for sentence in _SENTENCE_END.split(line.strip()):
                if not STAFF_PROMISE.search(sentence):
                    continue
                if outcome.get("name_confirmed") is False and "spell" in sentence.lower():
                    continue
                found.append(sentence)
    return found
