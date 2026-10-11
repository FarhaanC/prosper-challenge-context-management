"""Pass or fail, checked by code against what was actually saved (decision 20).

The AI's own account of the call is never used. What counts:
- the saved bookings (ours: the run's bookings file; naive: what book_appointment saved);
- whether hand_off was called;
- every saved booking is re-checked with our final rule check, for the REAL caller of the
  scenario (not whoever the agent thought it was talking to), on a fresh schedule. One that
  fails is a "bad booking", whatever the version;
- a promise that staff will call back or follow up, with no hand_off, is a fail (decision 87;
  the 22:42 call). These words are only flagged, never acted on.
"""

from __future__ import annotations

import re
from datetime import datetime

from clinic import Caller, Catalog, PatientDirectory, Schedule, check_booking

from .scenarios import BOOKED, HANDED_OFF, NOT_BOOKED, Scenario

# "A member of staff will call you back", "someone will follow up", "we'll get back to you"...
# Not "a follow-up visit", which is a visit type.
STAFF_PROMISE = re.compile(
    r"call you back|get back to you|follow up with you|will follow up|be in touch|reach out to you"
    r"|(staff|someone|team|colleague)\s+(member\s+)?(will|can|is going to|to)\s+(call|contact|reach|get in touch|follow)",
    re.IGNORECASE)


def real_caller(scenario: Scenario, patients: PatientDirectory) -> Caller:
    if scenario.patient_id:
        r = next(r for r in patients.records if r["id"] == scenario.patient_id)
        return Caller(name=r["name"], patient_id=r["id"], is_new_patient=False,
                      referrals_on_file=list(r.get("referrals_on_file", [])))
    return Caller(name=scenario.new_patient_name)


def booking_problems(booking: dict, caller: Caller, catalog: Catalog, now: datetime) -> list:
    """Our final rule check on one saved booking, on a schedule with nothing else booked."""
    try:
        start = datetime.fromisoformat(str(booking.get("start")))
    except ValueError:
        start = None
    return check_booking(catalog, Schedule(catalog), caller, booking.get("visit_type_id"),
                         booking.get("provider_id"), booking.get("location_id"), start, now)


def score(scenario: Scenario, run: dict, catalog: Catalog, patients: PatientDirectory, now: datetime) -> dict:
    outcome = run["outcome"]
    bookings = outcome["bookings"]
    caller = real_caller(scenario, patients)
    reasons = []

    if run["ended_by"] == "turn_limit":
        reasons.append("The call didn't finish within the turn limit.")
    for turn in run["turns"]:
        for problem in turn.get("agent", {}).get("problems", []):
            if "failed in the code" in problem:
                reasons.append(problem)

    bad = []
    for b in bookings:
        problems = booking_problems(b, caller, catalog, now)
        if problems:
            bad.append({"booking": b, "problems": problems})
    for b in bad:
        reasons.append("A booking breaks the rules: " + " ".join(b["problems"]))

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
                reasons.append(f"Booked {b.get('provider_id')} at {b.get('location_id')}, which isn't one of the "
                               "valid doctor-place pairs.")
    elif expected.outcome == NOT_BOOKED:
        if bookings:
            reasons.append(f"Expected no booking, found {len(bookings)}.")
    elif expected.outcome == HANDED_OFF:
        if not outcome["hand_off_called"]:
            reasons.append("Expected a hand-off to staff; hand_off was never called.")
        if bookings:
            reasons.append(f"Expected no booking, found {len(bookings)}.")

    promises = [] if outcome["hand_off_called"] else _staff_promises(run, outcome)
    if promises:
        reasons.append(f"Promised staff would follow up without calling hand_off: \"{promises[0]}\"")

    if scenario.check_in_after_read_back:
        after = [t for t in run["turns"] if t.get("after_check_in")]
        if not after:
            reasons.append("The read-back (and so the check-in) was never reached.")
        elif any(x["tool"] == "confirm_booking" for x in after[0]["agent"]["tools"]):
            reasons.append("A 'Yes' to 'Are you still there?' was taken as agreeing to the booking.")

    return {"passed": not reasons, "reasons": reasons, "bad_bookings": len(bad), "staff_promise": bool(promises)}


def _staff_promises(run: dict, outcome: dict) -> list:
    """Agent lines promising a staff follow-up. A name whose spelling couldn't be confirmed is
    checked by staff (decision 78), so that one line is a real promise, not a false one."""
    found = []
    for turn in run["turns"]:
        for line in turn.get("agent", {}).get("said", []):
            if not STAFF_PROMISE.search(line):
                continue
            if outcome.get("name_confirmed") is False and "spell" in line.lower():
                continue
            found.append(line)
    return found
