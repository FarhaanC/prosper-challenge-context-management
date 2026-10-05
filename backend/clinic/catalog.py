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

from .fuzzy import CLOSE, EXACT, QUALITY_NAMES, normalize, person_match, similarity, word_quality

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

DAY_ABBREVIATIONS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# A specialty name typed slightly wrong ("nuerology") still matches at this
# spelling similarity; "astrology" vs "urology" (0.75) does not.
SPECIALTY_SPELLING = 0.85
# "dermatologist" -> stem "dermatolog", which must begin a specialty name. Stems
# shorter than this ("ent" from "dentist" would be 4) are too vague to trust.
SPECIALTY_STEM_MIN = 4
# For answer_question's visit-type lookup: at least half the caller's words must
# appear in the name, or the whole phrase must be spelled 70% alike.
VISIT_WORD_OVERLAP = 0.5
VISIT_SPELLING = 0.7
# A place phrase matches a landmark's name if spelled this alike as a whole.
LANDMARK_SPELLING = 0.85

# Words in location names that don't help tell locations apart.
GENERIC_PLACE_WORDS = {
    "health", "center", "centre", "clinic", "medical", "group", "family", "specialty",
    "care", "community", "the", "one", "office", "location", "hospital", "place",
    "site", "branch", "please", "a", "of",
}
STREET_WORDS = {"street", "st", "avenue", "ave", "boulevard", "blvd", "road", "rd", "way", "lane"}
# Phrases meaning "close to X": rank by distance from X rather than requiring X.
NEAR_PHRASE = re.compile(
    r"\b(near|nearby|close to|closer to|closest to|around|next to|not far from|by|on the way to)\b"
)
FILLER_PREFIX = re.compile(
    r"^(?:(?:somewhere|anywhere|something|one|the one|a clinic|a place)\s+)?"
    r"(?:(?:near|nearby|close to|closer to|closest to|around|in|at|on|by|next to|not far from)\s+)?"
    r"(?:the\s+)?"
)
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
        words = [w for w in normalize(self.address).split() if not w.isdigit() and w not in STREET_WORDS]
        return " ".join(words)


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

    kind: str  # "location" | "landmark" | "ambiguous" | "none"
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
    opens, closes = time(int(m.group(3)), int(m.group(4))), time(int(m.group(5)), int(m.group(6)))
    if d2 < d1 or closes <= opens:
        raise CatalogError(f"Opening hours {hours!r} don't make sense.")
    return frozenset(range(d1, d2 + 1)), opens, closes


def distance_miles(a: tuple, b: tuple) -> float:
    """Straight-line ("as the crow flies") distance between two (lat, lon) points."""
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 3958.8 * 2 * math.asin(math.sqrt(h))


def _distinct_words(text: str, drop: set) -> set:
    return set(normalize(text).split()) - drop


def _words_fit(heard: set, name: set) -> bool:
    """Every heard word matches some word of the name (exactly or by close spelling)."""
    return bool(heard) and all(any(word_quality(h, n, allow_sounds_like=False) >= CLOSE for n in name)
                               for h in heard)


class Catalog:
    def __init__(self, raw: dict, extras: dict):
        problems: list = []
        extra_locs = extras.get("locations", {})

        self.locations: dict = {}
        for l in raw["locations"]:
            x = extra_locs.get(l["id"])
            if not x or "lat" not in x or "lon" not in x:
                problems.append(f"Location {l['id']} has no coordinates in location_extras.json.")
                continue
            try:
                days, opens, closes = parse_hours(l["hours"])
            except CatalogError as e:
                problems.append(f"Location {l['id']}: {e}")
                continue
            self.locations[l["id"]] = Location(
                id=l["id"], name=l["name"], address=l["address"], city=l["city"], phone=l["phone"],
                hours=l["hours"], capabilities=tuple(l.get("capabilities", [])),
                open_days=days, opens=opens, closes=closes,
                neighbourhood=x.get("neighbourhood", ""), also_called=tuple(x.get("also_called", [])),
                lat=float(x["lat"]), lon=float(x["lon"]),
            )
        self.visit_types: dict = {
            a["id"]: VisitType(
                id=a["id"], name=a["name"], specialty=a["specialty"], duration_min=int(a["duration_min"]),
                requires_referral=bool(a["requires_referral"]), new_patients_allowed=bool(a["new_patients_allowed"]),
                required_capability=a.get("required_capability"),
            )
            for a in raw["appointment_types"]
        }
        known_location_ids = {l["id"] for l in raw["locations"]}
        self.providers: dict = {}
        for p in raw["providers"]:
            for lid in p["location_ids"]:
                if lid not in known_location_ids:
                    problems.append(f"Doctor {p['id']} works at unknown location {lid}.")
            for vt in p["appointment_type_ids"]:
                if vt not in self.visit_types:
                    problems.append(f"Doctor {p['id']} offers unknown visit type {vt}.")
            self.providers[p["id"]] = Provider(
                id=p["id"], name=p["name"], title=p["title"], specialty=p["specialty"],
                location_ids=tuple(p["location_ids"]), accepting_new_patients=bool(p["accepting_new_patients"]),
                languages=tuple(p["languages"]), appointment_type_ids=tuple(p["appointment_type_ids"]),
            )
        if problems:
            raise CatalogError("The catalog data has problems:\n- " + "\n- ".join(problems))

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
        """Map the AI's wording to a catalog specialty: "OBGYN", "ob-gyn", "dermatologist",
        "pediatrician", "Allergy" (one half of "Allergy/Immunology"). None if unsure."""
        squashed = normalize(text).replace(" ", "")
        if not squashed:
            return None
        stem = re.sub(r"(ists?|ians?)$", "", squashed)
        best, best_score = None, 0.0
        for s in self.specialties():
            whole = normalize(s).replace(" ", "")
            parts = [normalize(p).replace(" ", "") for p in s.split("/")]
            if squashed == whole or squashed in parts:
                return s
            if stem != squashed and len(stem) >= SPECIALTY_STEM_MIN and any(p.startswith(stem) for p in parts):
                return s
            score = max(similarity(squashed, x) for x in [whole, *parts])
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
            rank, quality, first_ok = person_match(heard, p.name)
            if rank:
                scored.append((rank, ProviderMatch(p, quality, first_ok)))
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
        1. One of our locations by name, nickname or neighbourhood ("Mission Bay",
           "the Midtown one", "the Hayes Valley one") -> that location.
           A name several locations share ("Mission", "North") -> ambiguous: ask.
        2. A known landmark or neighbourhood ("near Union Square", "Chinatown").
        3. Steps 1-2 again without the word "district" ("the Marina District").
        4. A street from our addresses ("the one on Geary", "near Mission Street").
           When the caller says "street", "avenue" etc., streets are checked first.
        With "near", "closer to" and the like, near=True: rank by distance, don't restrict.
        """
        text = normalize(hint)
        if not text:
            return PlaceMatch(kind="none")
        near = bool(NEAR_PHRASE.search(text))
        core = FILLER_SUFFIX.sub("", FILLER_PREFIX.sub("", text)).strip()
        words = _distinct_words(core, GENERIC_PLACE_WORDS)
        if not words:
            return PlaceMatch(kind="none", label=str(hint))

        said_street = bool(words & STREET_WORDS)
        steps = [
            lambda: self._match_street(words - STREET_WORDS, near),
            lambda: self._match_locations(words, near),
            lambda: self._match_landmarks(core, words),
            lambda: self._match_locations(words - {"district"}, near),
            lambda: self._match_landmarks(core.replace("district", "").strip(), words - {"district"}),
        ]
        if not said_street:
            steps = steps[1:] + steps[:1]
        for step in steps:
            found = step()
            if found:
                return found
        return PlaceMatch(kind="none", label=str(hint))

    def _match_locations(self, words: set, near: bool) -> Optional[PlaceMatch]:
        if not words:
            return None
        hits = []
        for loc in self.locations.values():
            for n in (loc.name, loc.neighbourhood, *loc.also_called):
                if n and _words_fit(words, _distinct_words(n, GENERIC_PLACE_WORDS)):
                    hits.append(loc)
                    break
        if len(hits) > 1:
            # "Mission District" fits Mission District fully but Mission Bay only partly.
            full = [l for l in hits if any(_distinct_words(n, GENERIC_PLACE_WORDS) == words
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

    def _match_landmarks(self, core: str, words: set) -> Optional[PlaceMatch]:
        if not words:
            return None
        best, best_score = None, 0.0
        for name, point in self.landmarks.items():
            score = similarity(core, name)
            if _words_fit(words, _distinct_words(name, GENERIC_PLACE_WORDS)):
                score = max(score, 1.0)
            if score > best_score:
                best, best_score = (name, point), score
        if best and best_score >= LANDMARK_SPELLING:
            return PlaceMatch(kind="landmark", label=best[0], point=best[1], near=True)
        return None

    def _match_street(self, words: set, near: bool) -> Optional[PlaceMatch]:
        if not words:
            return None
        hits = [l for l in self.locations.values() if _words_fit(words, set(l.street.split()))]
        if len(hits) == 1:
            l = hits[0]
            return PlaceMatch(kind="location", label=f"{l.name} ({l.address})", location_ids=[l.id],
                              point=l.point, near=near)
        if hits:
            return PlaceMatch(kind="ambiguous", label=" or ".join(f"{l.name} ({l.address})" for l in hits),
                              location_ids=[l.id for l in hits], near=near)
        return None

    def location_point(self, location_id: str) -> tuple:
        return self.locations[location_id].point
