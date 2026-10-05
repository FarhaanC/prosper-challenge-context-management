"""The clinic catalog, held by code (never pasted whole into the AI's instructions).

Loads the given `catalog.json` untouched, plus our own fake map data
(`location_extras.json`), and answers small questions about it:

- the list of specialties, and the visit types inside one specialty
- doctors matching a (possibly misheard) name: always ALL matches, because
  names repeat (two Dr. Maria Garcias)
- which location or landmark a caller means by "near Downtown" / "the Mission one"
- distances between places
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .fuzzy import normalize, person_name_score, similarity

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# Words that appear in many location names and so don't help tell them apart.
GENERIC_PLACE_WORDS = {
    "health", "center", "centre", "clinic", "medical", "group", "family",
    "specialty", "care", "community", "the", "one", "office", "location",
    "hospital", "place", "site", "branch",
}
# Words callers wrap around a place: "near", "close to", "the ... area".
PLACE_PREFIX = re.compile(
    r"^(?:(?:somewhere|anywhere|something|one)\s+)?"
    r"(?:(?:near|nearby|close to|closest to|around|in|at|by|next to|not far from)\s+)?(?:the\s+)?"
)
NEAR_WORDS = re.compile(r"\b(near|nearby|close to|closest to|around|next to|not far from|by)\b")
PLACE_SUFFIX = re.compile(r"\s+(?:area|side|neighbou?rhood|one|location|clinic|office)$")


@dataclass(frozen=True)
class Location:
    id: str
    name: str
    address: str
    city: str
    phone: str
    hours: str
    capabilities: tuple
    neighbourhood: str = ""
    also_called: tuple = ()
    lat: float = 0.0
    lon: float = 0.0


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

    @property
    def display(self) -> str:
        return f"{self.name}, {self.title} ({self.specialty})"


@dataclass(frozen=True)
class VisitType:
    id: str
    name: str
    specialty: str
    duration_min: int
    requires_referral: bool
    new_patients_allowed: bool
    required_capability: Optional[str] = None


@dataclass
class PlaceMatch:
    """What a caller's place words resolved to."""

    kind: str  # "location" | "landmark" | "ambiguous" | "none"
    label: str = ""
    location_ids: list = field(default_factory=list)  # one if kind=location, several if ambiguous
    point: Optional[tuple] = None  # (lat, lon) to measure distance from
    near: bool = False  # caller said "near X" (rank by distance) rather than "the X one" (only X)


def distance_miles(a: tuple, b: tuple) -> float:
    """Straight-line distance between two (lat, lon) points."""
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 3958.8 * 2 * math.asin(math.sqrt(h))


class Catalog:
    def __init__(self, raw: dict, extras: Optional[dict] = None):
        extras = extras or {"locations": {}, "landmarks": {}}
        self.policies: list = list(raw.get("policies", []))

        self.locations: dict = {}
        for l in raw["locations"]:
            x = extras["locations"].get(l["id"], {})
            self.locations[l["id"]] = Location(
                id=l["id"], name=l["name"], address=l["address"], city=l["city"],
                phone=l["phone"], hours=l["hours"], capabilities=tuple(l.get("capabilities", [])),
                neighbourhood=x.get("neighbourhood", ""), also_called=tuple(x.get("also_called", [])),
                lat=x.get("lat", 0.0), lon=x.get("lon", 0.0),
            )
        self.providers: dict = {
            p["id"]: Provider(
                id=p["id"], name=p["name"], title=p["title"], specialty=p["specialty"],
                location_ids=tuple(p["location_ids"]), accepting_new_patients=p["accepting_new_patients"],
                languages=tuple(p["languages"]), appointment_type_ids=tuple(p["appointment_type_ids"]),
            )
            for p in raw["providers"]
        }
        self.visit_types: dict = {
            a["id"]: VisitType(
                id=a["id"], name=a["name"], specialty=a["specialty"], duration_min=a["duration_min"],
                requires_referral=a["requires_referral"], new_patients_allowed=a["new_patients_allowed"],
                required_capability=a.get("required_capability"),
            )
            for a in raw["appointment_types"]
        }
        self.landmarks: dict = {k: tuple(v) for k, v in extras.get("landmarks", {}).items()}

        # Indexes built once, so lookups stay fast as the catalog grows.
        self._providers_for_type: dict = {vt: [] for vt in self.visit_types}
        for p in self.providers.values():
            for vt in p.appointment_type_ids:
                self._providers_for_type.setdefault(vt, []).append(p)
        self._types_by_specialty: dict = {}
        for vt in self.visit_types.values():
            self._types_by_specialty.setdefault(vt.specialty, []).append(vt)

    # ---- loading -----------------------------------------------------------
    @classmethod
    def load(cls, data_dir: Path = DATA_DIR) -> "Catalog":
        data_dir = Path(data_dir)
        raw = json.loads((data_dir / "catalog.json").read_text(encoding="utf-8"))
        extras_path = data_dir / "location_extras.json"
        extras = json.loads(extras_path.read_text(encoding="utf-8")) if extras_path.exists() else None
        return cls(raw, extras)

    # ---- visit types -------------------------------------------------------
    def specialties(self) -> list:
        return sorted(self._types_by_specialty)

    def match_specialty(self, text: str) -> Optional[str]:
        """Map the AI's specialty wording ("OBGYN", "ob-gyn") to the catalog's name."""
        n = normalize(text).replace(" ", "")
        best, best_score = None, 0.0
        for s in self.specialties():
            sn = normalize(s).replace(" ", "")
            score = 1.0 if sn == n else similarity(sn, n)
            if score > best_score:
                best, best_score = s, score
        return best if best_score >= 0.85 else None

    def visit_types_in(self, specialty: str) -> list:
        return list(self._types_by_specialty.get(specialty, []))

    def providers_offering(self, visit_type_id: str) -> list:
        return list(self._providers_for_type.get(visit_type_id, []))

    def find_visit_types_by_name(self, text: str, limit: int = 3) -> list:
        """For answering questions ("does a knee MRI need a referral?"), not for booking."""
        q = set(normalize(text).split())
        scored = []
        for vt in self.visit_types.values():
            words = set(normalize(vt.name).split())
            overlap = len(q & words) / len(q) if q else 0
            sim = similarity(text, vt.name)
            score = max(overlap, sim)
            if overlap >= 0.5 or sim >= 0.7:
                scored.append((score, vt))
        scored.sort(key=lambda s: -s[0])
        return [vt for _, vt in scored[:limit]]

    # ---- doctors -----------------------------------------------------------
    def find_providers_by_name(self, heard: str) -> list:
        """ALL doctors that match the heard name, best matches first.

        Duplicate names are returned together on purpose, so the agent can ask
        "which one?" instead of guessing.
        """
        scored = [(person_name_score(heard, p.name), p) for p in self.providers.values()]
        scored = [(s, p) for s, p in scored if s >= 0.5]
        if not scored:
            return []
        top = max(s for s, _ in scored)
        # Keep everyone in the best tier (e.g. all exact "Garcia"s), not fuzzier ones.
        return [p for s, p in sorted(scored, key=lambda x: -x[0]) if s >= top - 0.01]

    # ---- places ------------------------------------------------------------
    def resolve_place(self, hint: str) -> PlaceMatch:
        """Work out what place a caller means.

        - One of our locations by name ("Mission Bay", "the Midtown one") -> that location
          ("near Downtown" also resolves to it, but with near=True: rank by distance, don't restrict)
        - A name shared by several of our locations ("Mission", "North") -> ambiguous, ask
        - A known neighbourhood or landmark ("near Union Square") -> a point to rank by distance
        """
        h = normalize(hint)
        near = bool(NEAR_WORDS.search(h))
        h = PLACE_SUFFIX.sub("", PLACE_PREFIX.sub("", h)).strip()
        if not h:
            return PlaceMatch(kind="none")
        words = set(h.split()) - GENERIC_PLACE_WORDS

        # 1) Our own locations, by the distinctive words of their name or nickname.
        hits = []
        for loc in self.locations.values():
            names = [loc.name, *loc.also_called]
            for n in names:
                nn = normalize(n)
                distinct = set(nn.split()) - GENERIC_PLACE_WORDS
                if nn == h or (words and words <= distinct):
                    hits.append(loc)
                    break
        if len(hits) == 1:
            loc = hits[0]
            return PlaceMatch(kind="location", label=loc.name, location_ids=[loc.id], point=(loc.lat, loc.lon), near=near)
        if len(hits) > 1:
            exact = [l for l in hits if normalize(l.name) == h]
            if len(exact) == 1:
                l = exact[0]
                return PlaceMatch(kind="location", label=l.name, location_ids=[l.id], point=(l.lat, l.lon), near=near)
            return PlaceMatch(kind="ambiguous", label=hint, location_ids=[l.id for l in hits], near=near)

        # 2) Landmarks and neighbourhoods.
        best, best_score = None, 0.0
        for name, point in self.landmarks.items():
            score = similarity(h, name)
            if words and words <= set(normalize(name).split()):
                score = max(score, 0.9)
            if score > best_score:
                best, best_score = (name, point), score
        if best and best_score >= 0.75:
            return PlaceMatch(kind="landmark", label=best[0], point=best[1], near=True)
        return PlaceMatch(kind="none", label=hint)

    def location_point(self, location_id: str) -> tuple:
        loc = self.locations[location_id]
        return (loc.lat, loc.lon)
