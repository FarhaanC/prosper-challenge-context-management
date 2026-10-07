"""Round 6 (spec-changes-round-6.md), sections 1-4 and 6: plain day/time fields,
"no preference" words in every field, sentences passed as a doctor or place, choosing an
option, and the patient data checks.

Expected answers come from the spec text and the raw data files (reference.py). The
module's fake calendar is used only as the source of open times, as in earlier rounds.
The clock is fixed: Tuesday 6 Oct 2026, 09:00 (conftest.NOW), so the booking window is
6 October to 20 October.
"""

import copy
import json
from datetime import date, datetime, timedelta

import pytest

from clinic import BOOKING, BookingCard, Catalog, CatalogError, Choices, PatientDirectory, Preferences, Schedule, \
    find_options
from conftest import NOW, new_caller
from reference import DATA, LOC, PROV, VT, ref_pairs

RAW = json.loads((DATA / "catalog.json").read_text())
EXTRAS = json.loads((DATA / "location_extras.json").read_text())
SKIN = "appt_027"   # Skin Cancer Screening: 30 minutes, new patients allowed, several doctors
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
FIRST, LAST = NOW.date(), NOW.date() + timedelta(days=14)
WINDOW = [FIRST + timedelta(days=i) for i in range(15)]
DANIEL_CHEN = next(p for p, x in PROV.items() if x["name"] == "Dr. Daniel Chen" and SKIN in x["appointment_type_ids"])


def run(catalog, schedule, prefs, vt=SKIN, now=NOW):
    return find_options(catalog, schedule, new_caller(), vt, prefs, now)


def kinds(r):
    return [n.kind for n in r.notes]


def said(r):
    return [n.say for n in r.notes]


def key(r):
    return [(o.provider_id, o.location_id, o.start) for o in r.options]


def skin_slots(schedule, now=NOW):
    return [(p, l, t) for p, l in sorted(ref_pairs(True, SKIN))
            for t in schedule.open_slots(p, l, VT[SKIN]["duration_min"], now)]


def skin_card(**prefs):
    card = BookingCard(caller=new_caller(), preferences=Preferences(**prefs))
    card.choices = Choices(specialty="Dermatology", visit_type_id=SKIN)
    return card


def refused(r):
    """Spec s1/s3: no options and a bad_input note (only bad_input notes)."""
    return not r.options and bool(r.notes) and set(kinds(r)) == {"bad_input"}


# =========================================================== s1: plain day and time fields
# ---- every accepted day form
WEEKDAY_FORMS = [(w, i) for i, w in enumerate(WEEKDAYS)] + [(w.lower(), i) for i, w in enumerate(WEEKDAYS)] + \
                [(w.upper(), i) for i, w in enumerate(WEEKDAYS)] + [("  Thursday ", 3)] + \
                [(s, i) for i, s in enumerate(["mon", "tue", "wed", "thu", "fri", "sat", "sun"])] + \
                [("Thu", 3), ("THU", 3), ("thurs", 3), ("Thurs", 3)]


@pytest.mark.parametrize("entry,weekday", WEEKDAY_FORMS)
def test_every_weekday_form_is_accepted_and_honoured(catalog, schedule, entry, weekday):
    r = run(catalog, schedule, Preferences(days=[entry]))
    assert "bad_input" not in kinds(r), (entry, said(r))
    open_that_day = [s for s in skin_slots(schedule) if s[2].weekday() == weekday]
    if open_that_day:
        assert r.options and all(o.start.weekday() == weekday for o in r.options), (entry, [o.spoken for o in r.options])
        assert not r.notes
    else:  # a weekend day: the wish can't be met, a true note says so, other options are offered
        assert said(r) == [f"Nothing is open on {WEEKDAYS[weekday]} for Skin Cancer Screening in the next 14 days; "
                           "here are other options."]
        assert r.options


@pytest.mark.parametrize("entry,offset", [("today", 0), ("Today", 0), ("TODAY", 0), ("tomorrow", 1), ("Tomorrow", 1)])
def test_today_and_tomorrow(catalog, schedule, entry, offset):
    r = run(catalog, schedule, Preferences(days=[entry]))
    want = FIRST + timedelta(days=offset)
    assert [s for s in skin_slots(schedule) if s[2].date() == want], "fixture: something should be open"
    assert r.options and all(o.start.date() == want for o in r.options) and not r.notes, said(r)


@pytest.mark.parametrize("day", WINDOW, ids=str)
def test_every_date_in_the_window_is_accepted(catalog, schedule, day):
    r = run(catalog, schedule, Preferences(days=[day.isoformat()]))
    assert "bad_input" not in kinds(r), said(r)
    if [s for s in skin_slots(schedule) if s[2].date() == day]:
        assert r.options and all(o.start.date() == day for o in r.options) and not r.notes
    else:  # named dates: no "in the next 14 days" (round 5 s6)
        assert said(r) == [f"Nothing is open on {day:%A} {day.day} {day:%B} for Skin Cancer Screening; "
                           "here are other options."]


@pytest.mark.parametrize("day", [FIRST - timedelta(days=1), LAST + timedelta(days=1), FIRST - timedelta(days=365),
                                 LAST + timedelta(days=365)], ids=str)
def test_dates_outside_the_window_are_refused_and_the_note_names_the_window(catalog, schedule, day):
    r = run(catalog, schedule, Preferences(days=[day.isoformat()]))
    assert refused(r), said(r)
    assert "6 October" in r.notes[0].say and "20 October" in r.notes[0].say, said(r)


def test_one_bad_entry_refuses_the_whole_search(catalog, schedule):
    r = run(catalog, schedule, Preferences(days=["Thursday", (LAST + timedelta(days=1)).isoformat()]))
    assert refused(r), said(r)
    r = run(catalog, schedule, Preferences(days=["Thursday", "next Friday"]))
    assert refused(r), said(r)


# ---- every refused day form
REFUSED_DAYS = [
    "Thursday morning", "this afternoon", "Thursday or Friday", "next Thursday", "Thursday works",   # the spec's list
    "Thursday, Friday", "Thursday and Friday", "Thursday at 3pm", "morning", "afternoon", "evening", "tonight",
    "this morning", "weekend", "next week", "Oct 13", "13 October", "October 13th", "20261013", "2026/10/13",
    "13/10/2026", "10/13/2026", "2026-10-7", "2026-1-07", "26-10-13", "2026-02-30", "2026-13-01", "2026-10-00",
    "th", "t", "x", "the day after tomorrow", "today or tomorrow",
]


@pytest.mark.parametrize("entry", REFUSED_DAYS)
def test_every_other_day_form_is_refused(catalog, schedule, entry):
    r = run(catalog, schedule, Preferences(days=[entry]))
    assert refused(r), (entry, said(r), [o.spoken for o in r.options])
    card = skin_card()
    card.change_choice("time", entry)    # new_value is one day entry: the same answer
    assert refused(run(catalog, schedule, card.preferences)), entry
    card = skin_card()
    card.change_choice("time", days=[entry])
    assert refused(run(catalog, schedule, card.preferences)), entry


# ---- time of day
@pytest.mark.parametrize("tod,morning", [("morning", True), ("afternoon", False), ("Morning", True),
                                         ("AFTERNOON", False), ("  morning  ", True)])
def test_morning_and_afternoon(catalog, schedule, tod, morning):
    r = run(catalog, schedule, Preferences(time_of_day=tod))
    assert r.options and not r.notes, said(r)
    assert all((o.start.hour < 12) == morning for o in r.options), [o.spoken for o in r.options]


@pytest.mark.parametrize("tod", ["evening", "morning or afternoon", "morning and afternoon", "lunchtime", "noon",
                                 "am", "pm", "this morning", "early morning", "late afternoon", "mornings",
                                 "night", "Thursday", "today", "before noon", "after 2"])
def test_every_other_time_of_day_is_refused(catalog, schedule, tod):
    r = run(catalog, schedule, Preferences(time_of_day=tod))
    assert refused(r), (tod, said(r))
    card = skin_card()
    card.change_choice("time", time_of_day=tod)
    assert refused(run(catalog, schedule, card.preferences)), tod


def test_day_and_time_together(catalog, schedule):
    r = run(catalog, schedule, Preferences(days=["Thursday", "Friday"], time_of_day="morning"))
    assert r.options and not r.notes
    assert all(o.start.strftime("%A") in ("Thursday", "Friday") and o.start.hour < 12 for o in r.options)


# ---- None keeps, "" / [] clears, new_value vs days
def test_none_keeps_each_field():
    card = skin_card(days=["Thursday"], time_of_day="morning")
    card.change_choice("time")                                    # nothing given: both kept
    assert (card.preferences.days, card.preferences.time_of_day) == (["Thursday"], "morning")
    card.change_choice("time", time_of_day="afternoon")           # days None: kept
    assert (card.preferences.days, card.preferences.time_of_day) == (["Thursday"], "afternoon")
    card.change_choice("time", days=["Friday"])                   # time None: kept
    assert (card.preferences.days, card.preferences.time_of_day) == (["Friday"], "afternoon")
    card.change_choice("time", days=None, time_of_day=None)
    assert (card.preferences.days, card.preferences.time_of_day) == (["Friday"], "afternoon")


def test_empty_clears_each_field_on_its_own():
    card = skin_card(days=["Thursday"], time_of_day="morning")
    card.change_choice("time", days=[])
    assert (card.preferences.days, card.preferences.time_of_day) == ([], "morning")
    card = skin_card(days=["Thursday"], time_of_day="morning")
    card.change_choice("time", time_of_day="")
    assert (card.preferences.days, card.preferences.time_of_day) == (["Thursday"], "")


def test_new_value_is_one_day_entry():
    a, b = skin_card(days=["Monday"], time_of_day="morning"), skin_card(days=["Monday"], time_of_day="morning")
    assert a.change_choice("time", "Thursday") == b.change_choice("time", days=["Thursday"]) == BOOKING
    assert a.preferences == b.preferences and a.preferences.days == ["Thursday"]
    assert a.preferences.time_of_day == "morning"     # time of day not mentioned: kept
    c = skin_card()
    c.change_choice("time", "Thursday", time_of_day="afternoon")
    assert (c.preferences.days, c.preferences.time_of_day) == (["Thursday"], "afternoon")


@pytest.mark.parametrize("new_value,days", [("Thursday", ["Friday"]), ("Thursday", []), ("any day", ["Friday"]),
                                            ("Friday", ["Friday"])])
def test_new_value_and_days_together_are_refused_and_change_nothing(catalog, schedule, new_value, days):
    card = skin_card(days=["Monday"], time_of_day="morning")
    card.preferences.preferred_location_id = "loc_004"
    r = run(catalog, schedule, card.preferences)
    card.remember_offer(r.options)
    card.choose_option(r.options[0].option_id)
    before = copy.deepcopy(card.to_dict())
    with pytest.raises(ValueError):
        card.change_choice("time", new_value, days=days)
    assert card.to_dict() == before


@pytest.mark.parametrize("what", ["weather", "", "doctors", "time of day"])
def test_unknown_thing_to_change_changes_nothing(catalog, schedule, what):
    card = skin_card(days=["Monday"])
    r = run(catalog, schedule, card.preferences)
    card.remember_offer(r.options)
    card.choose_option(r.options[0].option_id)
    before = copy.deepcopy(card.to_dict())
    with pytest.raises(ValueError):
        card.change_choice(what, "Thursday")
    assert card.to_dict() == before


# ---- late in the day and at the window's edges
def test_today_late_in_the_day_gives_a_true_note_and_other_options(catalog, schedule):
    late = datetime(2026, 10, 6, 16, 0)   # 2 hours' notice: nothing left today (closing 17:00)
    assert not [s for s in skin_slots(schedule, late) if s[2].date() == late.date()]
    r = run(catalog, schedule, Preferences(days=["today"]), now=late)
    assert said(r) == ["Nothing is open today for Skin Cancer Screening; here are other options."]
    assert r.options and all(o.start.date() > late.date() for o in r.options)


def test_tomorrow_late_on_a_friday_is_a_saturday(catalog, schedule):
    late = datetime(2026, 10, 9, 23, 30)  # Friday night: tomorrow is Saturday 10 October
    r = run(catalog, schedule, Preferences(days=["tomorrow"]), now=late)
    assert said(r) == ["Nothing is open tomorrow for Skin Cancer Screening; here are other options."]
    assert r.options and all(o.start.date() >= date(2026, 10, 12) for o in r.options)
    r = run(catalog, schedule, Preferences(days=["today"]), now=late)
    assert said(r) == ["Nothing is open today for Skin Cancer Screening; here are other options."]


def test_the_window_moves_with_the_clock(catalog, schedule):
    later = datetime(2026, 10, 9, 23, 30)   # window: 9 to 23 October
    assert not refused(run(catalog, schedule, Preferences(days=["2026-10-23"]), now=later))
    assert refused(run(catalog, schedule, Preferences(days=["2026-10-24"]), now=later))
    assert refused(run(catalog, schedule, Preferences(days=["2026-10-08"]), now=later))
    assert not refused(run(catalog, schedule, Preferences(days=["2026-10-09"]), now=later))


def test_a_refused_search_is_refused_whatever_else_is_asked(catalog, schedule):
    # refusal comes before anything else: even a doctor, place and language wish give no options
    r = run(catalog, schedule, Preferences(days=["next Thursday"], doctor_name_heard="Dr. Kenji Kim",
                                           location_hint="Downtown", language="Spanish"))
    assert refused(r), said(r)


# =========================================================== s2: "no preference" in every field
NO_PREF = ["I don't mind", "dont mind", "I DON'T MIND!", "no preference", "No Preference", "any", "ANY",
           "whatever", "whenever", "any day", "any time", "Any time.", "anyone", "anywhere", "doesn't matter"]


@pytest.mark.parametrize("word", NO_PREF)
def test_no_preference_counts_as_empty_in_every_field(catalog, schedule, word):
    base = run(catalog, schedule, Preferences())
    for field in ("doctor_name_heard", "location_hint", "language", "time_of_day"):
        r = run(catalog, schedule, Preferences(**{field: word}))
        assert not r.notes and key(r) == key(base), (field, word, said(r))
    r = run(catalog, schedule, Preferences(days=[word]))
    assert not r.notes and key(r) == key(base), ("days", word, said(r))


@pytest.mark.parametrize("word", NO_PREF)
def test_a_no_preference_day_entry_is_skipped(catalog, schedule, word):
    r = run(catalog, schedule, Preferences(days=["Thursday", word]))
    want = run(catalog, schedule, Preferences(days=["Thursday"]))
    assert key(r) == key(want) and not r.notes, (word, said(r))


@pytest.mark.parametrize("word", NO_PREF)
def test_no_preference_through_change_choice(catalog, schedule, word):
    card = skin_card(days=["Thursday"], time_of_day="morning", language="Spanish", doctor_name_heard="Dr. Kenji Kim",
                     location_hint="Downtown")
    for what in ("doctor", "location", "language"):
        card.change_choice(what, word)
    card.change_choice("time", days=[word], time_of_day=word)
    assert (card.preferences.days, card.preferences.time_of_day) == ([], "")
    r = run(catalog, schedule, card.preferences)
    assert not r.notes and key(r) == key(run(catalog, schedule, Preferences())), (word, said(r))


@pytest.mark.parametrize("word", ["any time", "any day", "I don't mind", "whenever"])
def test_each_field_is_independent(catalog, schedule, word):
    # "any time" as a day entry clears the day only, not the time of day (and the other way round)
    card = skin_card(days=["Thursday"], time_of_day="morning")
    card.change_choice("time", word)
    assert (card.preferences.days, card.preferences.time_of_day) == ([], "morning")
    card = skin_card(days=["Thursday"], time_of_day="morning")
    card.change_choice("time", time_of_day=word)
    assert (card.preferences.days, card.preferences.time_of_day) == (["Thursday"], "")
    r = run(catalog, schedule, Preferences(days=[word], time_of_day="morning"))
    assert r.options and not r.notes and all(o.start.hour < 12 for o in r.options)
    r = run(catalog, schedule, Preferences(days=["Thursday"], time_of_day=word))
    assert r.options and not r.notes and all(o.start.strftime("%A") == "Thursday" for o in r.options)


@pytest.mark.parametrize("word", NO_PREF)
def test_no_preference_doctor_never_brings_a_turned_down_doctor_back(catalog, schedule, word):
    card = skin_card()
    card.turn_down_doctors(catalog, provider_ids=[DANIEL_CHEN])
    card.change_choice("doctor", word)
    r = run(catalog, schedule, card.preferences)
    assert r.options and DANIEL_CHEN not in {o.provider_id for o in r.options}
    assert card.preferences.not_provider_ids == [DANIEL_CHEN]


# =========================================================== s3: sentences as doctor or place values
SENTENCE_WORDS = ["not", "but", "except", "without", "another", "other", "else", "someone", "somebody", "anyone",
                  "anybody", "different", "instead", "please"]
SPEC_EXAMPLES = ["someone else", "not Dr. Chen", "No, not Dr. Chen", "anyone but Dr. Chen", "another doctor",
                 "the other one", "Dr. Chen please"]


def _forms(word, name):
    return [f"{word} {name}", f"{name} {word}", f"{word.upper()} {name.upper()}!", f"{name},{word}.",
            f"{word.capitalize()}-{name}", f"{name} ({word})"]


@pytest.mark.parametrize("word", SENTENCE_WORDS)
def test_every_sentence_word_in_a_doctor_value_is_refused(catalog, schedule, word):
    for value in _forms(word, "Dr. Chen") + _forms(word, "Dr. Kenji Kim"):
        r = run(catalog, schedule, Preferences(doctor_name_heard=value))
        assert refused(r), (value, said(r), [o.spoken for o in r.options])
        note = r.notes[0].say
        assert "turn_down_doctors" in note and ("just the doctor" in note or "name" in note), note


@pytest.mark.parametrize("word", SENTENCE_WORDS)
def test_every_sentence_word_in_a_place_value_is_refused(catalog, schedule, word):
    for value in _forms(word, "Downtown") + _forms(word, "Midtown Medical Group") + _forms(word, "Union Square"):
        r = run(catalog, schedule, Preferences(location_hint=value))
        assert refused(r), (value, said(r), [o.spoken for o in r.options])


@pytest.mark.parametrize("value", SPEC_EXAMPLES + ["anywhere but Downtown"])
def test_the_spec_examples_are_refused_for_doctor_and_place(catalog, schedule, value):
    assert refused(run(catalog, schedule, Preferences(doctor_name_heard=value)))
    assert refused(run(catalog, schedule, Preferences(location_hint=value)))


@pytest.mark.parametrize("value", SPEC_EXAMPLES + ["Dr. Daniel Chen please", "not Dr. Daniel Chen",
                                                   "Dr. Daniel Chen instead", "Dr. Daniel Chen, not someone else"])
def test_a_sentence_never_brings_a_turned_down_doctor_back(catalog, schedule, value):
    card = skin_card()
    card.turn_down_doctors(catalog, provider_ids=[DANIEL_CHEN])
    card.change_choice("doctor", value)
    assert card.preferences.not_provider_ids == [DANIEL_CHEN]       # change_choice never turns anyone down
    assert refused(run(catalog, schedule, card.preferences))
    assert "not: Dr. Daniel Chen" in card.summary(catalog)           # still turned down
    card.change_choice("doctor", "Dr. Daniel Chen")                  # control: the bare name does bring him back
    r = run(catalog, schedule, card.preferences)
    assert r.options and {o.provider_id for o in r.options} == {DANIEL_CHEN}, said(r)


def test_change_choice_doctor_with_a_sentence_turns_nobody_down(catalog, schedule):
    card = skin_card()
    r = run(catalog, schedule, card.preferences)
    card.remember_offer(r.options)
    card.choose_option(r.options[0].option_id)
    for value in SPEC_EXAMPLES:
        card.change_choice("doctor", value)
        assert card.preferences.not_provider_ids == []


# ---- real names and places that merely look like the words
@pytest.mark.parametrize("name", sorted({x["name"] for x in PROV.values()}))
def test_every_real_doctor_name_is_not_a_sentence(catalog, schedule, name):
    for value in (name, name.replace("Dr. ", ""), "Dr. " + name.split()[-1], name + "'s"):
        r = find_options(catalog, schedule, new_caller(), SKIN, Preferences(doctor_name_heard=value), NOW)
        assert "bad_input" not in kinds(r), (value, said(r))


PLACES = sorted({l["name"] for l in LOC.values()} | set(EXTRAS["landmarks"])
                | {x["neighbourhood"] for x in EXTRAS["locations"].values()}
                | {a for x in EXTRAS["locations"].values() for a in x["also_called"]})


@pytest.mark.parametrize("place", PLACES)
def test_every_real_place_is_not_a_sentence(catalog, schedule, place):
    # round 7: "near X" / "the X one" / "close to X" are passed as the name X plus near yes/no
    for value, near in ((place, False), (place, True), (place.upper(), False), (f"the {place}", True)):
        r = run(catalog, schedule, Preferences(location_hint=value, near=near))
        assert "bad_input" not in kinds(r), (value, said(r))
        assert "place_unknown" not in kinds(r), (value, said(r))


@pytest.mark.parametrize("address", sorted(l["address"] for l in LOC.values()))
def test_our_street_addresses_are_not_sentences(catalog, schedule, address):
    street = " ".join(address.split()[1:])                      # "Geary Blvd"
    for value, near in ((address, False), (address, True), (street, False), (street, True)):   # round 7: names + near
        r = run(catalog, schedule, Preferences(location_hint=value, near=near))
        assert "bad_input" not in kinds(r) and "place_unknown" not in kinds(r), (value, said(r))


@pytest.fixture(scope="module")
def lookalike():
    """A catalog with doctors whose names CONTAIN the words inside longer words."""
    raw = copy.deepcopy(RAW)
    base = next(p for p in raw["providers"] if p["id"] == DANIEL_CHEN)
    names = ["Dr. Anne Otherson", "Dr. Bo Butler", "Dr. Cy Notley", "Dr. Di Elsner", "Dr. Ed Pleasance",
             "Dr. Flo Anotherby", "Dr. Gil Someonez", "Dr. Hal Exceptor", "Dr. Ida Insteadman", "Dr. Jo Withouts"]
    for i, n in enumerate(names):
        p = copy.deepcopy(base)
        p["id"], p["name"] = f"prov_look_{i}", n
        raw["providers"].append(p)
    cat = Catalog(raw, EXTRAS)
    return cat, Schedule(cat), {n: f"prov_look_{i}" for i, n in enumerate(names)}


def test_names_containing_the_words_inside_longer_words_still_work(lookalike):
    cat, sch, ids = lookalike
    for name, pid in ids.items():
        for value in (name, "Dr. " + name.split()[-1], name.split()[-1]):
            r = find_options(cat, sch, new_caller(), SKIN, Preferences(doctor_name_heard=value), NOW)
            assert "bad_input" not in kinds(r), (value, said(r))
            assert r.options and {o.provider_id for o in r.options} == {pid}, (value, said(r))


def test_look_alike_name_can_be_named_back_after_a_turn_down(lookalike):
    cat, sch, ids = lookalike
    card = skin_card()
    card.turn_down_doctors(cat, provider_ids=[ids["Dr. Cy Notley"]])
    card.change_choice("doctor", "Dr. Cy Notley")
    r = find_options(cat, sch, new_caller(), SKIN, card.preferences, NOW)
    assert {o.provider_id for o in r.options} == {ids["Dr. Cy Notley"]}, said(r)


# =========================================================== s4: choosing an option
def _offered_card(catalog, schedule, **prefs):
    card = skin_card(**prefs)
    r = find_options(catalog, schedule, card.caller, SKIN, card.preferences, NOW,
                     first_option_number=card.next_option_number)
    card.remember_offer(r.options)
    return card, r


def test_choose_option_puts_the_option_on_the_card(catalog, schedule):
    card, r = _offered_card(catalog, schedule)
    for o in r.options:
        got = card.choose_option(o.option_id)
        assert got is o or got == o
        c = card.choices
        assert (c.provider_id, c.location_id, c.slot) == (o.provider_id, o.location_id, o.start)
        assert (c.specialty, c.visit_type_id) == ("Dermatology", SKIN)   # untouched


def test_choose_option_accepts_the_number_as_a_number(catalog, schedule):
    card, r = _offered_card(catalog, schedule)
    assert card.choose_option(int(r.options[1].option_id)).option_id == r.options[1].option_id


@pytest.mark.parametrize("bad", ["99", "0", "", None, "one", "1.0", "-1"])
def test_choose_option_refuses_an_option_not_on_offer_and_changes_nothing(catalog, schedule, bad):
    card, r = _offered_card(catalog, schedule)
    card.turn_down_doctors(catalog, provider_ids=[DANIEL_CHEN])
    card.remember_offer(r.options)
    before = copy.deepcopy(card.to_dict())
    with pytest.raises(ValueError):
        card.choose_option(bad)
    assert card.to_dict() == before


def test_choose_option_refuses_a_stale_option(catalog, schedule):
    card, first = _offered_card(catalog, schedule)
    r2 = find_options(catalog, schedule, card.caller, SKIN, Preferences(days=["Thursday"]), NOW,
                      first_option_number=card.next_option_number)
    card.remember_offer(r2.options)
    assert not {o.option_id for o in first.options} & {o.option_id for o in r2.options}
    before = copy.deepcopy(card.to_dict())
    for o in first.options:
        with pytest.raises(ValueError):
            card.choose_option(o.option_id)
    assert card.to_dict() == before
    card.choose_option(r2.options[0].option_id)   # the new ones work


def test_choose_option_with_nothing_on_offer(catalog, schedule):
    card = skin_card()
    with pytest.raises(ValueError):
        card.choose_option("1")
    assert card.choices.provider_id == ""


def test_choosing_a_turned_down_doctor_takes_them_off_the_list(catalog, schedule):
    able = sorted({s[0] for s in skin_slots(schedule)})
    card = skin_card()
    card.turn_down_doctors(catalog, provider_ids=able)   # everyone: they're offered after all
    r = find_options(catalog, schedule, card.caller, SKIN, card.preferences, NOW)
    assert kinds(r) == ["no_other_doctor"] and r.options
    card.remember_offer(r.options)
    pick = card.choose_option(r.options[0].option_id)
    assert pick.provider_id not in card.preferences.not_provider_ids
    assert set(card.preferences.not_provider_ids) == set(able) - {pick.provider_id}
    assert PROV[pick.provider_id]["name"] not in card.summary(catalog).split("not: ")[-1].split("\n")[0] \
        or "not: " not in card.summary(catalog)
    # later changes of every kind keep them off the list
    for change in (("time", "Thursday"), ("location", "Downtown"), ("language", "English"), ("doctor", "")):
        card.choices.provider_id = pick.provider_id   # chosen again (choices set as after a new pick)
        card.change_choice(*change)
        assert pick.provider_id not in card.preferences.not_provider_ids, change


def test_turning_the_chosen_doctor_down_does_put_them_on_the_list(catalog, schedule):
    card, r = _offered_card(catalog, schedule)
    pick = card.choose_option(r.options[0].option_id)
    card.turn_down_doctors(catalog, current=True)
    assert card.preferences.not_provider_ids == [pick.provider_id]
    assert "not: " + pick.provider_name in card.summary(catalog)


@pytest.mark.parametrize("doctor", sorted({s for s in [DANIEL_CHEN, "prov_027", "prov_035"]}))
def test_summary_never_lists_the_chosen_doctor_even_if_filled_in_directly(catalog, doctor):
    card = skin_card()
    card.preferences.not_provider_ids = sorted({doctor, "prov_049"})
    card.choices.provider_id = doctor            # filled in directly, no choose_option
    summary = card.summary(catalog)
    assert "not: " in summary
    not_part = summary.split("not: ")[1].split("\n")[0]
    assert PROV[doctor]["name"] not in not_part.split(", "), summary
    assert PROV["prov_049"]["name"] in not_part


# =========================================================== s6: patient data checks
GOOD = {"id": "p1", "name": "Ann Lee", "date_of_birth": "1984-03-12"}


@pytest.mark.parametrize("dob", ["1990-02-30", "1990-13-01", "1990-00-10", "1990-01-00", "1900-02-29", "12/03/1984",
                                 "1984-3-12", "19840312", "84-03-12", "1984/03/12", "1984-03-12T00:00",
                                 " 1984-03-12", "1984-03-12 ", "March 12 1984", "1984-03-1x"])
def test_a_date_of_birth_that_isnt_a_real_yyyy_mm_dd_date_is_refused(dob):
    with pytest.raises(CatalogError) as e:
        PatientDirectory([dict(GOOD, date_of_birth=dob)])
    assert "p1" in str(e.value) and "date_of_birth" in str(e.value)


@pytest.mark.parametrize("dob", ["1984-02-29", "2000-02-29", "1950-12-31", "2026-01-01"])
def test_real_dates_are_accepted(dob):
    PatientDirectory([dict(GOOD, date_of_birth=dob)])


def test_a_repeated_patient_id_is_refused():
    with pytest.raises(CatalogError) as e:
        PatientDirectory([GOOD, dict(GOOD, name="Bo Chan", date_of_birth="1990-01-01")])
    assert "p1" in str(e.value)


def test_the_real_patient_file_loads():
    raw = json.loads((DATA / "patients.json").read_text())["patients"]
    PatientDirectory(raw)


def test_every_problem_is_listed_once_in_one_error():
    records = [
        "not a record",                                                     # 1
        {"id": "p2", "date_of_birth": "1984-03-12"},                        # 2 missing name
        {"id": "p3", "name": "Cy Diaz", "date_of_birth": "12/03/1984"},     # 3 not YYYY-MM-DD
        {"id": "p4", "name": "Di Ek", "date_of_birth": "1990-02-30"},       # 4 no such day
        {"id": "p5", "name": "Ed Fo", "date_of_birth": "1990-01-01"},
        {"id": "p5", "name": "Fay Go", "date_of_birth": "1991-01-01"},      # 5 repeated id
        {"id": "p5", "name": "Gus Ho", "date_of_birth": "1992-01-01"},      #   (the same problem again)
        {"id": "p6", "name": "Hal Io", "date_of_birth": "1993-01-01", "referrals_on_file": "Cardiology"},  # 6
    ]
    with pytest.raises(CatalogError) as e:
        PatientDirectory(records)
    lines = [ln[2:] for ln in str(e.value).splitlines() if ln.startswith("- ")]
    for fragment in ("#0", "p2", "p3", "p4", "p5", "p6"):
        hits = [ln for ln in lines if fragment in ln.split(":")[0] or f" {fragment} " in f" {ln} "]
        assert len(hits) == 1, (fragment, lines)
    assert len(lines) == 6, lines
