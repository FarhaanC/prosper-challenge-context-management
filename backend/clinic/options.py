"""Find up to 3 bookable options (doctor + location + time) for this caller.

Only options that already pass every rule are returned, so the AI can't pick an
impossible one. The caller's wishes (a doctor, a place, a day or time, a
language) narrow those options one at a time, strongest first:

1. the thing the caller changed most recently (`Preferences.latest`);
2. other things the caller said: doctor, then place, then day/time, then language;
3. choices carried over from earlier in the call (a doctor or place chosen
   before the caller changed something else).

A wish is applied only if some option still survives it. A wish that can't be
met is never silently dropped: it becomes a note for the agent to say, and the
note is checked against ALL valid options before it's written, so it's true:

- nobody can meet it: "None of the doctors available to you for Skin Cancer Screening speaks Hindi."
- it clashes with a stronger wish: "Dr. Daniel Chen isn't available at Midtown Medical Group."

Doctors the caller turned down (BookingCard.turn_down_doctors) are left out,
unless nobody else can do the visit, or the caller names them again
(card.turned_down_ids has the rule).

How the options are picked: if the caller named a place, by distance from it
(unless they asked for the soonest); otherwise soonest first. Different
doctor/location pairs are offered before extra times with the same pair, so the
caller gets a real choice.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Callable, Optional

from .card import DOCTOR, LANGUAGE, LOCATION, TIME, TIMES_OF_DAY, Preferences, turned_down_ids
from .catalog import Catalog, VisitType, distance_miles
from .fuzzy import NOT_NAME_WORDS, looks_like_a_sentence, means_no_preference, tidy
from .patients import Caller
from .rules import can_book_visit_type, pair_problems
from .slots import DAYS_AHEAD, Schedule, booking_days, is_iso_date, spoken_time

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
# The day words accepted, each meaning one weekday: full names, plurals ("thursdays")
# and the usual short forms. Nothing else, so "thus" or "frid" is refused, not guessed.
SHORT_DAYS = {"mon": 0, "tue": 1, "tues": 1, "wed": 2, "thu": 3, "thur": 3, "thurs": 3, "fri": 4, "sat": 5, "sun": 6}
WEEKDAY_WORDS = {**{w: i for i, w in enumerate(WEEKDAYS)}, **{w + "s": i for i, w in enumerate(WEEKDAYS)}, **SHORT_DAYS}
# Below this, saying "about 0.1 miles from X" adds nothing: it's effectively the same place.
DISTANCE_WORTH_SAYING = 0.2
# How many names to read out in "Doctors who can: ..." before saying "and N more".
NAMES_TO_READ = 3
# Order among the things the caller said (lower = stronger), after the latest change.
STRENGTH = {DOCTOR: 1, LOCATION: 2, TIME: 3, LANGUAGE: 4}

# Note kinds
NOT_BOOKABLE = "not_bookable"            # this caller can't book this visit type at all
BAD_INPUT = "bad_input"                  # a value the code can't use (day, time, doctor, place, language): resend it
DOCTOR_NOT_FOUND = "doctor_not_found"    # no doctor by that name
DOCTOR_NAME_GUESS = "doctor_name_guess"  # only approximate name matches: check with the caller
SAME_NAME = "doctors_same_name"          # several doctors share the name: ask which one
NO_OTHER_DOCTOR = "no_other_doctor"      # the caller turned a doctor down, but nobody else can do it
PLACE_UNKNOWN = "place_unknown"          # a place name we don't recognise
PLACE_AMBIGUOUS = "place_ambiguous"      # a place name that fits several locations: ask which one
WISH_IMPOSSIBLE = "wish_impossible"      # a wish nobody can meet
WISH_CONFLICT = "wish_conflict"          # a wish that can't be met together with a stronger one
NO_TIMES = "no_times"                    # nothing open at all in the booking window


@dataclass(frozen=True)
class Note:
    """Something the agent should tell the caller: a short label for what kind of
    note it is (so the tool layer can react, e.g. ask "which one?"), and the sentence."""

    kind: str
    say: str

    def __str__(self) -> str:
        return self.say

    def to_dict(self) -> dict:
        return {"kind": self.kind, "say": self.say}


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


# ---------------------------------------------------------------- small helpers
def _join(items, word: str = "and") -> str:
    items = list(items)
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + f" {word} " + items[-1]


def _a(word: str) -> str:
    """'a Spanish-speaking', 'an Arabic-speaking', 'a Ukrainian-speaking' (U said "you")."""
    w = word.lower()
    vowel_sound = w[:1] in "aeiou" and not w.startswith(("uk", "uni", "eu", "us"))
    return ("an " if vowel_sound else "a ") + word


def _both(a: Optional[Callable], b: Optional[Callable]) -> Optional[Callable]:
    """Combine two optional tests into one that needs both."""
    if a and b:
        return lambda x: a(x) and b(x)
    return a or b


# ---------------------------------------------------------------- day and time wishes
@dataclass
class TimeTests:
    """A day/time wish turned into tests. day_ok tests a date; time_ok tests a start time."""

    day_ok: Optional[Callable] = None
    time_ok: Optional[Callable] = None
    phrase: str = ""            # "on Thursday in the morning", "today"
    dates_only: bool = False    # only actual dates ("today", "2026-10-10"): don't add "in the next 14 days"
    problems: list = field(default_factory=list)


def check_time_wishes(days, time_of_day, now: datetime) -> TimeTests:
    """Turn the day and time-of-day values into tests, or say what can't be used.

    These are plain values the AI fills in, never phrases. Each day entry is one of:
    a weekday name ("Thursday", "Thursdays", or short: see SHORT_DAYS), "today", "tomorrow", or a
    date written YYYY-MM-DD inside the booking window. The time of day is "morning"
    (before 12:00) or "afternoon" (12:00 or later). Empty and "no preference" values
    mean no wish. Anything else ("Thursday morning", "next Thursday", "evening",
    "morning or afternoon") is a problem, with a sentence telling the AI how to pass it.
    """
    window = booking_days(now)
    day_tests, labels, problems = [], [], []
    weekdays_named = False
    for raw in days or []:
        d = tidy(raw).lower().rstrip(".")
        if not d or means_no_preference(d):
            continue
        if d in ("today", "tomorrow"):
            target = window[0] if d == "today" else window[1]
            day_tests.append(lambda day, t=target: day == t)
            labels.append(d)
            continue
        weekday = WEEKDAY_WORDS.get(d)
        if weekday is not None:
            day_tests.append(lambda day, i=weekday: day.weekday() == i)
            labels.append("on " + WEEKDAYS[weekday].capitalize())
            weekdays_named = True
            continue
        target = date.fromisoformat(d) if is_iso_date(d) else None
        if target is None:
            problems.append(f"I couldn't use the day '{raw}'. Pass each day on its own: a weekday name, 'today', "
                            f"'tomorrow' or a date like {window[7]:%Y-%m-%d}. Put morning or afternoon "
                            "in the time of day.")
        elif not window[0] <= target <= window[-1]:
            problems.append(f"{target:%A} {target.day} {target:%B} is outside the booking window "
                            f"({window[0].day} {window[0]:%B} to {window[-1].day} {window[-1]:%B}).")
        else:
            day_tests.append(lambda day, t=target: day == t)
            labels.append(f"on {target:%A} {target.day} {target:%B}")

    tod = tidy(time_of_day).lower()
    time_ok = None
    if tod and not means_no_preference(tod):
        if tod == TIMES_OF_DAY[0]:
            time_ok = lambda t: t.hour < 12  # noqa: E731
        elif tod == TIMES_OF_DAY[1]:
            time_ok = lambda t: t.hour >= 12  # noqa: E731
        else:
            problems.append(f"I couldn't use the time of day '{time_of_day}'. Pass 'morning' or 'afternoon', or leave "
                            "it empty (to look at mornings on one day and afternoons on another, search one day "
                            "at a time).")
    day_ok = (lambda day: any(test(day) for test in day_tests)) if day_tests else None
    phrase = " ".join(filter(None, [_join(labels, "or") if labels else "", f"in the {tod}" if time_ok else ""]))
    return TimeTests(day_ok, time_ok, phrase, bool(labels) and not weekdays_named, problems)


# ---------------------------------------------------------------- open times, per search
class _Times:
    """Open times for each doctor/location pair, worked out one day at a time and
    only as far as a check needs. One is made per search and thrown away after."""

    def __init__(self, schedule: Schedule, vt: VisitType, now: datetime):
        self.schedule, self.vt, self.now = schedule, vt, now
        self.days = booking_days(now)
        self._by_day: dict = {}  # (provider, location, date) -> open start times

    def take(self, pair, day_ok: Optional[Callable], time_ok: Optional[Callable], n: int) -> list:
        p, loc = pair
        out = []
        for day in self.days:
            if day_ok and not day_ok(day):
                continue  # skipped without working out its times
            key = (p.id, loc.id, day)
            if key not in self._by_day:
                self._by_day[key] = self.schedule.open_slots_on(p.id, loc.id, self.vt.duration_min, day, self.now)
            for t in self._by_day[key]:
                if time_ok is None or time_ok(t):
                    out.append(t)
                    if len(out) >= n:
                        return out
        return out

    def any_open(self, pairs, day_ok: Optional[Callable], time_ok: Optional[Callable]) -> bool:
        return any(self.take(pr, day_ok, time_ok, 1) for pr in pairs)


# ---------------------------------------------------------------- wishes
@dataclass
class _Wish:
    """One thing the caller wants, as plain data. Which options fit it is decided by
    the fields that are set: doctors, locations, a language, or day/time tests."""

    kind: str                                    # DOCTOR | LOCATION | TIME | LANGUAGE
    label: str                                   # "Dr. Daniel Chen", "Midtown Medical Group", "on Wednesday"
    context: str                                 # once applied: "with Dr. Daniel Chen", "at Midtown Medical Group"
    carried: bool = False                        # carried over from an earlier choice (weaker)
    provider_ids: Optional[frozenset] = None
    location_ids: Optional[frozenset] = None
    language: str = ""
    day_ok: Optional[Callable] = None
    time_ok: Optional[Callable] = None
    doctors: tuple = ()                          # for explaining a doctor wish nobody can meet
    heard: str = ""                              # the caller's words for a doctor wish

    def fits(self, pair) -> bool:
        p, loc = pair
        if self.provider_ids is not None and p.id not in self.provider_ids:
            return False
        if self.location_ids is not None and loc.id not in self.location_ids:
            return False
        return not self.language or self.language.lower() in {l.lower() for l in p.languages}


# Why one doctor can't do a visit for this caller: (one doctor, several doctors).
_REASONS = {
    "offer": ("doesn't offer {vt}", "don't offer {vt}"),
    "new": ("isn't taking new patients", "aren't taking new patients"),
    "equipment": ("doesn't work at a location with the {cap} equipment",
                  "don't work at a location with the {cap} equipment"),
    "times": ("has no open times for {vt} in the next {days} days",
              "have no open times for {vt} in the next {days} days"),
}


def _why_doctor_cant(catalog: Catalog, caller: Caller, vt: VisitType, p, valid: list) -> str:
    """Which _REASONS entry applies to this doctor, from the same rule checks as everywhere else."""
    if any(q.id == p.id for q, _ in valid):
        return "times"
    broken = {x.rule for lid in p.location_ids for x in pair_problems(caller, vt, p, catalog.locations[lid])}
    if 2 in broken:
        return "offer"
    if 5 in broken:
        return "new"
    return "equipment"


def _a_few(items: list, sep: str = ", ", word: str = "and") -> str:
    """Read out at most NAMES_TO_READ items: 'A, B and C', or 'A, B, C and 4 more'
    ('or' with word="or"). Items that contain commas use sep='; ': 'A; B; C; and 4 more'."""
    shown, more = items[:NAMES_TO_READ], len(items) - NAMES_TO_READ
    if sep != ", ":
        return sep.join(shown + ([f"{word} {more} more"] if more > 0 else []))
    return ", ".join(shown) + f" {word} {more} more" if more > 0 else _join(shown, word)


def _labels(doctors: list, places_of: Callable, with_specialty: bool = True) -> list:
    """How to say each doctor: 'Dr. Kenji Kim (Dermatology)', or just the name. A label
    that would otherwise repeat becomes 'Dr. Daniel Chen (Dermatology, Downtown Health
    Center / Richmond Care Center)', so two doctors with the same name are never read
    out as if they were one. Labels are counted before any is changed.
    `places_of(doctor)` gives the place names to add."""
    base = [f"{p.name} ({p.specialty})" if with_specialty else p.name for p in doctors]
    repeated = {label for label, n in Counter(base).items() if n > 1}
    return [f"{p.name} ({p.specialty}, {' / '.join(sorted(places_of(p)))})" if label in repeated else label
            for p, label in zip(doctors, base)]


def _who_can(pairs: list) -> str:
    """'Dr. Daniel Chen (Dermatology), Dr. Kenji Kim (Dermatology) and 4 more', with no
    name read out twice unexplained (two Maria Garcias get their locations added)."""
    doctors = list({p.id: p for p, _ in pairs}.values())
    return _a_few(_labels(doctors, lambda p: {l.name for q, l in pairs if q.id == p.id}))


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

    when = check_time_wishes(prefs.days, prefs.time_of_day, now)
    language, language_problem = _known_language(catalog, prefs.language)
    problems = when.problems + ([language_problem] if language_problem else []) + _sentence_problems(prefs)
    if problems:
        return OptionsResult(notes=[Note(BAD_INPUT, p) for p in problems])

    times = _Times(schedule, vt, now)
    notes: list = []
    every_valid = [pr for pr in b.valid_pairs if times.any_open([pr], None, None)]  # valid AND has open times

    wishes, point, point_label, place_notes = _place_wishes(catalog, prefs)
    notes += place_notes
    doctor_wishes, doctor_notes = _doctor_wishes(catalog, prefs)
    wishes += doctor_wishes
    notes += doctor_notes
    if when.day_ok or when.time_ok:
        wishes.append(_Wish(TIME, when.phrase, when.phrase, day_ok=when.day_ok, time_ok=when.time_ok))
    if language:
        wishes.append(_Wish(LANGUAGE, language, f"with {_a(language + '-speaking')} doctor", language=language))

    # Doctors the caller turned down are left out, unless nobody else can do it.
    turned_down = turned_down_ids(catalog, prefs)
    valid = [pr for pr in every_valid if pr[0].id not in turned_down]
    if turned_down and every_valid and not valid:
        valid = every_valid  # all of them were turned down
        only_one = len({p.id for p, _ in every_valid}) == 1
        notes.append(Note(NO_OTHER_DOCTOR, f"No other doctor can do {vt.name} for you; {_who_can(every_valid)} "
                                           + ("is the only option." if only_one else "are the only options.")))

    by_distance = point is not None and not prefs.soonest

    # ---- apply wishes, strongest first -------------------------------------
    wishes.sort(key=lambda w: (w.kind != prefs.latest, w.carried, STRENGTH[w.kind]))
    pairs, applied = valid, []
    for w in wishes:
        narrowed = [pr for pr in pairs if w.fits(pr)]
        narrowed_day, narrowed_time = _both(day_ok_of(applied), w.day_ok), _both(time_ok_of(applied), w.time_ok)
        if times.any_open(narrowed, narrowed_day, narrowed_time):
            pairs = narrowed
            applied.append(w)
            continue
        alone = [pr for pr in valid if w.fits(pr)]
        with_turned_down = [pr for pr in every_valid if w.fits(pr)]
        if times.any_open(alone, w.day_ok, w.time_ok):
            notes.append(_conflict_note(w, applied))
        elif times.any_open(with_turned_down, w.day_ok, w.time_ok):
            able = {p.name for p, l in with_turned_down
                    if p.id in turned_down and times.any_open([(p, l)], w.day_ok, w.time_ok)}
            notes.append(_turned_down_note(w, sorted(able)))
        else:
            notes.append(_impossible_note(catalog, caller, vt, w, b.valid_pairs, valid, by_distance, when))

    for w in applied:
        if w.kind == DOCTOR and w.heard and len(w.provider_ids or ()) > 1:
            notes += _same_name_note(catalog, vt, w, pairs)

    # ---- rank and pick -----------------------------------------------------
    final_day, final_time = day_ok_of(applied), time_ok_of(applied)
    firsts = {(p.id, l.id): times.take((p, l), final_day, final_time, 1) for p, l in pairs}
    ranked = [(p, l) for p, l in pairs if firsts[(p.id, l.id)]]
    if not ranked:
        notes.append(Note(NO_TIMES, f"There are no open times for {vt.name} in the next {DAYS_AHEAD} days."))
        return OptionsResult(options=[], notes=notes)

    def dist(loc) -> Optional[float]:
        return round(distance_miles(point, loc.point), 1) if point else None

    if by_distance:
        ranked.sort(key=lambda pr: (dist(pr[1]), firsts[(pr[0].id, pr[1].id)][0]))
    else:
        ranked.sort(key=lambda pr: firsts[(pr[0].id, pr[1].id)][0])

    candidates = {(p.id, l.id): times.take((p, l), final_day, final_time, limit) for p, l in ranked}
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


def day_ok_of(wishes: list) -> Optional[Callable]:
    tests = [w.day_ok for w in wishes if w.day_ok]
    return tests[0] if tests else None  # at most one time wish exists


def time_ok_of(wishes: list) -> Optional[Callable]:
    tests = [w.time_ok for w in wishes if w.time_ok]
    return tests[0] if tests else None


# ---------------------------------------------------------------- building wishes
# A language value must be one language name. On top of the words no name has
# (NOT_NAME_WORDS), these show the AI passed a sentence ("no Spanish", "any language").
NOT_A_LANGUAGE = NOT_NAME_WORDS | {"no", "language", "languages", "speaker", "speakers", "speaking"}


# Other names for a language in our records. Kept to the obvious; nothing is guessed
# ("Chinese" on its own isn't here: it could mean Mandarin or Cantonese).
LANGUAGE_ALSO_CALLED = {"mandarin chinese": "Mandarin", "chinese mandarin": "Mandarin"}


def _known_language(catalog: Catalog, said) -> tuple:
    """Returns (language, problem).

    The value must be one language name: a language in our records ("spanish" ->
    'Spanish'), one of its other names ("Mandarin Chinese" -> 'Mandarin'), or a name
    we have no record of ('Klingon', 'Haitian Creole', 'ASL'), which is kept as said so
    find_options can say truthfully that none of our doctors is listed as speaking it.
    "No preference" words mean no language wish. Anything else is refused with a
    problem saying how to pass it: a sentence ("not Spanish"), more than two words, or
    a value that mixes a language we have with other words ("Spanish French",
    "Spanish only"), because picking one of the words would be a guess."""
    words = tidy(said)
    if not words or means_no_preference(words):
        return "", ""
    low = words.lower()
    spoken = {l.lower(): l for p in catalog.providers.values() for l in p.languages}
    if low in spoken:
        return spoken[low], ""
    if low in LANGUAGE_ALSO_CALLED:
        return LANGUAGE_ALSO_CALLED[low], ""
    parts = low.split()
    if (len(parts) > 2 or not all(w.isalpha() for w in parts) or set(parts) & NOT_A_LANGUAGE
            or any(w in spoken for w in parts)):
        return "", (f"I couldn't use the language '{words}'. Pass one language name, like 'Spanish', "
                    "or leave it empty for no language wish.")
    return " ".join(w[:1].upper() + w[1:] for w in words.split()), ""  # keeps "ASL" as said


def _sentence_problems(prefs: Preferences) -> list:
    """A doctor or place value that is a sentence ("not Dr. Chen", "anywhere but
    Downtown") is refused rather than matched by spelling, which could turn a refusal
    into a wish for that very doctor or place."""
    problems = []
    doctor = tidy(prefs.doctor_name_heard)
    if doctor and not means_no_preference(doctor) and looks_like_a_sentence(doctor):
        problems.append(f"I couldn't use the doctor name '{doctor}'. Pass just the doctor's name, or leave it "
                        "empty for no doctor wish. To turn doctors down, use turn_down_doctors.")
    place = tidy(prefs.location_hint)
    if place and not means_no_preference(place) and looks_like_a_sentence(place):
        problems.append(f"I couldn't use the place '{place}'. Pass just a place name (a neighbourhood, street or "
                        "location name; set near for somewhere close), or leave it empty for no place wish.")
    return problems


def _doctor_wishes(catalog: Catalog, prefs: Preferences) -> tuple:
    wishes, notes = [], []
    heard = tidy(prefs.doctor_name_heard)
    if heard and not means_no_preference(heard):
        matches = catalog.match_providers(heard)
        if not matches:
            notes.append(Note(DOCTOR_NOT_FOUND, f"I couldn't find a doctor called {heard} here."))
        else:
            notes += _name_guess_notes(catalog, heard, matches)
            doctors = tuple(m.provider for m in matches)
            names = sorted({p.name for p in doctors})
            label = names[0] if len(names) == 1 else heard
            wishes.append(_Wish(DOCTOR, label, f"with {label}", provider_ids=frozenset(p.id for p in doctors),
                                doctors=doctors, heard=heard))
    p = catalog.providers.get(prefs.preferred_provider_id) if isinstance(prefs.preferred_provider_id, str) else None
    if p:
        wishes.append(_Wish(DOCTOR, p.name, f"with {p.name}", carried=True, provider_ids=frozenset([p.id]),
                            doctors=(p,)))
    return wishes, notes


def _place_wishes(catalog: Catalog, prefs: Preferences) -> tuple:
    """Returns (wishes, point to rank by distance from, its name, notes)."""
    wishes, notes, point, point_label = [], [], None, ""
    hint = tidy(prefs.location_hint)
    if hint:
        place = catalog.resolve_place(hint, near=prefs.near)
        if place.kind == "none":
            notes.append(Note(PLACE_UNKNOWN, f"I don't recognise the place '{hint}'. Pass just a place name: "
                                             "a neighbourhood, a street or one of our location names."))
        elif place.kind == "ambiguous":
            either = _a_few([catalog.locations[i].name for i in place.location_ids], word="or")
            notes.append(Note(PLACE_AMBIGUOUS, f"'{hint}' could mean {either}. Ask the caller which one."))
            if not place.near:  # "Mission" narrows to those; near the Mission doesn't narrow
                wishes.append(_Wish(LOCATION, either, f"at {either}", location_ids=frozenset(place.location_ids)))
        elif place.kind in ("location", "landmark"):
            point, point_label = place.point, place.label
            if place.kind == "location" and not place.near:
                loc = catalog.locations[place.location_ids[0]]
                wishes.append(_Wish(LOCATION, loc.name, f"at {loc.name}", location_ids=frozenset([loc.id])))
    loc = catalog.locations.get(prefs.preferred_location_id) if isinstance(prefs.preferred_location_id, str) else None
    if loc:
        point, point_label = point or loc.point, point_label or loc.name
        wishes.append(_Wish(LOCATION, loc.name, f"at {loc.name}", carried=True, location_ids=frozenset([loc.id])))
    return wishes, point, point_label, notes


# ---------------------------------------------------------------- notes
def _conflict_note(w: _Wish, applied: list) -> Note:
    """The wish could be met on its own, but not together with the stronger ones."""
    context = " ".join(a.context for a in applied)
    if w.kind == LANGUAGE:
        return Note(WISH_CONFLICT, f"No {w.language}-speaking doctor is available {context}.")
    if w.kind == TIME:
        return Note(WISH_CONFLICT, f"There's nothing {w.label} {context}.")
    return Note(WISH_CONFLICT, f"{w.label} isn't available {context}.")


def _turned_down_note(w: _Wish, names: list) -> Note:
    """The wish could only be met by doctors the caller turned down. `names`: those
    turned-down doctors who really have times meeting it."""
    listed = _a_few(names)
    if w.kind == DOCTOR:  # "Dr. Chen", when the only Chen who can do it was turned down
        if len(names) == 1:
            return Note(WISH_CONFLICT, f"The only doctor matching '{w.heard or w.label}' who can do this is "
                                       f"{names[0]}, whom you turned down. Check whether the caller wants "
                                       "that doctor after all.")
        return Note(WISH_CONFLICT, f"The only doctors matching '{w.heard or w.label}' who can do this are "
                                   f"{listed}, whom you turned down. Check whether the caller wants "
                                   "one of them after all.")
    subject = w.label
    if w.kind == TIME:  # "on Wednesday 7 October" -> "Wednesday 7 October"; "in the morning" -> "The morning"
        subject = re.sub(r"^on ", "", subject)
        subject = re.sub(r"^in the ", "the ", subject)
    subject = subject[:1].upper() + subject[1:]
    return Note(WISH_CONFLICT, f"{subject} is only possible with {listed}, whom you turned down.")


def _impossible_note(catalog: Catalog, caller: Caller, vt: VisitType, w: _Wish, rule_ok: list, valid: list,
                     by_distance: bool, when: TimeTests) -> Note:
    """Nobody can meet this wish. `rule_ok`: pairs passing the rules; `valid`: those with open times."""
    days = DAYS_AHEAD
    if w.kind == LANGUAGE:
        listed = sorted({l for p in catalog.providers.values() for l in p.languages})
        if w.language not in listed:  # "Chinese", "Klingon": not a language in our records at all
            return Note(WISH_IMPOSSIBLE, f"None of our doctors is listed as speaking {w.language}. "
                                         f"Our doctors speak {_join(listed)}.")
        return Note(WISH_IMPOSSIBLE, f"None of the doctors available to you for {vt.name} speaks {w.language}.")
    if w.kind == TIME:
        window = "" if when.dates_only else f" in the next {days} days"
        return Note(WISH_IMPOSSIBLE, f"Nothing is open {w.label} for {vt.name}{window}; here are other options.")
    if w.kind == LOCATION:
        tail = "; these are the closest alternatives." if by_distance else "; here are other options."
        return Note(WISH_IMPOSSIBLE, f"{w.label} has nothing available for {vt.name} in the next {days} days{tail}")
    # DOCTOR: say why each matching doctor can't, and who can.
    groups: dict = {}
    for p in w.doctors:
        groups.setdefault(_why_doctor_cant(catalog, caller, vt, p, rule_ok), []).append(p)
    parts = []
    for code, doctors in groups.items():
        one, many = _REASONS[code]
        reason = (one if len(doctors) == 1 else many).format(vt=vt.name, cap=vt.required_capability, days=days)
        labels = _labels(doctors, lambda p: _place_names(catalog, p), with_specialty=(code == "offer"))
        parts.append(f"{_a_few(labels)} {reason}")
    said = w.heard or w.label
    who = f" Doctors who can: {_who_can(valid)}." if valid else ""
    return Note(WISH_IMPOSSIBLE, f"No doctor matching '{said}' can do this: {'; '.join(parts)}.{who}")


def _same_name_note(catalog: Catalog, vt: VisitType, w: _Wish, pairs: list) -> list:
    offering = sorted({p.id for p, _ in pairs if p.id in w.provider_ids})
    if len(offering) < 2:
        return []
    desc = []
    for pid in offering:
        p = catalog.providers[pid]
        places = sorted({loc.name for q, loc in pairs if q.id == pid})
        desc.append(f"{p.name}, {p.title} ({p.specialty}) at {' / '.join(places)}")
    return [Note(SAME_NAME, f"There are {len(offering)} doctors matching '{w.heard}' who offer {vt.name}: "
                            + _a_few(desc, "; ") + ". Ask the caller which one they mean.")]


def _place_names(catalog: Catalog, p) -> set:
    return {catalog.locations[lid].name for lid in p.location_ids}


def _name_guess_notes(catalog: Catalog, heard: str, matches: list) -> list:
    """Say so when the name matched only approximately, so the agent checks with the caller."""
    if all(m.is_exact for m in matches):
        return []
    listed = _a_few(_labels([m.provider for m in matches], lambda p: _place_names(catalog, p)))
    if not all(m.first_name_matched for m in matches):
        return [Note(DOCTOR_NAME_GUESS, f"There's no doctor called {heard}. Doctors with that surname: {listed}. "
                                        "Check with the caller.")]
    return [Note(DOCTOR_NAME_GUESS, f"No doctor is called exactly '{heard}'. Closest "
                                    f"{'match' if len(matches) == 1 else 'matches'} ({matches[0].describe()}): "
                                    f"{listed}. Check with the caller.")]
