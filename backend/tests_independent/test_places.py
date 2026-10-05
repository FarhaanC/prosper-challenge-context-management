"""Places (decision 24): 'near X' ranks; 'the X one' restricts; shared names are
ambiguous; unknown places are reported, not guessed."""

import pytest


@pytest.mark.parametrize("hint,loc", [
    ("Midtown", "loc_005"), ("the Midtown one", "loc_005"), ("Midtown Medical Group", "loc_005"),
    ("midtown!!", "loc_005"), ("Downtown", "loc_004"), ("the downtown clinic", "loc_004"),
    ("Mission Bay", "loc_000"), ("the Mission District one", "loc_001"), ("Mission District Family Clinic", "loc_001"),
    ("North Beach", "loc_002"), ("North Gate", "loc_003"), ("Sunset", "loc_006"), ("Richmond", "loc_007"),
    ("Union Square", "loc_004"), ("Civic Center", "loc_005"), ("the Downtown location", "loc_004"),
    ("SUNSET COMMUNITY CLINIC", "loc_006"), ("Outer Sunset", "loc_006"),
])
def test_named_location_restricts(catalog, hint, loc):
    m = catalog.resolve_place(hint)
    assert m.kind == "location" and m.location_ids == [loc] and m.near is False


@pytest.mark.parametrize("hint,loc", [
    ("near Downtown", "loc_004"), ("close to Downtown", "loc_004"), ("around Midtown", "loc_005"),
    ("next to Union Square", "loc_004"), ("not far from Richmond", "loc_007"), ("by the Sunset", "loc_006"),
    ("somewhere near downtown", "loc_004"), ("near downtown, please", None),
])
def test_near_location(catalog, hint, loc):
    m = catalog.resolve_place(hint)
    if loc is None:
        return  # just must not crash
    assert m.kind == "location" and m.location_ids == [loc] and m.near is True


@pytest.mark.parametrize("hint", ["the one near Downtown", "closer to Downtown", "closest to downtown"])
def test_everyday_near_phrasings(catalog, hint):
    """'Closer to downtown' is the exact phrase from the baseline call (case 4).
    Decision 24 lists near / close to / ... ; 'closer to' and 'the one near' are the
    same wish in everyday speech, so they should resolve to Downtown with near=True."""
    m = catalog.resolve_place(hint)
    assert m.point is not None and m.near is True
    assert m.kind in ("location", "landmark")
    if m.kind == "location":
        assert m.location_ids == ["loc_004"]


@pytest.mark.parametrize("hint,locs", [
    ("Mission", {"loc_000", "loc_001"}), ("the Mission one", {"loc_000", "loc_001"}),
    ("North", {"loc_002", "loc_003"}), ("near Mission", {"loc_000", "loc_001"}),
])
def test_ambiguous(catalog, hint, locs):
    m = catalog.resolve_place(hint)
    assert m.kind == "ambiguous" and set(m.location_ids) == locs


@pytest.mark.parametrize("hint", ["Chinatown", "near Chinatown", "Financial District", "Castro",
                                  "Golden Gate Park", "Fisherman's Wharf", "fishermans wharf", "Noe Valley"])
def test_landmarks(catalog, hint):
    m = catalog.resolve_place(hint)
    assert m.kind == "landmark" and m.point is not None and m.near is True


@pytest.mark.parametrize("hint", ["Narnia", "the moon", "asdfgh", "", "   ", None, "Oakland", "Paris", "???"])
def test_nonsense_or_unknown_not_guessed(catalog, hint):
    m = catalog.resolve_place(hint)
    assert m.kind == "none"


@pytest.mark.parametrize("hint", ["health center", "the clinic"])
def test_generic_words_not_guessed(catalog, hint):
    m = catalog.resolve_place(hint)
    assert m.kind in ("none", "ambiguous")
