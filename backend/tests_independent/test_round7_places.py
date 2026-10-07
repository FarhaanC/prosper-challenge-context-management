"""Round 7 (spec-changes-round-7.md), section 1: a place is a NAME plus near yes/no.

- near=False: that place only (restrict). near=True: rank by distance, don't restrict.
- A landmark is always "near". An ambiguous name with near=True gives the note but
  doesn't narrow. A house number we don't have means "somewhere on that street".
- Phrases are no longer read: each listed phrase form is "not recognised" (place_unknown).
- A bare street name (no street word) is not a street.
- near with any other kind of change is refused, changing nothing.
- When a chosen place is carried over after another change, near goes back to False.
- The card summary shows "place: near Downtown" when near is set.

Expected answers come from the spec text, catalog.json and location_extras.json (read
here directly); the module's fake calendar is used only as the source of open times.
"""

import json
import math

import pytest

from clinic import BookingCard, Choices, Preferences, find_options
from conftest import NOW, new_caller, returning
from reference import DATA, LOC, SPECIALTIES, VT, ref_bookable, ref_pairs

EXTRAS = json.loads((DATA / "location_extras.json").read_text())
ALL = returning(list(SPECIALTIES))
UNKNOWN_NOTE = ("I don't recognise the place '{}'. Pass just a place name: a neighbourhood, a street or one of "
                "our location names.")

# ---- every name of each of our locations, straight from the data files
LOCATION_NAMES = sorted({(LOC[lid]["name"], lid) for lid in LOC}
                        | {(x["neighbourhood"], lid) for lid, x in EXTRAS["locations"].items() if x["neighbourhood"]}
                        | {(a, lid) for lid, x in EXTRAS["locations"].items() for a in x["also_called"]})
_location_words = {n.lower() for n, _ in LOCATION_NAMES}
LANDMARKS_ONLY = sorted(n for n in EXTRAS["landmarks"] if n.lower() not in _location_words)


def street_of(address):
    return address.split()[1]           # "4455 Geary Blvd" -> "Geary"


STREETS = {}
for _lid, _l in LOC.items():
    STREETS.setdefault(street_of(_l["address"]), set()).add(_lid)


def miles(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 3958.8 * 2 * math.asin(math.sqrt(h))


def loc_point(lid):
    x = EXTRAS["locations"][lid]
    return (x["lat"], x["lon"])


_SLOTS = {}


def open_pairs(schedule, vt):
    """(doctor, location) pairs a returning patient with every referral can book, with an open time."""
    if vt not in _SLOTS:
        _SLOTS[vt] = {(p, l) for p, l in ref_pairs(False, vt)
                      if schedule.open_slots(p, l, VT[vt]["duration_min"], NOW)}
    return _SLOTS[vt]


def visit_type_at(schedule, lid, few=False):
    """A visit type that can be booked at `lid` AND at two or more other locations, so that
    restricting to `lid` and not restricting give visibly different answers. few=True: one
    where fewer than 3 doctor/location pairs are at `lid`, so 3 options can't all be there."""
    for vt in sorted(VT):
        if not ref_bookable(False, list(SPECIALTIES), vt):
            continue
        pairs = open_pairs(schedule, vt)
        locs = {l for _, l in pairs}
        if lid in locs and len(locs - {lid}) >= 2 and (not few or sum(l == lid for _, l in pairs) < 3):
            return vt
    raise AssertionError(f"fixture: no visit type for {lid}")


def search(catalog, schedule, vt, **prefs):
    return find_options(catalog, schedule, ALL, vt, Preferences(**prefs), NOW)


def ranking_problems(r, point, pairs):
    """near: options ranked by distance from `point`, chosen from ALL valid pairs (not
    restricted): no offered pair is farther than a pair left out (0.1 mile rounding allowed)."""
    out = []
    d = [miles(point, loc_point(o.location_id)) for o in r.options]
    if any(b < a - 0.05 for a, b in zip(d, d[1:])):
        out.append(f"not sorted by distance: {[round(x, 2) for x in d]}")
    offered = {(o.provider_id, o.location_id) for o in r.options}
    left_out = [miles(point, loc_point(l)) for p, l in pairs if (p, l) not in offered]
    if left_out and d and max(d) > min(left_out) + 0.1:
        out.append(f"a closer pair was left out ({min(left_out):.2f} < {max(d):.2f})")
    if len(pairs) >= 3 and len(offered) < 3:
        out.append("the same doctor/location repeated although other pairs exist")
    return out


# =============================================================== names of our locations
@pytest.mark.parametrize("name,lid", LOCATION_NAMES)
def test_every_location_name_with_near_false_restricts(catalog, schedule, name, lid):
    m = catalog.resolve_place(name, near=False)
    assert (m.kind, m.location_ids, m.near) == ("location", [lid], False), (name, m)
    vt = visit_type_at(schedule, lid)
    r = search(catalog, schedule, vt, location_hint=name)
    assert r.options and not r.notes, (name, [n.say for n in r.notes])
    assert {o.location_id for o in r.options} == {lid}, (name, [o.location_name for o in r.options])


@pytest.mark.parametrize("name,lid", LOCATION_NAMES)
def test_every_location_name_with_near_true_ranks_and_does_not_restrict(catalog, schedule, name, lid):
    m = catalog.resolve_place(name, near=True)
    assert (m.kind, m.location_ids, m.near) == ("location", [lid], True), (name, m)
    assert m.point == pytest.approx(loc_point(lid))
    vt = visit_type_at(schedule, lid, few=True)
    r = search(catalog, schedule, vt, location_hint=name, near=True)
    assert r.options and not r.notes, (name, [n.say for n in r.notes])
    pairs = open_pairs(schedule, vt)
    assert r.options[0].location_id == lid      # the place itself is closest
    assert not ranking_problems(r, loc_point(lid), pairs), (name, ranking_problems(r, loc_point(lid), pairs))
    assert {o.location_id for o in r.options} != {lid}, "near must not restrict to that place"
    restricted = search(catalog, schedule, vt, location_hint=name, near=False)
    assert {o.location_id for o in restricted.options} == {lid}   # the same name without near does


@pytest.mark.parametrize("name", LANDMARKS_ONLY)
@pytest.mark.parametrize("near", [False, True])
def test_every_landmark_is_always_near(catalog, schedule, name, near):
    m = catalog.resolve_place(name, near=near)
    assert (m.kind, m.location_ids, m.near) == ("landmark", [], True), (name, m)
    point = tuple(EXTRAS["landmarks"][name])
    assert m.point == pytest.approx(point)
    vt = "appt_002"
    r = search(catalog, schedule, vt, location_hint=name, near=near)
    assert r.options and not r.notes, (name, [n.say for n in r.notes])
    assert not ranking_problems(r, point, open_pairs(schedule, vt)), (name, ranking_problems(r, point, open_pairs(schedule, vt)))


@pytest.mark.parametrize("name,lid", [("Richmund", "loc_007"), ("mid town", "loc_005"), ("Marina District", "loc_003"),
                                      ("Downtown SF", "loc_004"), ("Mission Bay Health Center", "loc_000"),
                                      ("Richmond District", "loc_007"), ("HAYES VALLEY", "loc_005"),
                                      ("Midtown San Francisco", "loc_005"), ("Mision Bay", "loc_000")])
@pytest.mark.parametrize("near", [False, True])
def test_names_are_still_matched_forgivingly(catalog, name, lid, near):
    """s1: spelling, spaces, "District", city words, generic name words."""
    m = catalog.resolve_place(name, near=near)
    assert (m.kind, m.location_ids, m.near) == ("location", [lid], near), (name, m)


@pytest.mark.parametrize("name", ["Marin", "Sunse", "Sunst", "Nort", "Bay", "Valley", "Rich"])
@pytest.mark.parametrize("near", [False, True])
def test_short_words_must_match_exactly(catalog, name, near):
    assert catalog.resolve_place(name, near=near).kind == "none", name


@pytest.mark.parametrize("name,ids", [("Mission", {"loc_000", "loc_001"}), ("North", {"loc_002", "loc_003"}),
                                      ("the Mission", {"loc_000", "loc_001"}),
                                      ("Geary Street", STREETS["Geary"]), ("Market Street", STREETS["Market"]),
                                      ("Bryant Street", STREETS["Bryant"])])
def test_a_name_several_places_share_is_ambiguous_and_narrows_without_near(catalog, schedule, name, ids):
    m = catalog.resolve_place(name)
    assert m.kind == "ambiguous" and set(m.location_ids) == ids and not m.near, (name, m)
    r = search(catalog, schedule, "appt_002", location_hint=name)
    amb = [n.say for n in r.notes if n.kind == "place_ambiguous"]
    assert len(amb) == 1 and all(LOC[l]["name"] in amb[0] for l in ids), [n.say for n in r.notes]
    assert r.options and {o.location_id for o in r.options} <= ids


@pytest.mark.parametrize("name,ids", [("Mission", {"loc_000", "loc_001"}), ("North", {"loc_002", "loc_003"}),
                                      ("Geary Street", STREETS["Geary"]), ("Market St", STREETS["Market"]),
                                      ("Bryant Street", STREETS["Bryant"])])
def test_a_shared_name_with_near_gives_the_note_but_does_not_narrow(catalog, schedule, name, ids):
    m = catalog.resolve_place(name, near=True)
    assert m.kind == "ambiguous" and set(m.location_ids) == ids and m.near, (name, m)
    for vt in ["appt_002", "appt_027"]:
        base = search(catalog, schedule, vt)
        r = search(catalog, schedule, vt, location_hint=name, near=True)
        assert [n.kind for n in r.notes] == ["place_ambiguous"], [n.say for n in r.notes]
        assert [(o.provider_id, o.location_id, o.start) for o in r.options] == \
               [(o.provider_id, o.location_id, o.start) for o in base.options]


# =============================================================== streets and house numbers
STREET_FORMS = ["{s} Street", "{s} St", "{s} st.", "{s} Boulevard", "{s} Blvd", "{s} Avenue", "{s} Road"]


@pytest.mark.parametrize("street", sorted(STREETS))
@pytest.mark.parametrize("form", STREET_FORMS)
@pytest.mark.parametrize("near", [False, True])
def test_a_street_with_a_street_word_is_one_of_ours(catalog, street, form, near):
    m = catalog.resolve_place(form.format(s=street), near=near)
    want = STREETS[street]
    assert set(m.location_ids) == want and m.near is near, (form.format(s=street), m)
    assert m.kind == ("location" if len(want) == 1 else "ambiguous")


@pytest.mark.parametrize("street", sorted(STREETS) + ["main", "GEARY"])
@pytest.mark.parametrize("near", [False, True])
def test_a_bare_street_name_is_not_a_street(catalog, schedule, street, near):
    """s1: "A bare street name without a street word ('Geary', 'main') is not a street."
    ("Mission" alone is a location name shared by two clinics, so it's ambiguous instead.)"""
    m = catalog.resolve_place(street, near=near)
    if street == "Mission":
        assert m.kind == "ambiguous" and set(m.location_ids) == {"loc_000", "loc_001"}
        return
    assert m.kind == "none" and not m.location_ids, (street, m)
    r = search(catalog, schedule, "appt_002", location_hint=street, near=near)
    assert [(n.kind, n.say) for n in r.notes] == [("place_unknown", UNKNOWN_NOTE.format(street))]


@pytest.mark.parametrize("lid", sorted(LOC))
@pytest.mark.parametrize("near", [False, True])
def test_a_house_number_we_have_picks_that_clinic(catalog, schedule, lid, near):
    address = LOC[lid]["address"]
    number, street = address.split()[0], street_of(address)
    for said in (address, f"{number} {street} Street", f"{number} {street.lower()} st"):
        m = catalog.resolve_place(said, near=near)
        assert (m.kind, m.location_ids, m.near) == ("location", [lid], near), (said, m)
    if not near:
        vt = visit_type_at(schedule, lid)
        r = search(catalog, schedule, vt, location_hint=address)
        assert r.options and {o.location_id for o in r.options} == {lid} and not r.notes


@pytest.mark.parametrize("street", sorted(s for s in STREETS if len(STREETS[s]) > 1))
@pytest.mark.parametrize("near", [False, True])
def test_a_house_number_we_do_not_have_is_somewhere_on_that_street(catalog, schedule, street, near):
    """s1: "ambiguous, near, no narrowing", whatever near the AI passed."""
    said = f"9999 {street} Street"
    m = catalog.resolve_place(said, near=near)
    assert m.kind == "ambiguous" and set(m.location_ids) == STREETS[street] and m.near is True, m
    base = search(catalog, schedule, "appt_002")
    r = search(catalog, schedule, "appt_002", location_hint=said, near=near)
    assert [n.kind for n in r.notes] == ["place_ambiguous"]
    assert [(o.provider_id, o.location_id, o.start) for o in r.options] == \
           [(o.provider_id, o.location_id, o.start) for o in base.options]


@pytest.mark.parametrize("street", sorted(s for s in STREETS if len(STREETS[s]) == 1))
def test_a_house_number_we_do_not_have_on_a_one_clinic_street_does_not_restrict(catalog, schedule, street):
    """My reading of s1: "somewhere on that street" never restricts to our clinic there."""
    (lid,) = STREETS[street]
    m = catalog.resolve_place(f"9999 {street} Street")
    assert m.near is True and m.location_ids == [lid], m
    vt = visit_type_at(schedule, lid)
    r = search(catalog, schedule, vt, location_hint=f"9999 {street} Street")
    assert not ranking_problems(r, loc_point(lid), open_pairs(schedule, vt))


# =============================================================== phrases are no longer read
PHRASE_FORMS = [
    "near {x}", "closer to {x}", "close to {x}", "next to {x}", "around {x}", "by {x}", "on the way to {x}",
    "the {x} one", "somewhere {x}", "somewhere near {x}",
    "{x} area", "{x} side", "{x} neighbourhood", "{x} neighborhood", "{x} location", "{x} clinic", "{x} office",
    "in {x}", "at {x}", "to {x}", "from {x}", "a {x}", "{x} one", "{x} place", "the one in {x}",
]
PHRASE_NAMES = ["Downtown", "Midtown", "Hayes Valley", "Union Square", "Chinatown", "Richmond"]


@pytest.mark.parametrize("form", PHRASE_FORMS)
@pytest.mark.parametrize("name", PHRASE_NAMES)
def test_each_listed_phrase_form_is_not_recognised(catalog, schedule, form, name):
    said = form.format(x=name)
    for near in (False, True):
        m = catalog.resolve_place(said, near=near)
        assert m.kind == "none" and not m.location_ids and m.point is None, (said, near, m)
    r = search(catalog, schedule, "appt_002", location_hint=said)
    assert [(n.kind, n.say) for n in r.notes] == [("place_unknown", UNKNOWN_NOTE.format(said))]
    base = search(catalog, schedule, "appt_002")
    assert [(o.provider_id, o.start) for o in r.options] == [(o.provider_id, o.start) for o in base.options]


@pytest.mark.parametrize("said", ["the one on Geary", "on Geary", "the one on Main Street", "on Mission Street",
                                  "the one on Market"])
def test_on_a_street_is_not_read(catalog, said):
    """s1: "the one on X", "on X" are no longer read. (The AI passes "Geary Street".)"""
    assert catalog.resolve_place(said).kind == "none", said


@pytest.mark.parametrize("name", ["Downtown", "Union Square"])
def test_not_far_from_is_not_used_as_a_place(catalog, schedule, name):
    """s1 lists "not far from…" as not recognised; the round-6 sentence guard (still in force,
    s4) refuses any place value with "not". Either way it must not become a place wish: the
    search is refused (bad_input) and nothing is narrowed. See the report: spec gap."""
    said = f"not far from {name}"
    assert catalog.resolve_place(said).kind == "none"
    r = search(catalog, schedule, "appt_002", location_hint=said)
    assert not r.options and [n.kind for n in r.notes] == ["bad_input"]


# =============================================================== the card
@pytest.mark.parametrize("what,value", [("doctor", "Dr. Daniel Chen"), ("time", "Thursday"), ("language", "Spanish"),
                                        ("visit_type", "knee MRI"), ("doctor", ""), ("time", "")])
def test_near_with_any_other_kind_of_change_is_refused_and_changes_nothing(catalog, what, value):
    card = BookingCard(caller=new_caller(), preferences=Preferences(location_hint="Midtown", near=True,
                                                                    days=["Monday"], language="Hindi"))
    card.choices = Choices(specialty="Dermatology", visit_type_id="appt_027", provider_id="prov_001",
                           location_id="loc_004", slot=NOW.replace(day=8, hour=10))
    before = card.to_dict()
    with pytest.raises(ValueError):
        card.change_choice(what, value, near=True)
    assert card.to_dict() == before
    with pytest.raises(ValueError):
        card.change_choice("time", days=["Friday"], near=True)
    assert card.to_dict() == before


def _chosen_card(near):
    card = BookingCard(caller=new_caller())
    card.choices = Choices(specialty="Dermatology", visit_type_id="appt_027")
    card.change_choice("location", "Downtown", near=near)
    card.choices.provider_id, card.choices.location_id, card.choices.slot = "prov_001", "loc_004", NOW.replace(day=8, hour=10)
    return card


@pytest.mark.parametrize("change", [("time", "Thursday"), ("doctor", "Dr. Kenji Kim"), ("language", "Spanish"),
                                    ("visit_type", "mole check"), ("turn_down", None)])
def test_near_goes_back_to_false_when_the_chosen_place_is_carried_over(catalog, change):
    card = _chosen_card(near=True)
    assert card.preferences.near is True
    if change[0] == "turn_down":
        card.turn_down_doctors(catalog, current=True)
    else:
        card.change_choice(*change)
    p = card.preferences
    assert (p.preferred_location_id, p.location_hint, p.near) == ("loc_004", "", False), p
    assert "near" not in card.summary(catalog)


def test_a_said_place_keeps_near_when_nothing_was_chosen(catalog):
    """Only a CHOSEN place is carried over (and loses near); a said place stays as said."""
    card = BookingCard(caller=new_caller())
    card.choices = Choices(specialty="Dermatology", visit_type_id="appt_027")
    card.change_choice("location", "Union Square", near=True)
    card.change_choice("time", "Thursday")
    p = card.preferences
    assert (p.location_hint, p.near, p.preferred_location_id) == ("Union Square", True, "")
    assert "place: near Union Square" in card.summary(catalog)


def test_a_new_location_change_sets_near_afresh(catalog):
    card = BookingCard(caller=new_caller())
    card.change_choice("location", "Downtown", near=True)
    card.change_choice("location", "Midtown")
    assert (card.preferences.location_hint, card.preferences.near) == ("Midtown", False)


@pytest.mark.parametrize("value", ["", "   ", "anywhere", "no preference", "I don't mind", "Anywhere"])
def test_near_with_no_place_is_no_wish(catalog, value):
    card = BookingCard(caller=new_caller())
    card.change_choice("location", value, near=True)
    assert (card.preferences.location_hint, card.preferences.near) == ("", False)
    assert "place" not in card.summary(catalog)


@pytest.mark.parametrize("name,near,shown", [("Downtown", True, "place: near Downtown"),
                                             ("Downtown", False, "place: Downtown"),
                                             ("Union Square", True, "place: near Union Square"),
                                             ("Geary Street", True, "place: near Geary Street")])
def test_the_summary_shows_near(catalog, name, near, shown):
    card = BookingCard(caller=new_caller())
    card.change_choice("location", name, near=near)
    line = next(l for l in card.summary(catalog).splitlines() if l.startswith("Caller asked for"))
    assert shown in line and line.count("near") == int(near), line


def test_a_carried_place_reads_as_its_name_without_near(catalog):
    card = _chosen_card(near=True)
    card.change_choice("time", "Friday")
    assert "place: Downtown Health Center" in card.summary(catalog)
