"""The clinic catalog, held by code (never pasted whole into the AI's instructions).

Loads the given `catalog.json` untouched, plus our own fake map data
(`location_extras.json`), checks both, and answers small questions:

- the list of specialties, and the visit types inside one specialty
- doctors matching a (possibly misheard) name: ALL matches, because names
  repeat (two Dr. Maria Garcias), each labelled with how close the match is
- which location, landmark or street a caller means ("near Downtown",
  "the Midtown one", "the one on Geary"), and distances between places
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from datetime import time
from pathlib import Path
from typing import Optional

from .fuzzy import EXACT, NONE, QUALITY_NAMES, means_no_preference, normalize, person_match, similarity

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

DAY_ABBREVIATIONS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# A specialty name said slightly wrong ("nuerology", "cardiolgy") still matches at
# this spelling similarity; "astrology" vs "urology" (0.75) doesn't. The words for
# the doctor ("dermatologist") must match exactly: close spelling there misfires
# ("podiatrist" is very like "pediatrist", "hematologist" like "dermatologist").
SPECIALTY_SPELLING = 0.85
# For answer_question's visit-type lookup: at least half the caller's words must
# appear in the name, or the whole phrase must be spelled 70% alike.
VISIT_WORD_OVERLAP = 0.5
VISIT_SPELLING = 0.7
# Place words this short must match exactly: spelling closeness on short words
# misfires ("main" is 80% like "marina", "none" like "noe", "Marin", a county,
# 91% like "Marina"). Longer words may be misspelled: "Richmund", "fishermans".
SHORT_PLACE_WORD = 5
PLACE_SPELLING = 0.8

# Words in place phrases that don't help tell places apart.
GENERIC_PLACE_WORDS = {
    "health", "center", "centre", "clinic", "medical", "group", "family", "specialty",
    "care", "community", "the", "one", "office", "location", "hospital", "place",
    "site", "branch", "please", "a", "of", "in", "at", "to", "from", "and",
}
CITY_WORDS = {"sf", "san", "francisco", "city"}
STREET_WORDS = {"street", "avenue", "boulevard", "road", "lane"}
STREET_ABBREVIATIONS = {"st", "ave", "blvd", "rd", "ln"}  # count only as the last word ("Mission St", not "St Mary's")
# Phrases meaning "close to X": rank by distance from X rather than requiring X.
NEAR_WORDS = ("on the way to", "not far from", "closest to", "closer to", "close to", "next to",
              "nearby", "near", "around", "by")
NEAR_PHRASE = re.compile(r"\b(" + "|".join(NEAR_WORDS) + r")\b")
FILLER_PREFIX = re.compile(
    r"^(?:(?:somewhere|anywhere|something|one|the one|a clinic|a place)\s+)?"
    r"(?:(?:" + "|".join(NEAR_WORDS + ("in", "at", "on")) + r")\s+)?"
    r"(?:the\s+)?"
)
ON_A_STREET = re.compile(r"(^|\s)on\s")
FILLER_SUFFIX = re.compile(r"(?:\s+(?:area|side|neighbou?rhood|one|location|clinic|office|please))+$")


@dataclass(frozen=True)
class Location:
    id: str
    name: str
    address: str
    city: str
    phone: str
    hours: str
    capabilities: tuple
    open_days: frozenset  # weekday numbers, Monday = 0
    opens: time
    closes: time
    neighbourhood: str
    also_called: tuple
    lat: float
    lon: float

    @property
    def point(self) -> tuple:
        return (self.lat, self.lon)

    @property
    def street(self) -> str:
        """'4455 Geary Blvd' -> 'geary'."""
        words = [w for w in normalize(self.address).split()
                 if not w.isdigit() and w not in STREET_WORDS | STREET_ABBREVIATIONS]
        return " ".join(words)

    @property
    def house_number(self) -> str:
        """'4455 Geary Blvd' -> '4455'."""
        return next((w for w in normalize(self.address).split() if w.isdigit()), "")


@dataclass(frozen=True)
class Provider:
    id: str
    name: str
    title: str
    specialty: str
    location_ids: tuple
    accepting_new_patients: bool
    languages: tuple
    appointment_type_ids: tuple


@dataclass(frozen=True)
class VisitType:
    id: str
    name: str
    specialty: str
    duration_min: int
    requires_referral: bool
    new_patients_allowed: bool
    required_capability: Optional[str] = None


@dataclass(frozen=True)
class ProviderMatch:
    """One doctor matching a heard name, and how good the match is."""

    provider: Provider
    quality: int              # fuzzy.EXACT, CLOSE or SOUNDS_LIKE
    first_name_matched: bool  # False: caller's first name matched nobody; surname only

    @property
    def is_exact(self) -> bool:
        return self.quality == EXACT and self.first_name_matched

    def describe(self) -> str:
        return QUALITY_NAMES[self.quality]


@dataclass
class PlaceMatch:
    """What a caller's place words resolved to."""

    kind: str  # "location" | "landmark" | "ambiguous" | "any" (no preference) | "none" (not recognised)
    label: str = ""
    location_ids: list = field(default_factory=list)  # one if kind=location, several if ambiguous
    point: Optional[tuple] = None  # (lat, lon) to measure distance from
    near: bool = False  # "near X" (rank by distance) rather than "the X one" (only X)


class CatalogError(ValueError):
    """The catalog or our extra data is broken. Raised at load, so it fails loudly and early."""


def parse_hours(hours: str) -> tuple:
    """'Mon-Fri 8:00-17:00' -> ({0,1,2,3,4}, time(8,0), time(17,0)). Anything else is an error."""
    m = re.fullmatch(r"\s*(\w{3})-(\w{3})\s+(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})\s*", hours or "")
    if not m or m.group(1) not in DAY_ABBREVIATIONS or m.group(2) not in DAY_ABBREVIATIONS:
        raise CatalogError(f"Can't read opening hours {hours!r}; expected e.g. 'Mon-Fri 8:00-17:00'.")
    d1, d2 = DAY_ABBREVIATIONS.index(m.group(1)), DAY_ABBREVIATIONS.index(m.group(2))
    try:
        opens, closes = time(int(m.group(3)), int(m.group(4))), time(int(m.group(5)), int(m.group(6)))
    except ValueError:  # "8:00-25:00"
        raise CatalogError(f"Opening hours {hours!r} contain a time that doesn't exist.") from None
    if d2 < d1 or closes <= opens:
        raise CatalogError(f"Opening hours {hours!r} don't make sense.")
    return frozenset(range(d1, d2 + 1)), opens, closes


def distance_miles(a: tuple, b: tuple) -> float:
    """Straight-line ("as the crow flies") distance between two (lat, lon) points."""
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 3958.8 * 2 * math.asin(math.sqrt(h))


def _distinct_words(text: str) -> list:
    """The words of a place name that tell it apart, in order: 'Mission Bay Health Center' -> ['mission', 'bay']."""
    return [w for w in normalize(text).split() if w not in GENERIC_PLACE_WORDS | CITY_WORDS]


def _word_fits(heard: str, real: str) -> bool:
    if heard == real:
        return True
    if min(len(heard), len(real)) <= SHORT_PLACE_WORD:
        return False
    return similarity(heard, real) >= PLACE_SPELLING


def _name_fits(heard: set, name: str, said: str = "") -> bool:
    """Does what the caller said pick out this place name?

    Every word they said must fit a word of the name, AND they must have said the
    name's first distinctive word or all of its words. So "Mission" fits Mission Bay,
    but "Bay", "Valley" or "Gate" on their own don't pick anything. `said` is the
    caller's words run together, so "mid town" still fits "Midtown".
    """
    words = _distinct_words(name)
    if not heard or not words:
        return False
    if said and said == "".join(words):
        return True
    if not all(any(_word_fits(h, w) for w in words) for h in heard):
        return False
    said_lead = any(_word_fits(h, words[0]) for h in heard)
    said_all = all(any(_word_fits(h, w) for h in heard) for w in words)
    return said_lead or said_all


_TEXT, _LIST, _YES_NO, _NUMBER = "text", "list of text", "true/false", "whole number"
_LATITUDE, _LONGITUDE = "a latitude (a number from -90 to 90)", "a longitude (a number from -180 to 180)"
_TEXT_OR_EMPTY = "text (it may be empty)"
REQUIRED_FIELDS = {
    "locations": {"id": _TEXT, "name": _TEXT, "address": _TEXT, "city": _TEXT, "phone": _TEXT, "hours": _TEXT},
    "providers": {"id": _TEXT, "name": _TEXT, "title": _TEXT, "specialty": _TEXT, "location_ids": _LIST,
                  "accepting_new_patients": _YES_NO, "languages": _LIST, "appointment_type_ids": _LIST},
    "appointment_types": {"id": _TEXT, "name": _TEXT, "specialty": _TEXT, "duration_min": _NUMBER,
                          "requires_referral": _YES_NO, "new_patients_allowed": _YES_NO},
}


# Fields that may be left out, but must be the right kind of value when present.
OPTIONAL_FIELDS = {
    "locations": {"capabilities": _LIST},
    "providers": {},
    "appointment_types": {"required_capability": _TEXT},
}
EXTRA_LOCATION_FIELDS = {"lat": _LATITUDE, "lon": _LONGITUDE}
EXTRA_LOCATION_OPTIONAL = {"neighbourhood": _TEXT_OR_EMPTY, "also_called": _LIST}


def _right_type(value, kind: str) -> bool:
    if kind in (_LATITUDE, _LONGITUDE):
        limit = 90 if kind == _LATITUDE else 180
        return isinstance(value, (int, float)) and not isinstance(value, bool) and -limit <= value <= limit
    if kind == _TEXT_OR_EMPTY:
        return isinstance(value, str)
    if kind == _TEXT:
        return isinstance(value, str) and bool(value.strip())
    if kind == _LIST:
        return isinstance(value, list) and all(isinstance(v, str) for v in value)
    if kind == _YES_NO:
        return isinstance(value, bool)
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _check_records(raw: dict) -> list:
    """Missing sections or fields, wrong kinds of value, and repeated ids, as plain sentences."""
    problems = []
    for section, fields in REQUIRED_FIELDS.items():
        records = raw.get(section) if isinstance(raw, dict) else None
        if not isinstance(records, list):
            problems.append(f"The catalog has no '{section}' list.")
            continue
        seen = set()
        for i, r in enumerate(records):
            if not isinstance(r, dict):
                problems.append(f"{section} entry #{i} isn't a record.")
                continue
            rid = r.get("id") if isinstance(r.get("id"), str) else None  # a list as an id mustn't crash the check
            label = rid or f"#{i}"
            missing = [f for f in fields if f not in r]
            if missing:
                problems.append(f"{section} entry {label} is missing {', '.join(missing)}.")
            checked = {**fields, **OPTIONAL_FIELDS[section]}
            wrong = [f"{f} should be {kind}" for f, kind in checked.items()
                     if f in r and not (r[f] is None and f in OPTIONAL_FIELDS[section]) and not _right_type(r[f], kind)]
            if wrong:
                problems.append(f"{section} entry {label}: {'; '.join(wrong)}.")
            if rid is not None and rid in seen:
                problems.append(f"{section} id {label} appears more than once.")
            seen.add(rid)
    return problems


def _check_extras(extras, location_ids: list) -> list:
    """Our own map data (location_extras.json), checked like the catalog: every
    location needs a real latitude and longitude, and landmarks need a point."""
    if not isinstance(extras, dict) or not isinstance(extras.get("locations"), dict):
        return ["location_extras.json has no 'locations' record."]
    problems = []
    for lid in location_ids:
        x = extras["locations"].get(lid)
        if not isinstance(x, dict):
            problems.append(f"Location {lid} has no coordinates in location_extras.json.")
            continue
        missing = [f for f in EXTRA_LOCATION_FIELDS if f not in x]
        if missing:
            problems.append(f"Location {lid} in location_extras.json is missing {', '.join(missing)}.")
        checked = {**EXTRA_LOCATION_FIELDS, **EXTRA_LOCATION_OPTIONAL}
        wrong = [f"{f} should be {kind}" for f, kind in checked.items() if f in x and not _right_type(x[f], kind)]
        if wrong:
            problems.append(f"Location {lid} in location_extras.json: {'; '.join(wrong)}.")
    landmarks = extras.get("landmarks", {})
    if not isinstance(landmarks, dict):
        problems.append("location_extras.json: landmarks should be a record of name -> [latitude, longitude].")
    else:
        for name, point in landmarks.items():
            if not (isinstance(point, list) and len(point) == 2
                    and _right_type(point[0], _LATITUDE) and _right_type(point[1], _LONGITUDE)):
                problems.append(f"Landmark {name!r} in location_extras.json should be [latitude, longitude].")
    return problems


def _find_problems(raw, extras) -> list:
    """Every problem with the catalog and our map data, as plain sentences, so one
    load lists them all: missing or wrong fields, repeated ids, map data, opening
    hours, and doctors pointing at locations or visit types that don't exist."""
    problems = _check_records(raw)
    if any(p.startswith("The catalog has no") for p in problems):
        return problems  # a whole section is missing; nothing further can be checked

    def records(section):
        return [r for r in raw[section] if isinstance(r, dict) and isinstance(r.get("id"), str)]

    locations, visit_types = records("locations"), records("appointment_types")
    problems += _check_extras(extras, [l["id"] for l in locations])
    for l in locations:
        if isinstance(l.get("hours"), str):
            try:
                parse_hours(l["hours"])
            except CatalogError as e:
                problems.append(f"Location {l['id']}: {e}")
    location_ids, visit_type_ids = {l["id"] for l in locations}, {a["id"] for a in visit_types}
    for p in records("providers"):
        where, offers = p.get("location_ids"), p.get("appointment_type_ids")
        if isinstance(where, list):
            problems += [f"Doctor {p['id']} works at unknown location {lid}." for lid in where
                         if isinstance(lid, str) and lid not in location_ids]
            if not where:
                problems.append(f"Doctor {p['id']} works at no location.")
        if isinstance(offers, list):
            problems += [f"Doctor {p['id']} offers unknown visit type {vt}." for vt in offers
                         if isinstance(vt, str) and vt not in visit_type_ids]
    return problems


# The usual word for a doctor whose specialty name doesn't follow the regular
# English pattern (dermatology -> dermatologist, allergy -> allergist,
# psychiatry -> psychiatrist, physical therapy -> physical therapist).
IRREGULAR_DOCTOR_WORDS = {
    "dental": ["dentist"],
    "orthopedics": ["orthopedist"],
    "pediatrics": ["pediatrician"],
}


def _doctor_words(specialty: str) -> list:
    """The usual word(s) for a doctor in this specialty (written without spaces),
    or [] if there isn't one ("ENT", "Family Medicine")."""
    if specialty in IRREGULAR_DOCTOR_WORDS:
        return IRREGULAR_DOCTOR_WORDS[specialty]
    if specialty.endswith("y"):
        return [specialty[:-1] + "ist"]
    return []


class Catalog:
    def __init__(self, raw: dict, extras: dict):
        problems = _find_problems(raw, extras)
        if problems:
            raise CatalogError("The catalog data has problems:\n- " + "\n- ".join(problems))
        # Everything below can trust the data: it has all been checked.
        extra_locs = extras["locations"]
        self.locations: dict = {}
        for l in raw["locations"]:
            x = extra_locs[l["id"]]
            days, opens, closes = parse_hours(l["hours"])
            self.locations[l["id"]] = Location(
                id=l["id"], name=l["name"], address=l["address"], city=l["city"], phone=l["phone"],
                hours=l["hours"], capabilities=tuple(l.get("capabilities") or []),
                open_days=days, opens=opens, closes=closes,
                neighbourhood=x.get("neighbourhood", ""), also_called=tuple(x.get("also_called", [])),
                lat=float(x["lat"]), lon=float(x["lon"]),
            )
        self.visit_types: dict = {
            a["id"]: VisitType(
                id=a["id"], name=a["name"], specialty=a["specialty"], duration_min=a["duration_min"],
                requires_referral=a["requires_referral"], new_patients_allowed=a["new_patients_allowed"],
                required_capability=a.get("required_capability"),
            )
            for a in raw["appointment_types"]
        }
        self.providers: dict = {
            p["id"]: Provider(
                id=p["id"], name=p["name"], title=p["title"], specialty=p["specialty"],
                location_ids=tuple(p["location_ids"]), accepting_new_patients=p["accepting_new_patients"],
                languages=tuple(p["languages"]), appointment_type_ids=tuple(p["appointment_type_ids"]),
            )
            for p in raw["providers"]
        }
        self.landmarks: dict = {k: tuple(v) for k, v in extras.get("landmarks", {}).items()}

        # Indexes built once, so lookups stay fast as the catalog grows.
        self._providers_for_type: dict = {vt: [] for vt in self.visit_types}
        for p in self.providers.values():
            for vt in p.appointment_type_ids:
                self._providers_for_type[vt].append(p)
        self._types_by_specialty: dict = {}
        for vt in self.visit_types.values():
            self._types_by_specialty.setdefault(vt.specialty, []).append(vt)

    # ---- loading -----------------------------------------------------------
    @classmethod
    def load(cls, data_dir: Path = DATA_DIR) -> "Catalog":
        data_dir = Path(data_dir)
        raw = json.loads((data_dir / "catalog.json").read_text(encoding="utf-8"))
        extras = json.loads((data_dir / "location_extras.json").read_text(encoding="utf-8"))
        return cls(raw, extras)

    # ---- visit types -------------------------------------------------------
    def specialties(self) -> list:
        return sorted(self._types_by_specialty)

    def match_specialty(self, text) -> Optional[str]:
        """Map the AI's wording to a catalog specialty: "OBGYN", "ob-gyn", "Allergy" (one
        half of "Allergy/Immunology"), or the word for the doctor ("dermatologist",
        "pediatrician", "dentist", "physical therapist"). None if unsure."""
        said = normalize(text).replace(" ", "")
        if not said:
            return None
        best, best_score = None, 0.0
        for s in self.specialties():
            names = [normalize(s).replace(" ", "")] + [normalize(p).replace(" ", "") for p in s.split("/")]
            doctor_words = [w for n in names for w in _doctor_words(n)]
            if said in names or said.rstrip("s") in doctor_words:
                return s
            score = max(similarity(said, n) for n in names)
            if score > best_score:
                best, best_score = s, score
        return best if best_score >= SPECIALTY_SPELLING else None

    def visit_types_in(self, specialty: str) -> list:
        return list(self._types_by_specialty.get(specialty, []))

    def providers_offering(self, visit_type_id: str) -> list:
        return list(self._providers_for_type.get(visit_type_id, []))

    def find_visit_types_by_name(self, text, limit: int = 3) -> list:
        """For answering questions ("does a knee MRI need a referral?"), not for booking."""
        q = set(normalize(text).split())
        if not q:
            return []
        scored = []
        for vt in self.visit_types.values():
            overlap = len(q & set(normalize(vt.name).split())) / len(q)
            spelling = similarity(text, vt.name)
            if overlap >= VISIT_WORD_OVERLAP or spelling >= VISIT_SPELLING:
                scored.append((max(overlap, spelling), vt))
        scored.sort(key=lambda s: -s[0])
        return [vt for _, vt in scored[:limit]]

    # ---- doctors -----------------------------------------------------------
    def match_providers(self, heard) -> list:
        """Every doctor in the best tier of matches for the heard name, with match quality.

        Duplicate names are returned together on purpose, so the agent can ask
        "which one?" instead of guessing. Weaker tiers are dropped: if "Maria Garcia"
        matches two Marias exactly, Carlos Garcia (surname only) is not returned.
        """
        scored = []
        for p in self.providers.values():
            rank = person_match(heard, p.name)
            if rank.quality != NONE:
                scored.append((rank, ProviderMatch(p, rank.quality, bool(rank.whole_name))))
        if not scored:
            return []
        top = max(r for r, _ in scored)
        return [m for r, m in scored if r == top]

    def find_providers_by_name(self, heard) -> list:
        return [m.provider for m in self.match_providers(heard)]

    # ---- places ------------------------------------------------------------
    def resolve_place(self, hint) -> PlaceMatch:
        """Work out what place a caller means.

        In this order:
        1. "Anywhere", "no preference" -> kind "any": no place wish.
        2. If the caller named a street ("Mission Street", "Geary Blvd") or said
           "on X" ("the one on Geary"): a street from our addresses. If they said a
           street word and it isn't one of ours, stop: it's not recognised.
        3. One of our locations by name, nickname or neighbourhood ("Mission Bay",
           "the Midtown one", "the Hayes Valley one") -> that location.
           A name several locations share ("Mission", "North") -> ambiguous: ask.
        4. A known landmark or neighbourhood ("near Union Square", "Chinatown").
        5. Steps 3-4 again without the word "district" ("the Marina District").
        With "near", "closer to" and the like, near=True: rank by distance, don't restrict.
        """
        text = normalize(hint)
        if not text:
            return PlaceMatch(kind="none")
        if means_no_preference(text):
            return PlaceMatch(kind="any")
        near = bool(NEAR_PHRASE.search(text))
        on_street = bool(ON_A_STREET.search(text))
        core = FILLER_SUFFIX.sub("", FILLER_PREFIX.sub("", text)).strip()
        words = set(_distinct_words(core))
        if not words:
            # Only city words ("in SF") or generic ones: no particular place.
            return PlaceMatch(kind="any") if set(core.split()) & CITY_WORDS else PlaceMatch(kind="none", label=str(hint))

        last = core.split()[-1]
        if words & STREET_WORDS or last in STREET_ABBREVIATIONS:
            street_words = words - STREET_WORDS - STREET_ABBREVIATIONS
            return self._match_street(street_words, near) or PlaceMatch(kind="none", label=str(hint))
        if on_street:
            found = self._match_street(words, near)
            if found:
                return found
        for attempt in (words, words - {"district"}):
            said = "".join(w for w in core.split() if w in attempt)
            found = self._match_locations(attempt, said, near) or self._match_landmarks(attempt, said)
            if found:
                return found
        if near:  # "near Geary": a street, said without "street"
            found = self._match_street(words, near)
            if found:
                return found
        return PlaceMatch(kind="none", label=str(hint))

    def _match_locations(self, words: set, said: str, near: bool) -> Optional[PlaceMatch]:
        hits = [loc for loc in self.locations.values()
                if any(n and _name_fits(words, n, said) for n in (loc.name, loc.neighbourhood, *loc.also_called))]
        if len(hits) > 1:
            # "Mission District" names Mission District fully but Mission Bay only partly.
            full = [l for l in hits if any(set(_distinct_words(n)) == words
                                           for n in (l.name, l.neighbourhood, *l.also_called) if n)]
            if len(full) == 1:
                hits = full
        if len(hits) == 1:
            loc = hits[0]
            return PlaceMatch(kind="location", label=loc.name, location_ids=[loc.id], point=loc.point, near=near)
        if hits:
            return PlaceMatch(kind="ambiguous", label=" or ".join(l.name for l in hits),
                              location_ids=[l.id for l in hits], near=near)
        return None

    def _match_landmarks(self, words: set, said: str) -> Optional[PlaceMatch]:
        hits = [(name, point) for name, point in self.landmarks.items() if _name_fits(words, name, said)]
        exact = [h for h in hits if set(_distinct_words(h[0])) == words]
        if exact or len(hits) == 1:
            name, point = (exact or hits)[0]
            return PlaceMatch(kind="landmark", label=name, point=point, near=True)
        return None

    def _match_street(self, words: set, near: bool) -> Optional[PlaceMatch]:
        """Our locations on the street the caller named. A house number picks between
        clinics on the same street ("4455 Geary Blvd"). A number none of them has
        ("9999 Geary") is somewhere else on that street, so the street's clinics are
        only used to measure distance from, not as the place they asked for."""
        numbers = {w for w in words if w.isdigit()}
        street = words - numbers
        if not street:
            return None
        on_street = [l for l in self.locations.values() if _name_fits(street, l.street)]
        hits = [l for l in on_street if not numbers or l.house_number in numbers]
        if numbers and not hits:
            hits, near = on_street, True
        if len(hits) == 1:
            l = hits[0]
            return PlaceMatch(kind="location", label=f"{l.name} ({l.address})", location_ids=[l.id],
                              point=l.point, near=near)
        if hits:
            return PlaceMatch(kind="ambiguous", label=" or ".join(f"{l.name} ({l.address})" for l in hits),
                              location_ids=[l.id for l in hits], near=near)
        return None
