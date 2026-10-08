"""The tools the AI calls during a phone call, and the tool registry.

Plain Python, no Pipecat (decision 22). Each tool takes the call's session and the
values the AI sent, calls the clinic module, and returns an Outcome: what the AI
is told, and the stage to move to (or None to stay). Moves are decided here, by
code, never by the AI.

What the AI sends follows the rule in clinic/__init__.py: names (doctors, places,
languages) as the caller said them; everything else a plain value (ids, yes/no,
one weekday or date per day entry, "morning" or "afternoon"). A value of the
wrong kind, or a field the tool doesn't have, is refused with a message saying
how to send it, and a refused call changes nothing. Nothing is guessed.

Every reply has "ok". When it's false, the reply is for the AI to act on and the
caller never hears it, except the identity steps' "say" sentence, which is meant
to be said.

Two checks apply to every tool (run_tool): once the call is booked or handed off,
only answer_question and hand_off work; and tools that need to know who is
calling refuse until start_booking has found or registered the caller.

The registry (TOOLS) holds each tool's description and fields, which is what the
AI reads, and the stages it can move to, which the builder checks against the
agent file and the editor will draw as dashed arrows.

| tool               | where           | moves to                                              |
| start_booking      | identify        | visit_type (found or new), end (staff); else stays    |
| list_visit_types   | visit_type      | stays                                                 |
| choose_visit_type  | visit_type      | booking (accepted), stays (refused)                   |
| choose_option      | booking         | stays (gives the read-back)                           |
| confirm_booking    | booking         | end (saved), booking (time gone: fresh options)       |
| change_choice      | every stage     | booking (fresh options), visit_type, or stays         |
| turn_down_doctors  | every stage     | booking (fresh options), or stays                     |
| answer_question    | every stage     | stays                                                 |
| hand_off           | every stage     | end                                                   |

change_choice and turn_down_doctors record without moving until there are options
to rebuild: before the caller is identified, and in the visit_type stage (decision 47).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from clinic import (
    BOOKING, END, VISIT_TYPE, Caller, Note, alternatives_for, answer_question, can_book_visit_type,
    check_booking, language_problem,
)
from clinic.card import TIMES_OF_DAY
from clinic.fuzzy import looks_like_a_sentence, means_no_preference, name_tokens, tidy
from clinic.options import check_time_wishes

from .session import CallSession

ANY = "any"  # the value that drops a wish in change_choice


@dataclass
class Outcome:
    result: dict                       # what the AI is told
    next_stage: Optional[str] = None   # None: stay in this stage


class Refused(ValueError):
    """A value the tool can't use. The AI is told why and how to send it."""


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
    """A list of day entries, or None if not sent (an empty list counts as not sent)."""
    value = args.get("days")
    if value is None:
        return None
    if not (isinstance(value, list) and all(isinstance(d, str) for d in value)):
        raise Refused("days must be a list, one day per entry, e.g. [\"Thursday\", \"Friday\"].")
    days = [tidy(d) for d in value if tidy(d)]
    return days or None


def _a_name(value: str, kind: str, extra: str = "") -> str:
    """A doctor or place value must be a name, not a sentence ("not Dr. Chen")."""
    if value and not means_no_preference(value) and looks_like_a_sentence(value):
        raise Refused(f"'{value}' isn't a {kind} name. Pass just the name.{extra}")
    return value


def _specialty(session: CallSession, args: dict) -> Optional[str]:
    said = _text(args, "specialty")
    if not said:
        return None
    specialty = session.catalog.match_specialty(said)
    if specialty is None:
        raise Refused(f"'{said}' isn't one of our specialties. Use one of: {', '.join(session.catalog.specialties())}.")
    return specialty


# ---------------------------------------------------------------- wishes
TURN_DOWN_HINT = " For 'someone else' or 'not Dr. X', use turn_down_doctors."

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
        "or a date YYYY-MM-DD (use the year from 'Now' in your instructions). \"Thursday or Friday\" is "
        "[\"Thursday\", \"Friday\"]. Never put a time of day here.")},
    "time_of_day": {"type": "string", "enum": [*TIMES_OF_DAY, ANY], "description": (
        "\"morning\" (before noon) or \"afternoon\" (noon or later). Leave it out if they didn't say.")},
    "soonest": {"type": "boolean", "description": "true if the caller wants the earliest time possible."},
    "language": {"type": "string", "description": "One language the doctor should speak (\"Spanish\")."},
}
SPECIALTY_FIELD = {"type": "string", "description": (
    "If it's clear which of our specialties fits what they want, that specialty's name from your instructions "
    "(its visit types are then ready in the next stage). Leave it out if unsure.")}


@dataclass
class Wishes:
    """Checked wish values; None means not sent. "any" is kept as sent: it means no
    wish when recording, and "drop this wish" in change_choice."""

    doctor: Optional[str] = None
    place: Optional[str] = None
    near: bool = False
    days: Optional[list] = None
    time_of_day: Optional[str] = None
    soonest: Optional[bool] = None
    language: Optional[str] = None


def _read_wishes(session: CallSession, args: dict) -> Wishes:
    """Check every wish value before anything is recorded, so a refused value changes nothing."""
    doctor = _a_name(_text(args, "doctor_name"), "doctor", TURN_DOWN_HINT)
    place = _a_name(_text(args, "place"), "place", " Put closeness in near.")
    near = _flag(args, "near")
    if near and (not place or means_no_preference(place)):
        raise Refused("near goes with a place name. Send the place too.")
    days = _days(args)
    time_of_day = _text(args, "time_of_day").lower() or None
    prefs = session.card.preferences
    problems = check_time_wishes(prefs.days if days is None else days,
                                 prefs.time_of_day if time_of_day is None else time_of_day, session.now()).problems
    if problems:
        raise Refused(" ".join(problems))
    language = _text(args, "language")
    if language:
        problem = language_problem(session.catalog, language)
        if problem:
            raise Refused(problem)
    return Wishes(doctor or None, place or None, bool(near), days, time_of_day, _flag(args, "soonest"),
                  language or None)


def _record(session: CallSession, w: Wishes) -> None:
    """Record the wishes said so far (start_booking, choose_visit_type). "any" means no wish."""
    p = session.card.preferences

    def said(value) -> bool:
        return bool(value) and not means_no_preference(value)

    if said(w.doctor):
        p.doctor_name_heard, p.preferred_provider_id = w.doctor, ""
    if said(w.place):
        p.location_hint, p.near, p.preferred_location_id = w.place, w.near, ""
    if w.days:
        days = [d for d in w.days if not means_no_preference(d)]
        if days:
            p.days = days
    if said(w.time_of_day):
        p.time_of_day = w.time_of_day
    if w.soonest is not None:
        p.soonest = w.soonest
    if said(w.language):
        p.language = w.language


def _after_change(session: CallSession, target: str) -> Outcome:
    """Where a change leads. Before identification, or while choosing the visit, it's
    recorded and the call stays (decision 47). Otherwise the stage is rebuilt."""
    if session.card.caller is None or (target == VISIT_TYPE and session.stage == VISIT_TYPE):
        return Outcome({"ok": True, "noted": "Recorded. Carry on with this stage."})
    if target == BOOKING:
        session.refresh_options()
    else:
        session.offer = None  # the visit changed: the old search no longer applies
    return Outcome({"ok": True}, target)


# ---------------------------------------------------------------- the tools
def start_booking(session: CallSession, args: dict) -> Outcome:
    card = session.card
    if card.caller is not None:
        raise Refused("The caller is already identified.")
    name = _text(args, "full_name")
    returning = _flag(args, "returning")
    if returning is None:
        raise Refused("Send returning: true if they've been a patient with us before, false if not.")
    wishes = _read_wishes(session, args)
    specialty = _specialty(session, args)
    visit = _text(args, "visit_description")

    def record() -> None:
        _record(session, wishes)
        if visit:
            card.preferences.visit_description = visit

    if returning:
        step = card.identity.attempt(session.clinic.patients, name, _text(args, "date_of_birth"),
                                     _text(args, "spelled_last_name"))
        if step.status == "hand_to_staff":
            return _hand_to_staff(session, "The caller's details need checking by a member of staff.")
        if step.status != "found":
            record()  # what they said they want isn't lost while we find them
            return Outcome({"ok": False, "status": step.status, "say": step.say})
        caller = step.caller
    else:
        if len(name_tokens(name)) < 2:
            raise Refused("Ask for the caller's full name (first and last) and send it in full_name.")
        caller = Caller(name=name)

    card.caller = caller
    record()
    session.listed_specialty = specialty
    return Outcome({"ok": True}, VISIT_TYPE)


def list_visit_types(session: CallSession, args: dict) -> Outcome:
    said = _text(args, "specialty")
    specialty = session.catalog.match_specialty(said)
    if specialty is None:
        raise Refused(f"'{said}' isn't one of our specialties. Use one of: {', '.join(session.catalog.specialties())}.")
    session.listed_specialty = specialty
    return Outcome({"ok": True, "specialty": specialty, "visit_types": session.visit_types_for(specialty)})


def choose_visit_type(session: CallSession, args: dict) -> Outcome:
    catalog, card = session.catalog, session.card
    vt_id = _text(args, "visit_type_id")
    if vt_id not in catalog.visit_types:
        raise Refused(f"'{vt_id}' isn't a visit type id. Use an id from the visit types listed.")
    # The caller's wishes count even if this visit can't be booked: they're not a
    # refused value, and dropping them would lose what was said (decision 54).
    _record(session, _read_wishes(session, args))
    b = can_book_visit_type(catalog, card.caller, vt_id)
    if not b.bookable:
        alternatives = [{"id": vt.id, "name": vt.name, "specialty": vt.specialty}
                        for vt in alternatives_for(catalog, card.caller, vt_id)]
        return Outcome({"ok": False, "reasons": b.reasons, "alternatives": alternatives,
                        "careful": "Never promise that an alternative visit will lead to a referral."})
    vt = catalog.visit_types[vt_id]
    card.choices.specialty, card.choices.visit_type_id = vt.specialty, vt.id
    card.preferences.visit_description = vt.name  # the card says what was agreed, not the first words used
    session.refresh_options()
    return Outcome({"ok": True}, BOOKING)


def choose_option(session: CallSession, args: dict) -> Outcome:
    card = session.card
    option_id = args.get("option_id")
    if isinstance(option_id, int) and not isinstance(option_id, bool):
        option_id = str(option_id)  # the AI sometimes sends the number as a number
    if not (isinstance(option_id, str) and option_id.strip().isdigit()):
        raise Refused("option_id must be the option's number only, e.g. \"2\".")
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
    if not (c.provider_id and c.slot):
        raise Refused("Nothing is chosen yet. Call choose_option first, read back, and ask the caller.")
    now = session.now()
    problems = check_booking(catalog, clinic.schedule, card.caller, c.visit_type_id, c.provider_id,
                             c.location_id, c.slot, now)
    if problems:
        # Back to choosing: the doctor and place become wishes, and a fresh search runs.
        # This isn't the caller changing the time, so "soonest" and their latest change are kept.
        prefs = card.preferences
        kept = prefs.soonest, prefs.latest
        card.change_choice("time")
        prefs.soonest, prefs.latest = kept
        session.refresh_options(Note("booking_failed", " ".join(problems) + " Here are other options."))
        return Outcome({"ok": False, "problems": problems}, BOOKING)

    vt = catalog.visit_types[c.visit_type_id]
    read_back = card.read_back(catalog)
    caller, p, loc = card.caller, catalog.providers[c.provider_id], catalog.locations[c.location_id]
    # Saved to the file first, then marked as taken: a failed write leaves nothing half done.
    clinic.save_booking({
        "booked_at": now.isoformat(timespec="minutes"),  # clinic time, like "start"
        "caller": caller.name, "patient_id": caller.patient_id, "new_patient": caller.is_new_patient,
        "visit_type_id": vt.id, "visit_type": vt.name, "provider_id": p.id, "provider": p.name,
        "location_id": loc.id, "location": loc.name, "start": c.slot.isoformat(),
        "duration_min": vt.duration_min, "read_back": read_back,
    })
    clinic.schedule.book(c.provider_id, c.slot, vt.duration_min)
    card.status = "booked"
    session.outcome = (f"The booking is saved: {read_back} Confirm the day, time and doctor in one short "
                       "sentence (not the whole read-back again), thank the caller and say goodbye.")
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
        target = card.turn_down_doctors(catalog, ids, on_offer=on_offer, current=current)
    except ValueError as e:
        raise Refused(str(e)) from e
    return _after_change(session, target)


# The order changes in one change_choice call are applied in: the visit type first (it
# clears everything), then the weakest wish to the strongest, so the strongest kind
# sent counts as the newest (find_options applies the newest change first).
CHANGE_ORDER = ("language", "time", "location", "doctor")


def change_choice(session: CallSession, args: dict) -> Outcome:
    card = session.card
    w = _read_wishes(session, args)
    visit = _text(args, "visit_type")
    specialty = _specialty(session, args)
    if specialty and not visit:
        raise Refused("specialty goes with visit_type. Send what they want now in visit_type too.")
    time_sent = w.days is not None or w.time_of_day is not None or w.soonest is not None
    sent = {"language": w.language is not None, "time": time_sent, "location": w.place is not None,
            "doctor": w.doctor is not None}
    if not (visit or any(sent.values())):
        raise Refused("Send at least one field that changes (or \"any\" to drop a wish).")

    target = None
    if visit:
        target = card.change_choice("visit_type", visit)
        session.listed_specialty = specialty
    for kind in CHANGE_ORDER:
        if not sent[kind]:
            continue
        if kind == "time":
            soonest = w.soonest
            target = card.change_choice("time", days=w.days, time_of_day=w.time_of_day)
            if soonest is not None:
                card.preferences.soonest = soonest  # a time change resets it; this call says what it is
        elif kind == "location":
            target = card.change_choice("location", w.place, near=w.near)
        elif kind == "doctor":
            target = card.change_choice("doctor", w.doctor)
        else:
            target = card.change_choice("language", w.language)
    return _after_change(session, target)


def answer_question_tool(session: CallSession, args: dict) -> Outcome:
    result = answer_question(session.catalog, _text(args, "about"), _text(args, "name"))
    return Outcome({"ok": result["found"], **result})


HAND_OFF_REASONS = {
    "reschedule": "The caller wants to reschedule an appointment.",
    "cancel": "The caller wants to cancel an appointment.",
    "speak_to_staff": "The caller asked to speak to a person.",
}


def hand_off(session: CallSession, args: dict) -> Outcome:
    reason = _text(args, "reason")
    if reason not in HAND_OFF_REASONS:
        raise Refused(f"reason must be one of: {', '.join(HAND_OFF_REASONS)}.")
    return _hand_to_staff(session, HAND_OFF_REASONS[reason])


def _hand_to_staff(session: CallSession, why: str) -> Outcome:
    card = session.card
    changed = card.status == "in_progress"
    if changed:
        card.status = "handed_off"
    booked = f"The booking is saved: {card.read_back(session.catalog)}" if card.status == "booked" else ""
    session.outcome = " ".join(filter(None, [
        booked, why,
        "A member of staff will call the caller back about this. Tell the caller that in one or two short "
        "sentences, thank them and say goodbye.",
    ]))
    return Outcome({"ok": True, "handed_off": changed}, END)


# ---------------------------------------------------------------- the registry
@dataclass
class Tool:
    name: str
    description: str
    run: Callable[[CallSession, dict], Outcome]
    properties: dict = field(default_factory=dict)
    required: list = field(default_factory=list)
    moves_to: tuple = ()        # stages this tool can move to (code decides which)
    needs_caller: bool = False  # refused until start_booking has found or registered the caller
    after_end: bool = False     # still works once the call is booked or handed off


def _tools() -> dict:
    tools = [
        Tool("start_booking", (
            "Call once you have the caller's full name, whether they've been a patient with us before, and (for "
            "returning patients) their date of birth. Also send anything they've already said they want. "
            "If it returns ok false with a 'say', say that sentence and follow it (ask again, ask them to spell "
            "their last name, or offer to register them as a new patient or have a member of staff call them "
            "back). If they choose to register as new, call again with returning false."),
            start_booking,
            {"full_name": {"type": "string", "description": "The caller's full name, first and last."},
             "returning": {"type": "boolean", "description": "true if they've been a patient with us before."},
             "date_of_birth": {"type": "string", "description": "Returning patients only: YYYY-MM-DD."},
             "spelled_last_name": {"type": "string", "description": (
                 "Only when asked to spell: the letters they spelled, joined (\"WILSON\").")},
             "visit_description": {"type": "string", "description": "What they want, in their words (\"knee MRI\")."},
             "specialty": SPECIALTY_FIELD,
             **WISH_FIELDS},
            ["full_name", "returning"], (VISIT_TYPE, END)),
        Tool("list_visit_types", (
            "List every visit type in one specialty, each marked can_book for THIS caller, with the reason if not. "
            "Pick the specialty that fits what the caller wants from the names in your instructions."),
            list_visit_types,
            {"specialty": {"type": "string", "description": "One specialty name from your instructions."}},
            ["specialty"], needs_caller=True),
        Tool("choose_visit_type", (
            "Call when the caller has picked a visit type. If it's refused, explain the reason in plain words "
            "and offer the alternative it gives. Also send any new wishes they mentioned in this stage."),
            choose_visit_type,
            {"visit_type_id": {"type": "string", "description": "The visit type's id from the list."}, **WISH_FIELDS},
            ["visit_type_id"], (BOOKING,), needs_caller=True),
        Tool("choose_option", (
            "Call when the caller picks one of the options on offer. Returns the read-back sentence to say."),
            choose_option,
            {"option_id": {"type": "string", "description": "The option number from your instructions, e.g. \"2\"."}},
            ["option_id"], needs_caller=True),
        Tool("confirm_booking", (
            "Call only after the caller said yes to the read-back. Saves the booking. If the time was taken "
            "meanwhile, fresh options are found."),
            confirm_booking, {}, [], (END, BOOKING), needs_caller=True),
        Tool("turn_down_doctors", (
            "The caller doesn't want certain doctors. \"Not Dr. Chen\": doctor_name \"Dr. Chen\" (works at any "
            "point in the call). \"Someone else\" or \"a different doctor\" while options are on offer: on_offer "
            "true. \"Not him\" or \"not her\" about the doctor just chosen: current true. If several doctors "
            "match a name, you get their ids: call again with doctor_id. Once options are on offer, fresh options "
            "follow."),
            turn_down_doctors,
            {"doctor_name": {"type": "string", "description": "A doctor's name only (\"Dr. Chen\")."},
             "doctor_id": {"type": "string", "description": "A doctor_id from an earlier which_one reply."},
             "on_offer": {"type": "boolean", "description": "Turn down every doctor in the options on offer."},
             "current": {"type": "boolean", "description": "Turn down the doctor just chosen."}},
            [], (VISIT_TYPE, BOOKING)),
        Tool("change_choice", (
            "The caller wants something different, or adds a wish. Send only the fields that change, in the same "
            "form as for start_booking: doctor_name, place (with near), days, time_of_day, soonest, language; or "
            "visit_type for a different kind of visit (what they want now, in their words, plus specialty if "
            "clear). Several can go in one call: \"Friday afternoon at Midtown\" is days [\"Friday\"], "
            "time_of_day \"afternoon\", place \"Midtown\". To drop a wish, send \"any\" (doctor_name \"any\", "
            "days [\"any\"], time_of_day \"any\"). Once options are on offer, fresh options follow."
            + TURN_DOWN_HINT),
            change_choice,
            {"visit_type": {"type": "string", "description": "A different kind of visit, in the caller's words."},
             "specialty": SPECIALTY_FIELD,
             **WISH_FIELDS},
            [], (VISIT_TYPE, BOOKING)),
        Tool("answer_question", (
            "Look up a fact instead of guessing: a location (address, hours, phone, neighbourhood, equipment), "
            "a doctor (specialty, languages, locations, taking new patients?) or a visit type (referral needed? "
            "how long? new patients?)."),
            answer_question_tool,
            {"about": {"type": "string", "enum": ["location", "doctor", "visit_type"]},
             "name": {"type": "string", "description": "The location, doctor or visit type name."}},
            ["about", "name"], after_end=True),
        Tool("hand_off", (
            "For things a member of staff handles: rescheduling or cancelling an appointment, or when the caller "
            "asks for a person. Staff will call them back; this ends the call with a goodbye."),
            hand_off,
            {"reason": {"type": "string", "enum": list(HAND_OFF_REASONS)}},
            ["reason"], (END,), after_end=True),
    ]
    return {t.name: t for t in tools}


TOOLS = _tools()


def _check_call(session: CallSession, tool: Tool, args: dict) -> None:
    unknown = sorted(set(args) - set(tool.properties))
    if unknown:
        known = ", ".join(tool.properties) or "none"
        raise Refused(f"{tool.name} has no field {', '.join(unknown)}. Its fields: {known}.")
    if session.card.status != "in_progress" and not tool.after_end:
        raise Refused("The call is finished (booked or handed to staff); only answer_question and hand_off work now.")
    if tool.needs_caller and session.card.caller is None:
        raise Refused("Identify the caller first, with start_booking.")


def run_tool(session: CallSession, name: str, args: dict) -> Outcome:
    """Run one tool, turn a refusal into a reply for the AI, and log the call.
    An unexpected error is logged too, then raised: it's a bug, not a refusal."""
    tool = TOOLS.get(name)
    if tool is None:
        raise ValueError(f"No tool called {name!r}. Tools: {', '.join(TOOLS)}.")
    args = dict(args or {})
    entry = {"event": "tool", "stage": session.stage, "tool": name, "args": args}
    try:
        _check_call(session, tool, args)
        outcome = tool.run(session, args)
    except Refused as e:
        outcome = Outcome({"ok": False, "error": str(e)})
    except Exception as e:
        session.log({**entry, "error": f"{type(e).__name__}: {e}"})
        raise
    session.log({**entry, "result": outcome.result, "next_stage": outcome.next_stage})
    return outcome
