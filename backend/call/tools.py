"""The tools the AI calls during a phone call, and the tool registry.

Plain Python, no Pipecat (decision 22). Each tool takes the call's session and the
values the AI sent, calls the clinic module, and returns an Outcome: what the AI
is told, and the stage to move to (or None to stay). Moves are decided here, by
code, never by the AI.

What the AI sends follows the rule in clinic/__init__.py: names (doctors, places,
languages) as the caller said them; everything else a plain value (ids, yes/no,
one weekday or date per day entry, "morning" or "afternoon"). A value of the
wrong kind is refused with a message saying how to send it; nothing is guessed.
Refusals and "not found" replies have "ok": false, and the caller never hears the
message itself: the AI acts on it.

The registry (TOOLS) holds each tool's description and fields, which is what the
AI reads, and the stages it can move to, which the builder checks against the
agent file and the editor will draw as dashed arrows.

| tool               | where           | moves to                                   |
| start_booking      | identify        | visit_type (found or new), end (staff)     |
| list_visit_types   | visit_type      | stays                                      |
| choose_visit_type  | visit_type      | booking (accepted), stays (refused)        |
| choose_option      | booking         | stays (gives the read-back)                |
| confirm_booking    | booking         | end (saved), booking (time gone: new options) |
| turn_down_doctors  | booking         | booking (new options)                      |
| change_choice      | every stage     | booking (new options), visit_type, stays   |
| answer_question    | every stage     | stays                                      |
| hand_off           | every stage     | end                                        |
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional

from clinic import (
    BOOKING, END, IDENTIFY, VISIT_TYPE, Caller, Note, alternatives_for, answer_question,
    can_book_visit_type, check_booking,
)
from clinic.card import CHANGEABLE, TIMES_OF_DAY
from clinic.fuzzy import looks_like_a_sentence, means_no_preference, name_tokens, tidy
from clinic.options import check_time_wishes
from clinic.slots import SlotTaken

from .session import CallSession


@dataclass
class Outcome:
    result: dict                       # what the AI is told
    next_stage: Optional[str] = None   # None: stay in this stage


class Refused(ValueError):
    """A value the tool can't use. The AI is told why and how to send it."""


def _refused(message: str) -> Outcome:
    return Outcome({"ok": False, "error": message})


# ---------------------------------------------------------------- reading values
def _text(args: dict, key: str) -> str:
    value = args.get(key)
    if value is None:
        return ""
    if not isinstance(value, str):
        raise Refused(f"{key} must be text.")
    return tidy(value)


def _flag(args: dict, key: str) -> Optional[bool]:
    """True/False, or None if not sent."""
    value = args.get(key)
    if value is None or isinstance(value, bool):
        return value
    raise Refused(f"{key} must be true or false.")


def _days(args: dict) -> Optional[list]:
    """A list of day entries, or None if not sent."""
    value = args.get("days")
    if value is None:
        return None
    if not (isinstance(value, list) and all(isinstance(d, str) for d in value)):
        raise Refused("days must be a list, one day per entry, e.g. [\"Thursday\", \"Friday\"].")
    return [tidy(d) for d in value]


def _a_name(value: str, kind: str, extra: str = "") -> str:
    """A doctor or place value must be a name, not a sentence ("not Dr. Chen")."""
    if value and not means_no_preference(value) and looks_like_a_sentence(value):
        raise Refused(f"'{value}' isn't a {kind} name. Pass just the name.{extra}")
    return value


def _check_times(session: CallSession, days: Optional[list], time_of_day: Optional[str]) -> None:
    """Day and time values are checked before anything is recorded, so a bad one
    changes nothing. A value not sent (None) is checked as it stands on the card."""
    prefs = session.card.preferences
    problems = check_time_wishes(prefs.days if days is None else days,
                                 prefs.time_of_day if time_of_day is None else time_of_day, session.now()).problems
    if problems:
        raise Refused(" ".join(problems))


# ---------------------------------------------------------------- wishes said early
TURN_DOWN_HINT = " For 'someone else' or 'not Dr. X', use turn_down_doctors once options are on offer."

WISH_FIELDS = {
    "doctor_name": {"type": "string", "description": (
        "A doctor the caller asked for, as they said it (\"Dr. Garcia\"). Only a name." + TURN_DOWN_HINT)},
    "place": {"type": "string", "description": (
        "A place the caller mentioned: one of our locations, a neighbourhood, a landmark or a street with its "
        "street word (\"Midtown\", \"Union Square\", \"Geary Street\"). Only the name; put closeness in near.")},
    "near": {"type": "boolean", "description": (
        "With place: true if the caller wants somewhere close to it (\"near Union Square\"), false if they mean "
        "that place itself (\"the Midtown one\").")},
    "days": {"type": "array", "items": {"type": "string"}, "description": (
        "Days that suit the caller, ONE day per entry: a weekday name (\"Thursday\"), \"today\", \"tomorrow\", "
        "or a date YYYY-MM-DD. \"Thursday or Friday\" is [\"Thursday\", \"Friday\"]. Never put a time of day here.")},
    "time_of_day": {"type": "string", "enum": list(TIMES_OF_DAY), "description": (
        "\"morning\" (before noon) or \"afternoon\" (noon or later). Leave it out if they didn't say.")},
    "soonest": {"type": "boolean", "description": "true if the caller wants the earliest time possible."},
    "language": {"type": "string", "description": "One language the doctor should speak (\"Spanish\")."},
}


def _read_wishes(session: CallSession, args: dict) -> Callable[[], None]:
    """Check every wish value, then return a function that records them on the card.
    Checking everything first means a refused value records nothing."""
    doctor = _a_name(_text(args, "doctor_name"), "doctor", TURN_DOWN_HINT)
    place = _a_name(_text(args, "place"), "place", " Put closeness in near.")
    near = _flag(args, "near")
    if near and not place:
        raise Refused("near goes with a place. Pass the place too.")
    days = _days(args)
    time_of_day = _text(args, "time_of_day").lower()
    _check_times(session, days, time_of_day or None)
    soonest = _flag(args, "soonest")
    language = _text(args, "language")

    def record() -> None:
        p = session.card.preferences
        if doctor and not means_no_preference(doctor):
            p.doctor_name_heard, p.preferred_provider_id = doctor, ""
        if place and not means_no_preference(place):
            p.location_hint, p.near, p.preferred_location_id = place, bool(near), ""
        if days:
            p.days = [d for d in days if d and not means_no_preference(d)]
        if time_of_day and not means_no_preference(time_of_day):
            p.time_of_day = time_of_day
        if soonest is not None:
            p.soonest = soonest
        if language and not means_no_preference(language):
            p.language = language
    return record


# ---------------------------------------------------------------- the tools
def start_booking(session: CallSession, args: dict) -> Outcome:
    card = session.card
    if card.caller is not None:
        raise Refused("The caller is already identified.")
    name = _text(args, "full_name")
    returning = _flag(args, "returning")
    if returning is None:
        raise Refused("Pass returning: true if they've been a patient with us before, false if not.")
    record_wishes = _read_wishes(session, args)
    visit = _text(args, "visit_description")

    found_say = ""
    if returning:
        step = card.identity.attempt(session.clinic.patients, name, _text(args, "date_of_birth"),
                                     _text(args, "spelled_last_name"))
        if step.status == "hand_to_staff":
            return _hand_to_staff(session, step.say)
        if step.status != "found":
            return Outcome({"ok": False, "status": step.status, "say": step.say})
        caller, found_say = step.caller, step.say
    else:
        if len(name_tokens(name)) < 2:
            raise Refused("Ask for the caller's full name (first and last) and pass it in full_name.")
        caller = Caller(name=name)

    card.caller = caller
    record_wishes()
    if visit:
        card.preferences.visit_description = visit
    return Outcome({"ok": True, "say": found_say}, VISIT_TYPE)


def list_visit_types(session: CallSession, args: dict) -> Outcome:
    catalog, caller = session.catalog, session.card.caller
    said = _text(args, "specialty")
    specialty = catalog.match_specialty(said)
    if specialty is None:
        raise Refused(f"'{said}' isn't one of our specialties. Use one of: {', '.join(catalog.specialties())}.")
    types = []
    for vt in catalog.visit_types_in(specialty):
        b = can_book_visit_type(catalog, caller, vt.id)
        types.append({"id": vt.id, "name": vt.name, "minutes": vt.duration_min,
                      "needs_referral": vt.requires_referral, "open_to_new_patients": vt.new_patients_allowed,
                      "can_book": b.bookable, "why_not": b.reasons})
    return Outcome({"ok": True, "specialty": specialty, "visit_types": types})


def choose_visit_type(session: CallSession, args: dict) -> Outcome:
    catalog, card = session.catalog, session.card
    vt_id = _text(args, "visit_type_id")
    if vt_id not in catalog.visit_types:
        raise Refused(f"'{vt_id}' isn't a visit type id. Use an id from list_visit_types.")
    record_wishes = _read_wishes(session, args)
    record_wishes()
    b = can_book_visit_type(catalog, card.caller, vt_id)
    if not b.bookable:
        alternatives = [{"id": vt.id, "name": vt.name, "specialty": vt.specialty}
                        for vt in alternatives_for(catalog, card.caller, vt_id)]
        return Outcome({"ok": False, "reasons": b.reasons, "alternatives": alternatives,
                        "careful": "Never promise that an alternative visit will lead to a referral."})
    vt = catalog.visit_types[vt_id]
    card.choices.specialty, card.choices.visit_type_id = vt.specialty, vt.id
    if not card.preferences.visit_description:
        card.preferences.visit_description = vt.name
    session.refresh_options()
    return Outcome({"ok": True}, BOOKING)


def choose_option(session: CallSession, args: dict) -> Outcome:
    card = session.card
    option_id = args.get("option_id")
    if isinstance(option_id, int) and not isinstance(option_id, bool):
        option_id = str(option_id)  # the AI sometimes sends the number as a number
    if not isinstance(option_id, str):
        raise Refused("option_id must be the option number from your instructions.")
    try:
        card.choose_option(option_id)
    except ValueError as e:
        raise Refused(str(e)) from e
    return Outcome({"ok": True, "read_back": card.read_back(session.catalog),
                    "next": "Say the read_back to the caller word for word and ask if they'd like to book it. "
                            "Call confirm_booking only after they say yes."})


def confirm_booking(session: CallSession, args: dict) -> Outcome:
    catalog, card, clinic = session.catalog, session.card, session.clinic
    c = card.choices
    if card.status != "in_progress":
        raise Refused("This call's booking is already finished; nothing more to confirm.")
    if not (c.provider_id and c.slot):
        raise Refused("Nothing is chosen yet. Call choose_option first, read back, and ask the caller.")
    now = session.now()
    problems = check_booking(catalog, clinic.schedule, card.caller, c.visit_type_id, c.provider_id,
                             c.location_id, c.slot, now)
    vt = catalog.visit_types[c.visit_type_id]
    if not problems:
        try:
            clinic.schedule.book(c.provider_id, c.slot, vt.duration_min)
        except SlotTaken:
            problems = ["That time is no longer available."]
    if problems:
        # Back to choosing: the doctor and place become wishes, and a fresh search runs.
        card.change_choice("time")
        session.refresh_options(Note("booking_failed", " ".join(problems) + " Here are other options."))
        return Outcome({"ok": False, "problems": problems}, BOOKING)

    read_back = card.read_back(catalog)
    caller, p, loc = card.caller, catalog.providers[c.provider_id], catalog.locations[c.location_id]
    clinic.save_booking({
        "booked_at": datetime.now().isoformat(timespec="seconds"),
        "caller": caller.name, "patient_id": caller.patient_id, "new_patient": caller.is_new_patient,
        "visit_type_id": vt.id, "visit_type": vt.name, "provider_id": p.id, "provider": p.name,
        "location_id": loc.id, "location": loc.name, "start": c.slot.isoformat(),
        "duration_min": vt.duration_min, "read_back": read_back,
    })
    card.status = "booked"
    session.outcome = (f"The booking is saved: {read_back} Confirm it to the caller in one sentence, "
                       "thank them and say goodbye.")
    return Outcome({"ok": True, "booked": read_back}, END)


def turn_down_doctors(session: CallSession, args: dict) -> Outcome:
    catalog, card = session.catalog, session.card
    name = _a_name(_text(args, "doctor_name"), "doctor", " For 'someone else', use on_offer or current.")
    doctor_id = _text(args, "doctor_id")
    on_offer, current = bool(_flag(args, "on_offer")), bool(_flag(args, "current"))
    ids = [doctor_id] if doctor_id else []
    if name:
        matches = catalog.match_providers(name)
        if not matches:
            raise Refused(f"No doctor matches '{name}'.")
        if len(matches) > 1:
            return Outcome({"ok": False, "which_one": [
                {"doctor_id": m.provider.id, "name": m.provider.name, "specialty": m.provider.specialty,
                 "locations": [catalog.locations[i].name for i in m.provider.location_ids]} for m in matches],
                "next": "Several doctors match. Work out which one the caller means (ask if unsure), then call "
                        "again with that doctor_id."})
        ids.append(matches[0].provider.id)
    try:
        stage = card.turn_down_doctors(catalog, ids, on_offer=on_offer, current=current)
    except ValueError as e:
        raise Refused(str(e)) from e
    session.refresh_options()
    return Outcome({"ok": True}, stage)


def change_choice(session: CallSession, args: dict) -> Outcome:
    card = session.card
    if card.status != "in_progress":
        raise Refused("The call is finished (booked or handed to staff); nothing can be changed now.")
    what = _text(args, "what").lower()
    if what not in CHANGEABLE:
        raise Refused(f"what must be one of: {', '.join(CHANGEABLE)}.")
    new_value = _text(args, "new_value")
    if what == "doctor":
        _a_name(new_value, "doctor", TURN_DOWN_HINT)
    if what == "location":
        _a_name(new_value, "place", " Put closeness in near.")
    near = _flag(args, "near")
    days = _days(args)
    time_of_day = args.get("time_of_day")
    if time_of_day is not None and not isinstance(time_of_day, str):
        raise Refused("time_of_day must be \"morning\", \"afternoon\" or \"\" (to clear it).")
    if what == "time":
        if new_value:
            raise Refused("For a time change, pass days and/or time_of_day, not new_value.")
        if days is None and time_of_day is None:
            raise Refused("For a time change, pass days and/or time_of_day.")
        _check_times(session, days, None if time_of_day is None else time_of_day.strip().lower())
    try:
        target = card.change_choice(what, new_value, days=days, time_of_day=time_of_day, near=bool(near))
    except ValueError as e:
        raise Refused(str(e)) from e

    if session.stage == IDENTIFY or (target == VISIT_TYPE and session.stage == VISIT_TYPE):
        return Outcome({"ok": True, "noted": "Recorded. Carry on with this stage."})
    if target == BOOKING:
        session.refresh_options()
    return Outcome({"ok": True}, target)


def answer_question_tool(session: CallSession, args: dict) -> Outcome:
    return Outcome(answer_question(session.catalog, args.get("about"), args.get("name")))


HAND_OFF_REASONS = {
    "reschedule": "The caller wants to reschedule an appointment, which a member of staff handles.",
    "cancel": "The caller wants to cancel an appointment, which a member of staff handles.",
    "speak_to_staff": "The caller asked to speak to a person.",
}


def hand_off(session: CallSession, args: dict) -> Outcome:
    reason = _text(args, "reason")
    if reason not in HAND_OFF_REASONS:
        raise Refused(f"reason must be one of: {', '.join(HAND_OFF_REASONS)}.")
    return _hand_to_staff(session, HAND_OFF_REASONS[reason])


def _hand_to_staff(session: CallSession, why: str) -> Outcome:
    card = session.card
    if card.status == "in_progress":
        card.status = "handed_off"
    booked = f"The booking is saved: {card.read_back(session.catalog)}" if card.status == "booked" else ""
    session.outcome = " ".join(filter(None, [
        booked, why,
        "Tell the caller you're putting them through to a member of staff, thank them, and say goodbye.",
    ]))
    return Outcome({"ok": True, "handed_off": True}, END)


# ---------------------------------------------------------------- the registry
@dataclass
class Tool:
    name: str
    description: str
    run: Callable[[CallSession, dict], Outcome]
    properties: dict = field(default_factory=dict)
    required: list = field(default_factory=list)
    moves_to: tuple = ()   # stages this tool can move to (code decides which)


def _tools() -> dict:
    tools = [
        Tool("start_booking", (
            "Call once you have the caller's full name, whether they've been a patient with us before, and (for "
            "returning patients) their date of birth. Also pass anything they've already said they want. "
            "If it returns ok false with a 'say', say that sentence and follow it (ask again, ask them to spell "
            "their last name, or offer to register them as a new patient or put them through to staff). "
            "If they choose to register as new, call again with returning false."),
            start_booking,
            {"full_name": {"type": "string", "description": "The caller's full name, first and last."},
             "returning": {"type": "boolean", "description": "true if they've been a patient with us before."},
             "date_of_birth": {"type": "string", "description": "Returning patients only: YYYY-MM-DD."},
             "spelled_last_name": {"type": "string", "description": (
                 "Only when asked to spell: the letters they spelled, joined (\"WILSON\").")},
             "visit_description": {"type": "string", "description": "What they want, in their words (\"knee MRI\")."},
             **WISH_FIELDS},
            ["full_name", "returning"], (VISIT_TYPE, END)),
        Tool("list_visit_types", (
            "List every visit type in one specialty, each marked can_book for THIS caller, with the reason if not. "
            "Pick the specialty that fits what the caller wants from the names in your instructions."),
            list_visit_types,
            {"specialty": {"type": "string", "description": "One specialty name from your instructions."}},
            ["specialty"]),
        Tool("choose_visit_type", (
            "Call when the caller has picked a visit type. If it's refused, explain the reason in plain words "
            "and offer the alternative it gives. Also pass any new wishes they mentioned in this stage."),
            choose_visit_type,
            {"visit_type_id": {"type": "string", "description": "The id from list_visit_types."}, **WISH_FIELDS},
            ["visit_type_id"], (BOOKING,)),
        Tool("choose_option", (
            "Call when the caller picks one of the options on offer. Returns the read-back sentence to say."),
            choose_option,
            {"option_id": {"type": "string", "description": "The option number from your instructions."}},
            ["option_id"]),
        Tool("confirm_booking", (
            "Call only after the caller said yes to the read-back. Saves the booking. If the time was taken "
            "meanwhile, fresh options are found."),
            confirm_booking, {}, [], (END, BOOKING)),
        Tool("turn_down_doctors", (
            "The caller doesn't want certain doctors. \"Someone else\" or \"a different doctor\" while options are "
            "on offer: on_offer true. \"Not him\" or \"not her\" about the doctor just chosen: current true. "
            "\"Not Dr. Chen\": doctor_name \"Dr. Chen\". If several doctors match the name, you get their ids: "
            "call again with doctor_id. Fresh options follow."),
            turn_down_doctors,
            {"doctor_name": {"type": "string", "description": "A doctor's name only (\"Dr. Chen\")."},
             "doctor_id": {"type": "string", "description": "A doctor_id from an earlier which_one reply."},
             "on_offer": {"type": "boolean", "description": "Turn down every doctor in the options on offer."},
             "current": {"type": "boolean", "description": "Turn down the doctor just chosen."}},
            [], (BOOKING,)),
        Tool("change_choice", (
            "The caller wants a different (or new) visit type, doctor, place, time or language. Send what, plus "
            "only the fields for that kind:\n"
            "- visit_type: new_value = what they want now, in their words.\n"
            "- doctor: new_value = a doctor's name, or \"\" for any doctor." + TURN_DOWN_HINT + "\n"
            "- location: new_value = a place name, or \"\" for anywhere; near = true for somewhere close to it.\n"
            "- time: days and/or time_of_day (leave one out to keep it; [] or \"\" clears it). No new_value.\n"
            "- language: new_value = one language, or \"\" for any.\n"
            "Once options are on offer, fresh options follow."),
            change_choice,
            {"what": {"type": "string", "enum": list(CHANGEABLE)},
             "new_value": {"type": "string", "description": "See above. Only a name or the visit, never a sentence."},
             "near": {"type": "boolean", "description": "location only: somewhere close to the place."},
             "days": {**WISH_FIELDS["days"], "description": (
                 "time only: ONE day per entry: a weekday name, \"today\", \"tomorrow\" or YYYY-MM-DD. "
                 "[] clears the day wish.")},
             "time_of_day": {"type": "string", "enum": [*TIMES_OF_DAY, ""],
                             "description": "time only: \"morning\", \"afternoon\", or \"\" to clear it."}},
            ["what"], (VISIT_TYPE, BOOKING)),
        Tool("answer_question", (
            "Look up a fact instead of guessing: a location (address, hours, phone, neighbourhood, equipment), "
            "a doctor (specialty, languages, locations, taking new patients?) or a visit type (referral needed? "
            "how long? new patients?)."),
            answer_question_tool,
            {"about": {"type": "string", "enum": ["location", "doctor", "visit_type"]},
             "name": {"type": "string", "description": "The location, doctor or visit type name."}},
            ["about", "name"]),
        Tool("hand_off", (
            "Put the caller through to a member of staff: to reschedule or cancel an appointment, or when they "
            "ask for a person. Ends the call with a goodbye."),
            hand_off,
            {"reason": {"type": "string", "enum": list(HAND_OFF_REASONS)}},
            ["reason"], (END,)),
    ]
    return {t.name: t for t in tools}


TOOLS = _tools()


def run_tool(session: CallSession, name: str, args: dict) -> Outcome:
    """Run one tool, turn a refusal into a reply for the AI, and log the call."""
    args = dict(args or {})
    try:
        outcome = TOOLS[name].run(session, args)
    except Refused as e:
        outcome = _refused(str(e))
    session.log({"event": "tool", "stage": session.stage, "tool": name, "args": args,
                 "result": outcome.result, "next_stage": outcome.next_stage})
    return outcome
