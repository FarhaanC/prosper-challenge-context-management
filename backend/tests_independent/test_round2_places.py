"""Round 2, spec change 3: places. Expected answers come from the spec text,
catalog.json addresses and location_extras.json."""

import json
import math

import pytest

from clinic import Preferences, find_options
from conftest import NOW, new_caller, returning
from reference import DATA, LOC, SPECIALTIES

EXTRAS = json.loads((DATA / "location_extras.json").read_text())


def pt(lid):
    x = EXTRAS["locations"][lid]
    return (x["lat"], x["lon"])


def miles(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 3958.8 * 2 * math.asin(math.sqrt(h))


# ---------------------------------------------------------------- spec phrasings
NEAR_WORDS = ["near", "nearby", "close to", "closer to", "closest to", "around", "next to", "not far from", "by",
              "the one near", "on the way to"]


@pytest.mark.parametrize("word", NEAR_WORDS)
def test_every_near_phrasing_ranks_without_restricting(catalog, word):
    m = catalog.resolve_place(f"{word} Downtown")
    assert m.kind in ("location", "landmark") and m.near is True, (word, m)
    assert m.point is not None


@pytest.mark.parametrize("word", NEAR_WORDS)
def test_every_near_phrasing_with_a_landmark(catalog, word):
    m = catalog.resolve_place(f"{word} Chinatown")
    assert m.kind == "landmark" and m.near is True and m.label == "Chinatown", (word, m)


@pytest.mark.parametrize("hint,lid", [
    ("the Hayes Valley one", "loc_005"), ("the Marina District", "loc_003"), ("Richmond District", "loc_007"),
    ("the Midtown one", "loc_005"), ("the Mission District one", "loc_001"), ("Mission Bay", "loc_000"),
    ("the Marina one", "loc_003"), ("the Sunset one", "loc_006"), ("North Beach", "loc_002"),
    ("Downtown Health Center", "loc_004"), ("the downtown one", "loc_004"),
])
def test_naming_one_of_our_locations_restricts(catalog, hint, lid):
    m = catalog.resolve_place(hint)
    assert (m.kind, m.location_ids, m.near) == ("location", [lid], False), (hint, m)


def test_near_a_neighbourhood_ranks(catalog):
    m = catalog.resolve_place("near Hayes Valley")
    assert m.near is True and m.point is not None


def test_castro_district_is_the_landmark(catalog):
    m = catalog.resolve_place("Castro District")
    assert m.kind == "landmark" and m.label == "Castro"


@pytest.mark.parametrize("hint", ["near Mission Street", "the one on Mission Street", "Mission Street"])
def test_mission_street_is_north_beach_specialty_center(catalog, hint):
    m = catalog.resolve_place(hint)
    assert m.location_ids == ["loc_002"], m  # 481 Mission St
    assert m.near == hint.startswith("near")


@pytest.mark.parametrize("hint,ids", [
    ("the one on Geary", {"loc_004", "loc_006"}), ("Geary Boulevard", {"loc_004", "loc_006"}),
    ("the one on Market", {"loc_001", "loc_005"}), ("the one on Bryant Street", {"loc_003", "loc_007"}),
    ("the Mission", {"loc_000", "loc_001"}), ("Mission", {"loc_000", "loc_001"}),
    ("the North one", {"loc_002", "loc_003"}),
])
def test_ambiguous_places(catalog, hint, ids):
    m = catalog.resolve_place(hint)
    assert m.kind == "ambiguous" and set(m.location_ids) == ids, m


@pytest.mark.parametrize("hint,lid", [("the one on Main Street", "loc_000"), ("Main St", "loc_000"),
                                      ("the one on Main", "loc_000"), ("on Main", "loc_000")])
def test_main_street_is_mission_bay(catalog, hint, lid):
    """4874 Main St is Mission Bay Health Center (catalog.json)."""
    m = catalog.resolve_place(hint)
    assert m.location_ids == [lid], (hint, m)


def test_the_mission_nickname_was_removed_from_extras():
    for x in EXTRAS["locations"].values():
        assert "The Mission" not in x["also_called"] and "the Mission" not in x["also_called"]


# ---------------------------------------------------------------- must NOT be guessed (decision 24)
@pytest.mark.parametrize("hint,wrong", [
    ("Marina Boulevard", "loc_000"),   # the Marina is North Gate's neighbourhood, not Main St
    ("the one on Main", "loc_003"),    # 'Main' is not 'Marina'
    ("Bay Area", "loc_000"),           # the whole region, not Mission Bay
])
def test_no_wrong_location_guessed(catalog, hint, wrong):
    m = catalog.resolve_place(hint)
    assert wrong not in m.location_ids, (hint, m)


@pytest.mark.parametrize("hint,wrong", [("Glen Park", "Golden Gate Park"), ("near Cole Valley", "Noe Valley")])
def test_no_wrong_landmark_guessed(catalog, hint, wrong):
    """Real San Francisco neighbourhoods we have no data for must be reported as unknown,
    not swapped for a different place miles away."""
    m = catalog.resolve_place(hint)
    assert m.label != wrong, (hint, m)


@pytest.mark.parametrize("hint", ["Oakland", "Mars", "Daly City", "Downtown Oakland", "Midtown Manhattan",
                                  "Sunset Boulevard", "near me", "the closest one", "Twin Peaks",
                                  "Richmond Virginia"])
def test_unknown_places_are_none(catalog, hint):
    assert catalog.resolve_place(hint).kind == "none", (hint, catalog.resolve_place(hint))


@pytest.mark.parametrize("hint", ["downtown SF", "downtown San Francisco"])
def test_realistic_downtown_phrasings(catalog, hint):
    """My own realistic phrasings: a caller adds the city name."""
    m = catalog.resolve_place(hint)
    assert m.kind in ("location", "landmark"), (hint, m)


# ---------------------------------------------------------------- through find_options
@pytest.mark.parametrize("hint", ["", "   ", "\t"])
def test_blank_place_is_no_wish_no_note(catalog, schedule, hint):
    r = find_options(catalog, schedule, new_caller(), "appt_027", Preferences(location_hint=hint), NOW)
    assert r.options and not r.notes


def test_the_mission_gives_ambiguous_note(catalog, schedule):
    r = find_options(catalog, schedule, new_caller(), "appt_027", Preferences(location_hint="the Mission"), NOW)
    kinds = [n.kind for n in r.notes]
    assert "place_ambiguous" in kinds
    amb = next(n for n in r.notes if n.kind == "place_ambiguous")
    assert "Mission Bay" in amb.say and "Mission District" in amb.say


def test_unknown_place_note(catalog, schedule):
    r = find_options(catalog, schedule, new_caller(), "appt_027", Preferences(location_hint="Mars"), NOW)
    assert [n.kind for n in r.notes] == ["place_unknown"] and r.options


@pytest.mark.parametrize("hint,origin", [("near Hayes Valley", "loc_005"), ("closer to downtown", "loc_004"),
                                         ("on the way to Downtown", "loc_004")])
def test_near_ranks_by_distance_and_keeps_other_places(catalog, schedule, hint, origin):
    r = find_options(catalog, schedule, returning(list(SPECIALTIES)), "appt_027",
                     Preferences(location_hint=hint), NOW)
    assert r.options and not r.notes, [str(n) for n in r.notes]
    d = [miles(pt(origin), pt(o.location_id)) for o in r.options]
    assert d == sorted(d), [(o.location_name, round(x, 2)) for o, x in zip(r.options, d)]
    assert len({o.location_id for o in r.options}) > 1  # near does not restrict


def test_soonest_ranks_by_time_even_with_a_named_place(catalog, schedule):
    for hint in ["near Downtown", "the Midtown one", "near Chinatown"]:
        r = find_options(catalog, schedule, returning(list(SPECIALTIES)), "appt_002",
                         Preferences(location_hint=hint, soonest=True), NOW)
        starts = [o.start for o in r.options]
        assert starts == sorted(starts), hint
