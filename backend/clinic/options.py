"""Find up to 3 bookable options (doctor + location + time) for this caller.

Only options that already pass every rule are returned, so the AI can't pick an
impossible one. The caller's wishes (a doctor, a place, a day or time, a
language) narrow those options, one at a time, in this order of strength:

1. the thing the caller changed most recently (`Preferences.latest`);
2. other things the caller said: doctor, place, day/time, language;
3. choices carried over from earlier in the call (a doctor or place chosen
   before the caller changed something else).

A wish is applied only if some option still survives it. A wish that can't be
met is never silently dropped: it becomes a note for the agent to say, and
every note is checked against ALL valid options before it's written, so it
is always true:

- impossible for anyone: "None of the doctors who offer Skin Cancer Screening speaks Klingon."
- impossible together with a stronger wish: "Dr. Daniel Chen isn't available at Midtown Medical Group."

How the options are picked: if the caller named a place, by distance from it
(unless they asked for the soonest); otherwise soonest first. Different
doctor/location pairs are offered before extra times with the same pair, so
the caller gets a real choice.

Each note is a sentence with a label (`Note.kind`), so the tool layer can
react to the kind (e.g. ask "which one?") without searching the text.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Callable, Iterator, Optional

from .card import CLEAR_WORDS, Preferences
from .catalog import Catalog, VisitType, distance_miles
from .patients import Caller
from .rules import can_book_visit_type, pair_problems
from .slots import DAYS_AHEAD, Schedule, spoken_time

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
TIMES_OF_DAY = {"morning": lambda t: t.hour < 12, "afternoon": lambda t: t.hour >= 12}
# Below this, saying "about 0.1 miles from X" adds nothing: it's effectively the same place.
DISTANCE_WORTH_SAYING = 0.2
# How many names to read out in "Doctors who can: ..." before saying "and N more".
NAMES_TO_READ = 3

# Note kinds
NOT_BOOKABLE = "not_bookable"          # this caller can't book this visit type at all
BAD_INPUT = "bad_input"                # a day/time value the code can't use: rephrase and retry
DOCTOR_NOT_FOUND = "doctor_not_found"  # no doctor by that name
DOCTOR_NAME_GUESS = "doctor_name_guess"  # only approximate name matches: check with the caller
SAME_NAME = "doctors_same_name"        # several doctors share the name: ask which one
PLACE_UNKNOWN = "place_unknown"        # place words not recognised
PLACE_AMBIGUOUS = "place_ambiguous"    # place words fit several locations: ask which one
WISH_IMPOSSIBLE = "wish_impossible"    # a wish nobody can meet
WISH_CONFLICT = "wish_conflict"        # a wish that can't be met together with a stronger one
NO_TIMES = "no_times"                  # nothing open at all in the booking window


class Note(str):
    """A sentence for the agent to say, labelled with what kind of note it is.

    It behaves exactly like a string (so it can be read, joined and searched),
    plus a `kind` attribute; `to_dict()` gives {"kind": ..., "say": ...}.
    """

    kind: str

    def __new__(cls, kind: str, say: str):
        note = super().__new__(cls, say)
        note.kind = kind
        return note

    def to_dict(self) -> dict:
        return {"kind": self.kind, "say": str(self)}


@dataclass
class Option:
    option_id: str
    provider_id: str
    provider_name: str
    location_id: str
    location_name: str
    start: datetime
    spoken: str
    distance_miles: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "option_id": self.option_id, "provider_id": self.provider_id,
            "provider_name": self.provider_name, "location_id": self.location_id,
            "location_name": self.location_name, "start": self.start.isoformat(),
            "spoken": self.spoken, "distance_miles": self.distance_miles,
        }


@dataclass
class OptionsResult:
    options: list = field(default_factory=list)  # [Option], at most `limit`
    notes: list = field(default_factory=list)    # [Note]
    bookable: bool = True

    def to_dict(self) -> dict:
        return {"bookable": self.bookable, "notes": [n.to_dict() for n in self.notes],
                "options": [o.to_dict() for o in self.options]}


# ---------------------------------------------------------------- input checks
def check_time_wishes(days, time_of_day, now: datetime) -> tuple:
    """Turn day and time wishes into filters, or explain what can't be used.

    Accepted days: a weekday name ("Thursday", "thu", "thurs"), "today", "tomorrow",
    or a date as YYYY-MM-DD. Accepted times: "morning" (before 12:00) or
    "afternoon" (12:00 or later). Blank values or "any" mean no wish.
    Returns (day_tests, label, time_test, problems).
    """
    day_tests, labels, problems = [], [], []
    for raw in days or []:
        d = str(raw).strip().lower()
        if not d or d in CLEAR_WORDS:
            continue
        if d in ("today", "tomorrow"):
            target = now.date() + timedelta(days=0 if d == "today" else 1)
            day_tests.append(lambda s, t=target: s.date() == t)
            labels.append(d)
            continue
        weekday = next((i for i, w in enumerate(WEEKDAYS) if len(d.rstrip("s")) >= 3 and w.startswith(d.rstrip("s"))), None)
        if weekday is not None:
            day_tests.append(lambda s, i=weekday: s.weekday() == i)
            labels.append(WEEKDAYS[weekday].capitalize())
            continue
        try:
            target = date.fromisoformat(d)
        except ValueError:
            problems.append(f"I couldn't use the day '{raw}'. Pass a weekday name, 'today', 'tomorrow' "
                            f"or a date like {now.date() + timedelta(days=7):%Y-%m-%d}.")
            continue
        day_tests.append(lambda s, t=target: s.date() == t)
        labels.append(f"{target:%A} {target.day} {target:%B}")

    tod = str(time_of_day or "").strip().lower()
    time_test = None
    if tod and tod not in CLEAR_WORDS:
        if tod in TIMES_OF_DAY:
            time_test = TIMES_OF_DAY[tod]
        else:
            problems.append(f"I couldn't use the time '{time_of_day}'. Pass 'morning' or 'afternoon', or leave it empty.")
            tod = ""
    else:
        tod = ""

    day_label = " or ".join(labels)
    label = f"{day_label} {tod}".strip() if day_label else (f"the {tod}" if tod else "")
    return day_tests, label, time_test, problems


# ---------------------------------------------------------------- open times, lazily
class _Times:
    """Open times per doctor/location pair, worked out only as far as needed and
    shared by every check within one search."""

    def __init__(self, schedule: Schedule, vt: VisitType, now: datetime):
        self.schedule, self.vt, self.now = schedule, vt, now
        self._seen: dict = {}   # pair key -> times found so far
        self._more: dict = {}   # pair key -> iterator for the rest

    def _iter(self, key) -> Iterator[datetime]:
        seen = self._seen.setdefault(key, [])
        if key not in self._more:
            self._more[key] = self.schedule.iter_open_slots(key[0], key[1], self.vt.duration_min, self.now)
        yield from seen
        for t in self._more[key]:
            seen.append(t)
            yield t

    def take(self, pair, ok: Optional[Callable], n: int) -> list:
        out = []
        for t in self._iter((pair[0].id, pair[1].id)):
            if ok is None or ok(t):
                out.append(t)
                if len(out) >= n:
                    break
        return out

    def any_open(self, pairs, ok: Optional[Callable]) -> bool:
        return any(self.take(p, ok, 1) for p in pairs)


# ---------------------------------------------------------------- wishes
@dataclass
class _Wish:
    kind: str        # doctor | place | time | language
    label: str       # how to say it: "Dr. Daniel Chen", "Midtown Medical Group", "Thursday morning"
    context: str     # once applied: "with Dr. Daniel Chen", "at Midtown Medical Group", "on Thursday morning"
    carried: bool    # carried over from an earlier choice (weaker than what the caller said)
    pair_ok: Optional[Callable] = None
    time_ok: Optional[Callable] = None
    impossible: Optional[Callable] = None  # () -> Note, when nobody can meet it


def _join(items: list) -> str:
    items = list(items)
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def _both(a: Optional[Callable], b: Optional[Callable]) -> Optional[Callable]:
    if a and b:
        return lambda t: a(t) and b(t)
    return a or b


def _who_can(pairs: list) -> str:
    """'Dr. Daniel Chen (Dermatology), Dr. Kenji Kim (Dermatology) and 4 more', with no
    name read out twice unexplained (two Maria Garcias get their locations added)."""
    doctors = list({p.id: p for p, _ in pairs}.values())
    labels = [f"{p.name} ({p.specialty})" for p in doctors]
    for i, p in enumerate(doctors):
        if labels.count(labels[i]) > 1:
            labels[i] = f"{p.name} ({p.specialty}, {_join(sorted({l.name for q, l in pairs if q.id == p.id}))})"
    shown = labels[:NAMES_TO_READ]
    more = len(labels) - len(shown)
    return ", ".join(shown) + (f" and {more} more" if more else "")


def _doctor_impossible(catalog: Catalog, caller: Caller, vt: VisitType, label: str, doctors: list,
                       valid: list) -> Note:
    """Why none of these doctors can do this visit for this caller, plus who can."""
    reasons: dict = {}
    for p in doctors:
        if any(q.id == p.id for q, _ in valid):
            reason = f"have no open times for {vt.name} in the next {DAYS_AHEAD} days"
        else:
            broken = {x.rule for lid in p.location_ids
                      for x in pair_problems(caller, vt, p, catalog.locations[lid])}
            if 2 in broken:
                reason = f"don't offer {vt.name}"
            elif 5 in broken:
                reason = "aren't taking new patients"
            else:
                reason = f"don't work at a location with the {vt.required_capability} equipment"
        who = f"{p.name} ({p.specialty})" if reason.startswith("don't offer") else p.name
        reasons.setdefault(reason, []).append(who)
    parts = []
    for reason, names in reasons.items():
        if len(names) == 1:
            reason = reason.replace("don't", "doesn't").replace("aren't", "isn't").replace("have no", "has no")
        parts.append(f"{_join(names)} {reason}")
    return Note(WISH_IMPOSSIBLE, f"No doctor matching '{label}' can do this: {'; '.join(parts)}. "
                                 f"Doctors who can: {_who_can(valid)}.")


def find_options(
    catalog: Catalog,
    schedule: Schedule,
    caller: Caller,
    visit_type_id,
    prefs: Preferences,
    now: datetime,
    limit: int = 3,
    first_option_number: int = 1,
) -> OptionsResult:
    b = can_book_visit_type(catalog, caller, visit_type_id)
    if not b.bookable:
        return OptionsResult(bookable=False, notes=[Note(NOT_BOOKABLE, r) for r in b.reasons])
    vt = catalog.visit_types[visit_type_id]

    day_tests, time_label, time_test, problems = check_time_wishes(prefs.days, prefs.time_of_day, now)
    if problems:
        return OptionsResult(notes=[Note(BAD_INPUT, p) for p in problems])

    valid = list(b.valid_pairs)
    times = _Times(schedule, vt, now)
    notes: list = []
    wishes: list = []
    point, point_label = None, ""

    # ---- doctor wishes -----------------------------------------------------
    heard = (prefs.doctor_name_heard or "").strip()
    same_name_ids: set = set()
    if heard:
        matches = catalog.match_providers(heard)
        if not matches:
            notes.append(Note(DOCTOR_NOT_FOUND, f"I couldn't find a doctor called {heard} here."))
        else:
            notes += _name_guess_notes(heard, matches)
            doctors = [m.provider for m in matches]
            ids = {p.id for p in doctors}
            names = sorted({p.name for p in doctors})
            label = names[0] if len(names) == 1 else heard
            same_name_ids = ids
            wishes.append(_Wish(
                "doctor", label, f"with {label}", carried=False,
                pair_ok=lambda pr, ids=ids: pr[0].id in ids,
                impossible=lambda d=doctors, l=heard: _doctor_impossible(catalog, caller, vt, l, d, valid),
            ))
    if prefs.preferred_provider_id in catalog.providers:
        p = catalog.providers[prefs.preferred_provider_id]
        wishes.append(_Wish(
            "doctor", p.name, f"with {p.name}", carried=True,
            pair_ok=lambda pr, pid=p.id: pr[0].id == pid,
            impossible=lambda p=p: _doctor_impossible(catalog, caller, vt, p.name, [p], valid),
        ))

    # ---- place wishes ------------------------------------------------------
    hint = (prefs.location_hint or "").strip()
    if hint:
        place = catalog.resolve_place(hint)
        if place.kind == "none":
            notes.append(Note(PLACE_UNKNOWN, f"I don't recognise the place '{hint}'. "
                                             "Ask for a neighbourhood, a street or one of our location names."))
        elif place.kind == "ambiguous":
            names = [catalog.locations[i].name for i in place.location_ids]
            notes.append(Note(PLACE_AMBIGUOUS, f"'{hint}' could mean {' or '.join(names)}. Ask the caller which one."))
            either = " or ".join(names)
            wishes.append(_Wish(
                "place", either, f"at {either}", carried=False,
                pair_ok=lambda pr, ids=set(place.location_ids): pr[1].id in ids,
                impossible=lambda e=either: Note(WISH_IMPOSSIBLE, f"{e} has nothing available for {vt.name} "
                                                                  f"in the next {DAYS_AHEAD} days."),
            ))
        else:
            point, point_label = place.point, place.label
            if place.kind == "location" and not place.near:
                loc = catalog.locations[place.location_ids[0]]
                wishes.append(_place_wish(loc, vt, carried=False))
    if prefs.preferred_location_id in catalog.locations:
        loc = catalog.locations[prefs.preferred_location_id]
        point, point_label = point or loc.point, point_label or loc.name
        wishes.append(_place_wish(loc, vt, carried=True))

    # ---- time and language wishes -----------------------------------------
    if day_tests or time_test:
        day_ok = (lambda t: any(test(t) for test in day_tests)) if day_tests else None
        wishes.append(_Wish(
            "time", time_label, f"on {time_label}" if day_tests else f"in {time_label}", carried=False,
            time_ok=_both(day_ok, time_test),
            impossible=lambda: Note(WISH_IMPOSSIBLE, f"Nothing is open on {time_label} for {vt.name} in the next "
                                                     f"{DAYS_AHEAD} days; these are the nearest other times."),
        ))
    language = (prefs.language or "").strip()
    if language:
        lang = language.lower()
        wishes.append(_Wish(
            "language", f"A {language.capitalize()}-speaking doctor", f"with a {language.capitalize()}-speaking doctor",
            carried=False,
            pair_ok=lambda pr: lang in {l.lower() for l in pr[0].languages},
            impossible=lambda: Note(WISH_IMPOSSIBLE, f"None of the doctors who offer {vt.name} speaks "
                                                     f"{language.capitalize()}."),
        ))

    # ---- apply wishes, strongest first -------------------------------------
    strength = {"doctor": 1, "place": 2, "time": 3, "language": 4}
    wishes.sort(key=lambda w: (w.carried, w.kind != prefs.latest, strength[w.kind]))
    pairs, time_ok, applied = valid, None, []
    for w in wishes:
        narrowed = [pr for pr in pairs if w.pair_ok is None or w.pair_ok(pr)]
        narrowed_time = _both(time_ok, w.time_ok)
        if times.any_open(narrowed, narrowed_time):
            pairs, time_ok = narrowed, narrowed_time
            applied.append(w)
            continue
        alone = [pr for pr in valid if w.pair_ok is None or w.pair_ok(pr)]
        if not times.any_open(alone, w.time_ok):
            notes.append(w.impossible())
        else:
            context = " ".join(a.context for a in applied)
            notes.append(Note(WISH_CONFLICT, f"{w.label} isn't available {context}."))

    if len(same_name_ids) > 1:
        offering = sorted({pr[0].id for pr in pairs if pr[0].id in same_name_ids})
        if len(offering) > 1:
            desc = []
            for pid in offering:
                p = catalog.providers[pid]
                places = sorted({loc.name for q, loc in pairs if q.id == pid})
                desc.append(f"{p.name}, {p.title} ({p.specialty}) at {' / '.join(places)}")
            notes.append(Note(SAME_NAME, f"There are {len(offering)} doctors matching '{heard}' who offer "
                                         f"{vt.name}: " + "; ".join(desc) + ". Ask the caller which one they mean."))

    # ---- rank and pick -----------------------------------------------------
    firsts = {(p.id, l.id): times.take((p, l), time_ok, 1) for p, l in pairs}
    ranked = [(p, l) for p, l in pairs if firsts[(p.id, l.id)]]
    if not ranked:
        notes.append(Note(NO_TIMES, f"There are no open times for {vt.name} in the next {DAYS_AHEAD} days."))
        return OptionsResult(options=[], notes=notes)

    def dist(loc) -> Optional[float]:
        return round(distance_miles(point, loc.point), 1) if point else None

    by_distance = point is not None and not prefs.soonest
    if by_distance:
        ranked.sort(key=lambda pr: (dist(pr[1]), firsts[(pr[0].id, pr[1].id)][0]))
    else:
        ranked.sort(key=lambda pr: firsts[(pr[0].id, pr[1].id)][0])

    candidates = {(p.id, l.id): times.take((p, l), time_ok, limit) for p, l in ranked}
    picked = []
    for round_no in range(limit):
        for p, l in ranked:
            if len(picked) < limit and len(candidates[(p.id, l.id)]) > round_no:
                picked.append((p, l, candidates[(p.id, l.id)][round_no]))
    if not by_distance:
        picked.sort(key=lambda x: x[2])

    options = []
    for i, (p, loc, start) in enumerate(picked):
        d = dist(loc)
        where = f"{loc.name} ({loc.neighbourhood})" if loc.neighbourhood else loc.name
        spoken = f"{p.name} at {where}, {spoken_time(start)}"
        if d is not None and d >= DISTANCE_WORTH_SAYING:
            spoken += f", about {d} miles from {point_label}"
        options.append(Option(str(first_option_number + i), p.id, p.name, loc.id, loc.name, start, spoken, d))
    return OptionsResult(options=options, notes=notes)


def _name_guess_notes(heard: str, matches: list) -> list:
    """Say so when the name matched only approximately, so the agent checks with the caller."""
    if all(m.is_exact for m in matches):
        return []
    listed = _join([f"{m.provider.name} ({m.provider.specialty})" for m in matches[:NAMES_TO_READ]])
    if not all(m.first_name_matched for m in matches):
        return [Note(DOCTOR_NAME_GUESS, f"There's no doctor called {heard}. Doctors with that surname: {listed}. "
                                        "Check with the caller.")]
    return [Note(DOCTOR_NAME_GUESS, f"No doctor is called exactly '{heard}'. Closest "
                                    f"{'match' if len(matches) == 1 else 'matches'} ({matches[0].describe()}): "
                                    f"{listed}. Check with the caller.")]


def _place_wish(loc, vt: VisitType, carried: bool) -> _Wish:
    return _Wish(
        "place", loc.name, f"at {loc.name}", carried=carried,
        pair_ok=lambda pr, lid=loc.id: pr[1].id == lid,
        impossible=lambda: Note(WISH_IMPOSSIBLE, f"{loc.name} has nothing available for {vt.name} in the next "
                                                 f"{DAYS_AHEAD} days; these are the closest alternatives."),
    )
