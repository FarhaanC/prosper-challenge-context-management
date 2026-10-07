"""Places (decision 24, as changed by round 7): the AI passes a place NAME plus near
yes/no. near=False restricts to that place; near=True ranks; shared names are
ambiguous; unknown places are reported, not guessed."""

import pytest


@pytest.mark.parametrize("hint,loc", [
    # round 7: "the X one", "the downtown clinic", "the Downtown location" are phrases, not
    # names; the AI now passes the bare name ("Midtown", "Downtown", "Mission District").
    ("Midtown", "loc_005"), ("Midtown Medical Group", "loc_005"),
    ("midtown!!", "loc_005"), ("Downtown", "loc_004"), ("downtown", "loc_004"),
    ("Mission Bay", "loc_000"), ("Mission District", "loc_001"), ("Mission District Family Clinic", "loc_001"),
    ("North Beach", "loc_002"), ("North Gate", "loc_003"), ("Sunset", "loc_006"), ("Richmond", "loc_007"),
    ("Union Square", "loc_004"), ("Civic Center", "loc_005"), ("Downtown Health Center", "loc_004"),
    ("SUNSET COMMUNITY CLINIC", "loc_006"), ("Outer Sunset", "loc_006"),
])
def test_named_location_restricts(catalog, hint, loc):
    m = catalog.resolve_place(hint)
    assert m.kind == "location" and m.location_ids == [loc] and m.near is False


# round 7: what the caller said ("near Downtown", "close to Downtown", "around Midtown",
# "not far from Richmond", "by the Sunset", "somewhere near downtown") becomes the name plus near=True.
@pytest.mark.parametrize("hint,loc", [
    ("Downtown", "loc_004"), ("Midtown", "loc_005"), ("Union Square", "loc_004"), ("Richmond", "loc_007"),
    ("the Sunset", "loc_006"), ("downtown", "loc_004"),
])
def test_near_location(catalog, hint, loc):
    m = catalog.resolve_place(hint, near=True)
    assert m.kind == "location" and m.location_ids == [loc] and m.near is True


@pytest.mark.parametrize("hint", ["Downtown", "downtown", "DOWNTOWN"])
def test_everyday_near_phrasings(catalog, hint):
    """'Closer to downtown' is the exact phrase from the baseline call (case 4). In round 7
    the AI hears it and passes "Downtown" with near=True; the code must rank by distance."""
    m = catalog.resolve_place(hint, near=True)
    assert m.point is not None and m.near is True
    assert m.kind == "location" and m.location_ids == ["loc_004"]


@pytest.mark.parametrize("hint,near,locs", [
    ("Mission", False, {"loc_000", "loc_001"}), ("the Mission", False, {"loc_000", "loc_001"}),
    ("North", False, {"loc_002", "loc_003"}), ("Mission", True, {"loc_000", "loc_001"}),
])
def test_ambiguous(catalog, hint, near, locs):
    m = catalog.resolve_place(hint, near=near)
    assert m.kind == "ambiguous" and set(m.location_ids) == locs and m.near is near


@pytest.mark.parametrize("hint", ["Chinatown", "Financial District", "Castro",
                                  "Golden Gate Park", "Fisherman's Wharf", "fishermans wharf", "Noe Valley"])
@pytest.mark.parametrize("near", [False, True])
def test_landmarks(catalog, hint, near):
    m = catalog.resolve_place(hint, near=near)   # a landmark is always "near": it isn't a clinic
    assert m.kind == "landmark" and m.point is not None and m.near is True


@pytest.mark.parametrize("hint", ["Narnia", "the moon", "asdfgh", "", "   ", None, "Oakland", "Paris", "???"])
def test_nonsense_or_unknown_not_guessed(catalog, hint):
    m = catalog.resolve_place(hint)
    assert m.kind == "none"


@pytest.mark.parametrize("hint", ["health center", "the clinic"])
def test_generic_words_not_guessed(catalog, hint):
    m = catalog.resolve_place(hint)
    assert m.kind in ("none", "ambiguous")
