"""Round 2: change_choice's new shape (decision 51; spec note "change_choice has a new shape").

- The same wish fields as start_booking (doctor_name, place + near, days, time_of_day,
  soonest, language) plus visit_type (and specialty). Several can go in one call.
- "any" drops a wish; an empty string or list counts as not sent.
- Refused, changing nothing: nothing sent; specialty without visit_type; near without a
  real place (place "any" included); a field it doesn't have.
- Applied in the order visit type, language, time, place, doctor; the strongest kind sent
  becomes the "latest" change (find_options applies the latest change first).
- Where the call goes is unchanged: no caller yet or stage 2 -> recorded, stays; booking
  -> fresh options, booking rebuilt; a visit-type change from booking -> visit_type.
- A time change resets "soonest" unless soonest is sent in the same call.

Which times exist comes from the rules module's fake calendar (clinic.Schedule); which
doctor can do what, where, from catalog.json.
"""

import pytest

from voice_reference import (BOOKING, IDENTIFY, JAMES, KNEE_MRI, NEW, PROV, SKIN_CHECK, VISIT_TYPE, make_clinic,
                             new_call, offered, ref_bookable, ref_pairs, section, snapshot, step, to_booking,
                             to_visit_type)
from voice_round2_reference import fields_of, open_starts, refused_unchanged, visit_type_lines, visit_types_of

WEDNESDAY, FRIDAY = 2, 4
MIDTOWN = "loc_005"
SKIN_NEW_PAIRS = sorted(ref_pairs(True, SKIN_CHECK))


@pytest.fixture
def clinic(catalog, directory, tmp_path):
    return make_clinic(catalog, directory, bookings_file=tmp_path / "b.jsonl", log_dir=None)


def numbers(s):
    return [int(o[0]) for o in offered(s)]


def choose_first(s):
    o = s.card.offered_options[0]
    assert step(s, "choose_option", {"option_id": o.option_id}).result["ok"] is True
    return o


# ================================================================== several changes in one call
WED_AFTERNOON_MIDTOWN = {"days": ["Wednesday"], "time_of_day": "afternoon", "place": "Midtown"}


def expected_wednesday_afternoon_midtown(catalog):
    pairs = [(p, l) for p, l in SKIN_NEW_PAIRS if l == MIDTOWN]
    want = open_starts(catalog, pairs, 30, lambda st: st.weekday() == WEDNESDAY, lambda st: st.hour >= 12)
    assert want, "reference: a new patient can have a skin check at Midtown on a Wednesday afternoon"
    return [(pid, lid, st) for st, pid, lid in want[:3]]


@pytest.mark.parametrize("args", [
    WED_AFTERNOON_MIDTOWN,
    {"place": "Midtown", "time_of_day": "afternoon", "days": ["Wednesday"]},  # same, other order
])
def test_three_changes_in_one_call_are_all_applied_in_booking(clinic, catalog, args):
    s = to_booking(clinic)
    old = numbers(s)
    out = step(s, "change_choice", args)
    assert out.result["ok"] is True and out.next_stage == BOOKING and s.stage == BOOKING
    p = s.card.preferences
    assert p.days == ["Wednesday"] and p.time_of_day == "afternoon" and p.location_hint == "Midtown"
    assert min(numbers(s)) > max(old), "fresh options"
    got = [(pid, lid, st) for _, pid, lid, st in offered(s)]
    assert got == expected_wednesday_afternoon_midtown(catalog)


def test_three_changes_in_stage_2_are_recorded_and_used_for_the_first_options(clinic, catalog):
    s = to_visit_type(clinic, NEW)
    out = step(s, "change_choice", WED_AFTERNOON_MIDTOWN)
    assert out.result["ok"] is True and out.next_stage is None and s.stage == VISIT_TYPE
    step(s, "choose_visit_type", {"visit_type_id": SKIN_CHECK})
    got = [(pid, lid, st) for _, pid, lid, st in offered(s)]
    assert got == expected_wednesday_afternoon_midtown(catalog)


def test_several_changes_before_identification_are_recorded_without_moving(clinic):
    s = new_call(clinic)
    out = step(s, "change_choice", {"visit_type": "skin check", "doctor_name": "Dr. Kenji Kim", "place": "Downtown",
                                    "near": True, "days": ["Monday", "Friday"], "time_of_day": "morning",
                                    "soonest": True, "language": "Spanish"})
    assert out.result["ok"] is True and out.next_stage is None and s.stage == IDENTIFY
    assert s.card.caller is None
    p = s.card.preferences
    assert p.visit_description == "skin check" and p.doctor_name_heard == "Dr. Kenji Kim"
    assert (p.location_hint, p.near) == ("Downtown", True)
    assert p.days == ["Monday", "Friday"] and p.time_of_day == "morning"
    assert p.soonest is True and p.language == "Spanish"


def test_doctor_and_place_changed_together_after_choosing(clinic):
    # Both are new wishes: neither the chosen doctor nor the chosen place is carried over.
    s = to_booking(clinic, SKIN_CHECK, JAMES)
    choose_first(s)
    out = step(s, "change_choice", {"doctor_name": "Dr. Daniel Smith", "place": "Richmond Care Center"})
    assert out.result["ok"] is True and s.stage == BOOKING
    p = s.card.preferences
    assert p.doctor_name_heard == "Dr. Daniel Smith" and p.preferred_provider_id == ""
    assert p.location_hint == "Richmond Care Center" and p.preferred_location_id == ""
    assert offered(s) and all((pid, lid) == ("prov_035", "loc_007") for _, pid, lid, _ in offered(s))


# ================================================================== the order, and "latest"
LATEST = [
    ({"days": ["Friday"], "place": "Midtown"}, "location"),
    ({"place": "Midtown", "days": ["Friday"]}, "location"),
    ({"language": "Spanish", "time_of_day": "morning"}, "time"),
    ({"time_of_day": "morning", "language": "Spanish"}, "time"),
    ({"doctor_name": "Dr. Daniel Smith", "language": "Arabic"}, "doctor"),
    ({"language": "Arabic", "doctor_name": "Dr. Daniel Smith"}, "doctor"),
    ({"language": "Spanish", "days": ["Monday"], "place": "Downtown", "doctor_name": "Dr. Kenji Kim"}, "doctor"),
    ({"place": "Downtown", "language": "Spanish", "days": ["Monday"]}, "location"),
]


@pytest.mark.parametrize("args,latest", LATEST)
def test_the_strongest_kind_sent_becomes_the_latest_change(clinic, args, latest):
    s = to_booking(clinic)
    assert step(s, "change_choice", args).result["ok"] is True
    assert s.card.preferences.latest == latest


def test_place_beats_time_when_both_are_sent_and_they_clash(clinic, catalog):
    # Midtown + Friday: for a new patient only Dr. Kenji Kim does skin checks at Midtown, and he
    # is never there on a Friday. The place is the stronger kind, so it wins and the Friday
    # wish gets a note; it must not be the other way round.
    midtown = [(p, l) for p, l in SKIN_NEW_PAIRS if l == MIDTOWN]
    assert open_starts(catalog, midtown, 30)
    assert not open_starts(catalog, midtown, 30, lambda st: st.weekday() == FRIDAY)
    assert open_starts(catalog, SKIN_NEW_PAIRS, 30, lambda st: st.weekday() == FRIDAY), "Friday exists elsewhere"
    s = to_booking(clinic)
    step(s, "change_choice", {"days": ["Friday"], "place": "Midtown"})
    assert offered(s) and all(lid == MIDTOWN for _, _, lid, _ in offered(s))
    assert all(st.weekday() != FRIDAY for *_, st in offered(s))
    told = " ".join(section(s.fill("{options}"), "Tell the caller first"))
    assert "Friday" in told, told


def test_doctor_beats_language_when_both_are_sent_and_they_clash(clinic):
    # Dr. Daniel Smith doesn't speak Arabic; Dr. Daniel Chen does (catalog.json).
    assert "Arabic" not in PROV["prov_035"]["languages"] and "Arabic" in PROV["prov_001"]["languages"]
    s = to_booking(clinic)
    step(s, "change_choice", {"language": "Arabic", "doctor_name": "Dr. Daniel Smith"})
    assert offered(s) and all(pid == "prov_035" for _, pid, _, _ in offered(s))
    told = " ".join(section(s.fill("{options}"), "Tell the caller first"))
    assert "Arabic" in told, told


def test_visit_type_is_applied_first_so_the_other_changes_survive_it(clinic):
    # The visit-type change clears the turned-down list and what depended on the visit; the
    # time and doctor sent with it must still be there afterwards, and be the latest change.
    s = to_booking(clinic, SKIN_CHECK, JAMES)
    step(s, "turn_down_doctors", {"doctor_id": "prov_027"})
    choose_first(s)
    out = step(s, "change_choice", {"days": ["Friday"], "doctor_name": "Dr. Linda Ramirez", "visit_type": "knee MRI"})
    assert out.result["ok"] is True and out.next_stage == VISIT_TYPE and s.stage == VISIT_TYPE
    p = s.card.preferences
    assert p.visit_description == "knee MRI"
    assert p.days == ["Friday"]
    assert p.doctor_name_heard == "Dr. Linda Ramirez" and p.preferred_provider_id == ""
    assert p.latest == "doctor"
    assert p.not_provider_ids == [], "a visit change starts the turned-down list again"
    c = s.card.choices
    assert (c.visit_type_id, c.provider_id, c.location_id, c.slot) == ("", "", "", None)
    assert not s.card.offered_options
    out = step(s, "choose_visit_type", {"visit_type_id": KNEE_MRI})
    assert out.result["ok"] is True
    assert offered(s) and all(pid == "prov_014" and st.weekday() == FRIDAY for _, pid, _, st in offered(s))


def test_visit_type_and_time_from_booking_latest_is_time(clinic):
    s = to_booking(clinic)
    out = step(s, "change_choice", {"visit_type": "flu shot", "time_of_day": "morning"})
    assert out.result["ok"] is True and out.next_stage == VISIT_TYPE
    assert s.card.preferences.time_of_day == "morning" and s.card.preferences.latest == "time"


# ================================================================== soonest and time changes
@pytest.fixture
def soonest_call(clinic):
    s = to_booking(clinic, SKIN_CHECK, NEW, soonest=True, place="Downtown", near=True)
    assert s.card.preferences.soonest is True
    return s


@pytest.mark.parametrize("args", [{"days": ["Friday"]}, {"time_of_day": "morning"},
                                  {"days": ["Friday"], "time_of_day": "afternoon"}])
def test_a_time_change_resets_soonest(soonest_call, args):
    assert step(soonest_call, "change_choice", args).result["ok"] is True
    assert soonest_call.card.preferences.soonest is False


@pytest.mark.parametrize("args", [{"days": ["Friday"], "soonest": True}, {"time_of_day": "morning", "soonest": True}])
def test_soonest_sent_with_the_time_change_is_kept(soonest_call, args):
    assert step(soonest_call, "change_choice", args).result["ok"] is True
    assert soonest_call.card.preferences.soonest is True


@pytest.mark.parametrize("args", [{"place": "Midtown"}, {"language": "Spanish"}, {"doctor_name": "Dr. Kenji Kim"}])
def test_other_changes_keep_soonest(soonest_call, args):
    assert step(soonest_call, "change_choice", args).result["ok"] is True
    assert soonest_call.card.preferences.soonest is True


def test_soonest_on_its_own_ranks_by_time_not_distance(clinic, catalog):
    s = to_booking(clinic, SKIN_CHECK, NEW, place="Downtown", near=True)
    out = step(s, "change_choice", {"soonest": True})
    assert out.result["ok"] is True and out.next_stage == BOOKING
    starts = [st for *_, st in offered(s)]
    assert starts == sorted(starts)
    earliest = open_starts(catalog, SKIN_NEW_PAIRS, 30)[0][0]
    assert starts[0] == earliest, "the soonest time any valid doctor has"


def test_soonest_then_a_time_change_in_identify(clinic):
    s = new_call(clinic)
    step(s, "change_choice", {"soonest": True})
    assert s.card.preferences.soonest is True
    step(s, "change_choice", {"days": ["Friday"]})
    assert s.card.preferences.soonest is False


def test_time_of_day_alone_keeps_the_days_and_days_alone_keep_the_time_of_day(clinic):
    s = to_booking(clinic, SKIN_CHECK, NEW, days=["Thursday"], time_of_day="morning")
    step(s, "change_choice", {"time_of_day": "afternoon"})
    assert s.card.preferences.days == ["Thursday"] and s.card.preferences.time_of_day == "afternoon"
    step(s, "change_choice", {"days": ["Friday"]})
    assert s.card.preferences.days == ["Friday"] and s.card.preferences.time_of_day == "afternoon"


# ================================================================== "any" drops a wish
ALL_WISHES = dict(doctor_name="Dr. Kenji Kim", place="Midtown", days=["Wednesday"], time_of_day="afternoon",
                  language="Spanish")


def wishes(p):
    return {"doctor": (p.doctor_name_heard, p.preferred_provider_id),
            "place": (p.location_hint, p.near, p.preferred_location_id),
            "days": p.days, "time": p.time_of_day, "language": p.language}


DROPS = [
    ({"doctor_name": "any"}, "doctor", ("", "")),
    ({"place": "any"}, "place", ("", False, "")),
    ({"days": ["any"]}, "days", []),
    ({"time_of_day": "any"}, "time", ""),
    ({"language": "any"}, "language", ""),
]


@pytest.mark.parametrize("args,kind,empty", DROPS, ids=[d[1] for d in DROPS])
def test_any_drops_that_wish_and_only_that_one_in_booking(clinic, args, kind, empty):
    s = to_booking(clinic, SKIN_CHECK, NEW, **ALL_WISHES)
    before = wishes(s.card.preferences)
    assert before[kind] != empty
    old = numbers(s)
    out = step(s, "change_choice", args)
    assert out.result["ok"] is True and out.next_stage == BOOKING
    after = wishes(s.card.preferences)
    assert after[kind] == empty
    assert {k: v for k, v in after.items() if k != kind} == {k: v for k, v in before.items() if k != kind}
    assert offered(s) and min(numbers(s)) > max(old)


@pytest.mark.parametrize("args,kind,empty", DROPS, ids=[d[1] for d in DROPS])
def test_any_drops_that_wish_before_identification(clinic, args, kind, empty):
    s = new_call(clinic)
    step(s, "change_choice", dict(ALL_WISHES))
    out = step(s, "change_choice", args)
    assert out.result["ok"] is True and out.next_stage is None and s.stage == IDENTIFY
    assert wishes(s.card.preferences)[kind] == empty


def test_doctor_any_after_choosing_drops_the_doctor_but_carries_the_place(clinic):
    s = to_booking(clinic, SKIN_CHECK, JAMES)
    o = choose_first(s)
    step(s, "change_choice", {"doctor_name": "any"})
    p = s.card.preferences
    assert p.doctor_name_heard == "" and p.preferred_provider_id == ""
    assert p.preferred_location_id == o.location_id, "plan table: a doctor change keeps the place as a wish"


def test_place_any_after_choosing_drops_the_place_but_carries_the_doctor(clinic):
    s = to_booking(clinic, SKIN_CHECK, JAMES)
    o = choose_first(s)
    step(s, "change_choice", {"place": "any"})
    p = s.card.preferences
    assert p.location_hint == "" and p.preferred_location_id == "" and p.near is False
    assert p.preferred_provider_id == o.provider_id, "plan table: a place change keeps the doctor as a wish"


# ================================================================== empty values count as not sent
@pytest.mark.parametrize("args", [{}, {"doctor_name": ""}, {"place": ""}, {"days": []}, {"time_of_day": ""},
                                  {"language": ""}, {"visit_type": ""}, {"doctor_name": "", "days": []}],
                         ids=["nothing", "doctor", "place", "days", "time", "language", "visit", "two empties"])
@pytest.mark.parametrize("where", [IDENTIFY, VISIT_TYPE, BOOKING])
def test_only_empty_values_count_as_nothing_sent(clinic, args, where):
    s = new_call(clinic) if where == IDENTIFY else to_visit_type(clinic, NEW) if where == VISIT_TYPE else \
        to_booking(clinic)
    refused_unchanged(s, "change_choice", args)
    if where == BOOKING:
        assert step(s, "choose_option", {"option_id": s.card.offered_options[0].option_id}).result["ok"] is True


def test_empty_days_sent_with_a_time_of_day_keeps_the_days(clinic):
    s = to_booking(clinic, SKIN_CHECK, NEW, days=["Thursday"])
    assert step(s, "change_choice", {"days": [], "time_of_day": "afternoon"}).result["ok"] is True
    assert s.card.preferences.days == ["Thursday"] and s.card.preferences.time_of_day == "afternoon"


def test_empty_doctor_sent_with_a_language_keeps_the_doctor(clinic):
    s = to_booking(clinic, SKIN_CHECK, NEW, doctor_name="Dr. Kenji Kim")
    assert step(s, "change_choice", {"doctor_name": "", "language": "Spanish"}).result["ok"] is True
    assert s.card.preferences.doctor_name_heard == "Dr. Kenji Kim" and s.card.preferences.language == "Spanish"


def test_empty_place_sent_with_days_keeps_the_place(clinic):
    s = to_booking(clinic, SKIN_CHECK, NEW, place="Midtown")
    assert step(s, "change_choice", {"place": "", "days": ["Wednesday"]}).result["ok"] is True
    assert s.card.preferences.location_hint == "Midtown" and s.card.preferences.days == ["Wednesday"]


# ================================================================== refusals
REFUSED = [
    ("specialty without visit_type", {"specialty": "Radiology"}),
    ("specialty with an empty visit_type", {"visit_type": "", "specialty": "Radiology"}),
    ("near without a place", {"near": True}),
    ("near with an empty place", {"place": "", "near": True}),
    ("near with place any", {"place": "any", "near": True}),
    ("near with a time change", {"days": ["Friday"], "near": True}),
    ("old shape", {"what": "time", "days": ["Friday"]}),
    ("old new_value", {"new_value": "Dr. Kenji Kim"}),
    ("a misspelt field", {"doctor": "Dr. Kenji Kim"}),
    ("good day, bad language", {"days": ["Friday"], "language": "not Spanish"}),
    ("good place, bad day", {"place": "Midtown", "days": ["Friday morning"]}),
    ("good doctor, bad time", {"doctor_name": "Dr. Kenji Kim", "time_of_day": "evening"}),
    ("good visit, bad doctor", {"visit_type": "knee MRI", "doctor_name": "someone else"}),
    ("good visit, unknown specialty", {"visit_type": "knee MRI", "specialty": "Astrology"}),
    ("soonest as text", {"soonest": "yes"}),
    ("days not a list", {"days": "Friday"}),
]


@pytest.mark.parametrize("label,args", REFUSED, ids=[r[0] for r in REFUSED])
@pytest.mark.parametrize("where", [IDENTIFY, VISIT_TYPE, BOOKING])
def test_change_choice_refusals_change_nothing_in_every_stage(clinic, label, args, where):
    s = new_call(clinic) if where == IDENTIFY else to_visit_type(clinic, NEW) if where == VISIT_TYPE else \
        to_booking(clinic)
    refused_unchanged(s, "change_choice", args)
    if where == BOOKING:
        assert step(s, "choose_option", {"option_id": s.card.offered_options[0].option_id}).result["ok"] is True


def test_unknown_field_refusal_names_the_fields_change_choice_has(clinic):
    s = to_booking(clinic)
    msg = refused_unchanged(s, "change_choice", {"what": "time", "days": ["Friday"]})
    assert "what" in msg
    for field in fields_of("change_choice"):
        assert field in msg, (field, msg)


# ================================================================== where the call goes
def test_visit_type_change_in_stage_2_is_recorded_and_stays(clinic):
    s = to_visit_type(clinic, NEW, visit_description="skin check")
    out = step(s, "change_choice", {"visit_type": "knee MRI", "specialty": "Radiology"})
    assert out.result["ok"] is True and out.next_stage is None and s.stage == VISIT_TYPE
    assert s.card.preferences.visit_description == "knee MRI"


@pytest.mark.parametrize("who,is_new,refs", [(NEW, True, []), (JAMES, False, ["Radiology", "Orthopedics"])],
                         ids=["new", "james"])
def test_visit_type_change_with_a_specialty_lists_its_visit_types_in_stage_2(clinic, who, is_new, refs):
    s = to_booking(clinic, SKIN_CHECK, who)
    out = step(s, "change_choice", {"visit_type": "knee MRI", "specialty": "Radiology"})
    assert out.result["ok"] is True and out.next_stage == VISIT_TYPE
    rows = visit_type_lines(s.fill("{visit_types}"))
    assert set(rows) == visit_types_of("Radiology")
    for vid, (_, _, can_book, _) in rows.items():
        assert can_book == ref_bookable(is_new, refs, vid), vid


def test_options_come_back_once_a_new_visit_type_is_accepted(clinic):
    s = to_booking(clinic, SKIN_CHECK, JAMES)
    step(s, "change_choice", {"visit_type": "knee MRI"})
    with pytest.raises(ValueError):
        s.fill("{options}")
    step(s, "choose_visit_type", {"visit_type_id": KNEE_MRI})
    text = s.fill("{options}")
    assert all(PROV[o.provider_id]["name"] in text for o in s.card.offered_options)


def test_a_refused_change_in_booking_leaves_the_card_and_the_options(clinic):
    s = to_booking(clinic)
    before = snapshot(s)
    step(s, "change_choice", {"days": ["Friday"], "place": "anywhere but Downtown"})
    assert snapshot(s) == before
