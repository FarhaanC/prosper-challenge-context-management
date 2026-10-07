"""Round 3, spec change 4 "Places". Expected answers come from the spec text,
catalog.json addresses and location_extras.json."""

import pytest

from clinic import Preferences, find_options
from conftest import NOW, new_caller, returning
from reference import SPECIALTIES

ALL = returning(list(SPECIALTIES))


def opts(r):
    return [(o.provider_id, o.location_id, o.start) for o in r.options]


# ---------------------------------------------------------------- spec phrases, one by one
@pytest.mark.parametrize("hint", ["main", "Main", "the main one", "main clinic", "the main location"])
def test_main_is_not_marina_and_not_a_street(catalog, hint):
    m = catalog.resolve_place(hint)
    assert "loc_003" not in m.location_ids and m.kind not in ("location", "ambiguous"), m


@pytest.mark.parametrize("hint", ["none", "None", "anywhere", "no preference", "No preference", "don't mind",
                                  "Anywhere", "  anywhere  "])
def test_no_preference_words_are_any(catalog, schedule, hint):
    m = catalog.resolve_place(hint)
    assert m.kind == "any" and not m.location_ids, (hint, m)
    r = find_options(catalog, schedule, ALL, "appt_002", Preferences(location_hint=hint), NOW)
    assert not r.notes and opts(r) == opts(find_options(catalog, schedule, ALL, "appt_002", Preferences(), NOW))


@pytest.mark.parametrize("hint", ["I don't mind", "anywhere is fine", "doesn't matter", "wherever"])
def test_my_own_no_preference_phrasings(catalog, hint):
    """My own realistic phrasings (not listed in the spec)."""
    assert catalog.resolve_place(hint).kind == "any", hint


def test_mission_is_ambiguous_union_is_downtown(catalog):
    m = catalog.resolve_place("Mission")
    assert m.kind == "ambiguous" and set(m.location_ids) == {"loc_000", "loc_001"}
    m = catalog.resolve_place("Union")
    assert (m.kind, m.location_ids) == ("location", ["loc_004"])


@pytest.mark.parametrize("hint", ["Bay", "Valley", "Gate", "Square", "the Bay", "Gate Park", "Square one",
                                  "Park", "Heights", "Hill", "Beach", "Health Center", "the clinic", "Center"])
def test_partial_words_pick_nothing(catalog, hint):
    m = catalog.resolve_place(hint)
    assert m.kind in ("none", "any") and not m.location_ids and m.point is None, (hint, m)


@pytest.mark.parametrize("hint,ids", [
    ("Mission Street", ["loc_002"]), ("Mission St", ["loc_002"]), ("Mission St.", ["loc_002"]),
    ("on Main", ["loc_000"]), ("the one on Main", ["loc_000"]), ("Main Street", ["loc_000"]),
    ("the one on Mission", ["loc_002"]),
])
def test_streets_with_a_street_word_or_on(catalog, hint, ids):
    m = catalog.resolve_place(hint)
    assert m.location_ids == ids and m.kind == "location", (hint, m)


@pytest.mark.parametrize("hint,ids", [("Geary Blvd", {"loc_004", "loc_006"}), ("the one on Geary", {"loc_004", "loc_006"}),
                                      ("Market Street", {"loc_001", "loc_005"}), ("on Bryant", {"loc_003", "loc_007"})])
def test_shared_streets_are_ambiguous(catalog, hint, ids):
    m = catalog.resolve_place(hint)
    assert m.kind == "ambiguous" and set(m.location_ids) == ids, (hint, m)


@pytest.mark.parametrize("hint", ["Marina Boulevard", "Sunset Boulevard", "Union Street", "Union St", "Van Ness Avenue",
                                  "Geary", "Market", "Bryant"])  # "near Market": round 4 change 3, see test_round4_*
def test_streets_not_ours_or_without_a_street_word_are_not_recognised(catalog, hint):
    m = catalog.resolve_place(hint)
    assert m.kind == "none" and not m.location_ids, (hint, m)


@pytest.mark.parametrize("hint,lid", [("4874 Main St", "loc_000"), ("481 Mission St", "loc_002"),
                                      ("2099 Market St", "loc_005"), ("4732 Market Street", "loc_001"),
                                      ("near 481 Mission St", "loc_002"), ("4455 Geary Blvd", "loc_004")])
def test_a_full_address_from_the_catalog_is_recognised(catalog, hint, lid):
    """My own realistic case: a caller reads the address off a letter. Spec: streets from our
    addresses are matched when the caller says a street word, and the house number is the
    most precise thing they could say (it also settles shared streets)."""
    m = catalog.resolve_place(hint)
    assert m.location_ids == [lid], (hint, m)


@pytest.mark.parametrize("hint,ids", [("near Market Street", {"loc_001", "loc_005"}),
                                      ("near the Mission", {"loc_000", "loc_001"}),
                                      ("close to Geary Boulevard", {"loc_004", "loc_006"}),
                                      ("near Mission", {"loc_000", "loc_001"})])
def test_near_an_ambiguous_place_notes_but_does_not_narrow(catalog, schedule, hint, ids):
    """Spec: '"near" plus an ambiguous name gives a place_ambiguous note but does NOT narrow.'"""
    m = catalog.resolve_place(hint)
    assert m.kind == "ambiguous" and set(m.location_ids) == ids and m.near
    for vt in ["appt_002", "appt_027", "appt_017"]:
        base = find_options(catalog, schedule, ALL, vt, Preferences(), NOW)
        r = find_options(catalog, schedule, ALL, vt, Preferences(location_hint=hint), NOW)
        assert [n.kind for n in r.notes] == ["place_ambiguous"], [str(n) for n in r.notes]
        assert opts(r) == opts(base), (vt, hint)


def test_the_one_on_geary_does_narrow_to_both(catalog, schedule):
    r = find_options(catalog, schedule, ALL, "appt_002", Preferences(location_hint="the one on Geary"), NOW)
    assert "place_ambiguous" in [n.kind for n in r.notes]
    assert r.options and {o.location_id for o in r.options} <= {"loc_004", "loc_006"}


@pytest.mark.parametrize("hint,lid", [("on the way to Downtown", "loc_004"), ("on the way to the Midtown one", "loc_005"),
                                      ("on the way to Hayes Valley", "loc_005")])
def test_on_the_way_to_is_near(catalog, hint, lid):
    m = catalog.resolve_place(hint)
    assert m.near and m.point is not None and (m.location_ids in ([lid], [])), (hint, m)


@pytest.mark.parametrize("hint,lid", [("downtown SF", "loc_004"), ("Downtown San Francisco", "loc_004"),
                                      ("the Midtown one in SF", "loc_005"), ("SF Midtown", "loc_005"),
                                      ("mid town", "loc_005"), ("the mid town one", "loc_005"),
                                      ("Mission Bay San Francisco", "loc_000")])
def test_city_words_are_ignored_and_mid_town_fits(catalog, hint, lid):
    m = catalog.resolve_place(hint)
    assert m.location_ids == [lid], (hint, m)


# ---------------------------------------------------------------- my own San Francisco phrasings
@pytest.mark.parametrize("hint,lid", [
    ("the one in the Marina", "loc_003"), ("Inner Richmond", "loc_007"), ("Outer Sunset", "loc_006"),
    ("the Civic Center one", "loc_005"), ("Union Square", "loc_004"), ("Mission Bay area", "loc_000"),
    ("the Mission District", "loc_001"), ("Richmond District", "loc_007"), ("Sunset District", "loc_006"),
    ("Richmund", "loc_007"), ("Dowtown", "loc_004"), ("north beach area", "loc_002"),
    ("the clinic in the Marina", "loc_003"), ("downtown in San Francisco", "loc_004"),
])
def test_realistic_names_of_our_locations(catalog, hint, lid):
    m = catalog.resolve_place(hint)
    assert m.location_ids == [lid] and not m.near, (hint, m)


@pytest.mark.parametrize("hint,label", [("near Chinatown", "Chinatown"), ("SoMa", "SoMa"),
                                        ("Financial District", "Financial District"), ("the Embarcadero", "Embarcadero"),
                                        ("Fisherman's Wharf", "Fisherman's Wharf"), ("the Haight", "Haight-Ashbury"),
                                        ("close to the Castro", "Castro"), ("Pacific Heights", "Pacific Heights"),
                                        ("near Nob Hill", "Nob Hill"), ("Dogpatch", "Dogpatch"), ("Bay View", "Bayview"),
                                        ("the Presidio", "Presidio"), ("near Golden Gate Park", "Golden Gate Park")])
def test_realistic_landmarks(catalog, hint, label):
    m = catalog.resolve_place(hint)
    assert m.kind == "landmark" and m.label == label and m.near, (hint, m)


@pytest.mark.parametrize("hint", ["Twin Peaks", "Ocean Beach", "Japantown", "Glen Park", "Cole Valley", "Lower Haight",
                                  "East Bay", "South Bay", "North Bay", "Bay Area", "near the Golden Gate Bridge",
                                  "near Oracle Park", "Daly City", "near me", "the closest one", "Midtown Manhattan",
                                  "the hospital", "Sunset Boulevard", "Richmond Virginia", "Mission Viejo", "Noe Street",
                                  "SF", "San Francisco", "the city"])
def test_places_that_must_not_pick_a_location(catalog, hint):
    m = catalog.resolve_place(hint)
    assert not m.location_ids and m.kind in ("none", "any"), (hint, m)


@pytest.mark.parametrize("hint", ["the Midtown one", "Mission Bay", "the one on Main", "Union Square", "the Sunset one"])
def test_named_place_restricts_options_when_possible(catalog, schedule, hint):
    lid = catalog.resolve_place(hint).location_ids[0]
    r = find_options(catalog, schedule, ALL, "appt_002", Preferences(location_hint=hint), NOW)
    from round2_reference import universe
    if any(s[1] == lid for s in universe(schedule, False, list(SPECIALTIES), "appt_002")):
        assert r.options and all(o.location_id == lid for o in r.options), (hint, [o.location_name for o in r.options])
    else:
        assert "wish_impossible" in [n.kind for n in r.notes]


def test_unknown_place_note_and_options_kept(catalog, schedule):
    for hint in ["the main one", "Marina Boulevard", "Glen Park"]:
        r = find_options(catalog, schedule, new_caller(), "appt_027", Preferences(location_hint=hint), NOW)
        assert [n.kind for n in r.notes] == ["place_unknown"] and r.options, hint
        assert hint in r.notes[0].say
