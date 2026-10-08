"""Voice stages, area 6: what the AI is shown (placeholders filled at move time).

INTERFACE.md: {today} = today's date and the time at the clinics; {booking_card} = who
is calling, what they asked for, what's agreed; {specialties} = the names of all our
specialties; {options} = the notes and options on offer, from the latest search;
{outcome} = what the end stage should tell the caller. The plan: the AI never holds the
catalog; it sees small slices; options are already valid; notes for the caller say why a
wish couldn't be met. Option numbers are never reused (clinic module, card.remember_offer).
"""

from datetime import datetime

import pytest

from voice_reference import (BOOKING, JAMES, KNEE_MRI, LOC, NEW, NOW, PROV, SKIN_CHECK, SPECIALTIES, VT,
                             make_clinic, new_call, offered, option_lines, section, spoken, step, to_booking,
                             to_visit_type)


@pytest.fixture
def clinic(catalog, directory, tmp_path):
    return make_clinic(catalog, directory, bookings_file=tmp_path / "b.jsonl", log_dir=None)


# ------------------------------------------------------------------ {today}
@pytest.mark.parametrize("now,day,clock", [
    (NOW, "Tuesday 6 October", "9 AM"),
    (datetime(2026, 10, 8, 14, 30), "Thursday 8 October", "2:30 PM"),
    (datetime(2026, 10, 12, 0, 5), "Monday 12 October", "12:05 AM"),
])
def test_today_is_the_clinic_date_and_time_from_the_call_clock(clinic, now, day, clock):
    s = new_call(clinic, now=now)
    text = s.fill("{today}")
    assert day in text and clock in text, text


# ------------------------------------------------------------------ {specialties}
def test_specialties_are_exactly_the_21_catalog_specialties(clinic):
    s = to_visit_type(clinic, NEW)
    names = [x.strip() for x in s.fill("{specialties}").rstrip(".").split(",")]
    assert len(SPECIALTIES) == 21
    assert sorted(names) == sorted(SPECIALTIES)


def test_specialties_text_carries_no_visit_types_or_doctors(clinic):
    s = to_visit_type(clinic, NEW)
    text = s.fill("{specialties}")
    assert not any(v["name"] in text for v in VT.values() if v["name"] not in SPECIALTIES)
    assert "Dr." not in text


# ------------------------------------------------------------------ {booking_card}
def test_booking_card_before_identification_names_nobody(clinic):
    s = new_call(clinic)
    text = s.fill("{booking_card}")
    assert "Farhan" not in text and "Wilson" not in text


def test_booking_card_shows_caller_wishes_and_agreed_choices(clinic):
    s = to_booking(clinic, KNEE_MRI, JAMES, visit_description="knee MRI", place="Downtown", near=True,
                   days=["Wednesday"], language="English")
    text = s.fill("{booking_card}")
    assert "James Wilson" in text and "returning" in text.lower()
    assert "Radiology" in text and "Orthopedics" in text, "referrals on file"
    assert "knee MRI" in text and "Downtown" in text and "Wednesday" in text and "English" in text
    assert "MRI - Knee" in text, "the agreed visit type"
    o = s.card.offered_options[0]
    step(s, "choose_option", {"option_id": o.option_id})
    text = s.fill("{booking_card}")
    assert PROV[o.provider_id]["name"] in text and LOC[o.location_id]["name"] in text and spoken(o.start) in text


def test_booking_card_says_new_patient_without_referrals(clinic):
    s = to_visit_type(clinic, NEW)
    text = s.fill("{booking_card}")
    assert "Farhan Jida" in text and "new patient" in text.lower()


def test_booking_card_stays_small(clinic):
    # Plan guarantee 3: what the AI sees doesn't grow with the catalog.
    s = to_booking(clinic, KNEE_MRI, JAMES, place="Downtown", near=True)
    text = s.fill("{booking_card}")
    assert len(text) < 800, len(text)
    others = [p["name"] for pid, p in PROV.items() if p["specialty"] != "Radiology"]
    assert not any(n in text for n in others)


# ------------------------------------------------------------------ {options}
def test_options_text_lists_exactly_the_options_on_offer(clinic):
    s = to_booking(clinic, KNEE_MRI, JAMES)
    lines = option_lines(s.fill("{options}"))
    assert set(lines) == {o.option_id for o in s.card.offered_options}
    for o in s.card.offered_options:
        line = lines[o.option_id]
        assert PROV[o.provider_id]["name"] in line and LOC[o.location_id]["name"] in line
        assert spoken(o.start) in line


def test_options_text_shows_at_most_three(clinic):
    s = to_booking(clinic)
    assert 1 <= len(option_lines(s.fill("{options}"))) <= 3


def test_options_text_is_refreshed_after_every_rebuild(clinic):
    s = to_booking(clinic)
    step(s, "change_choice", {"what": "time", "days": ["Friday"]})
    lines = option_lines(s.fill("{options}"))
    assert set(lines) == {o.option_id for o in s.card.offered_options}
    assert all(o.start.weekday() == 4 for o in s.card.offered_options)


def test_unusable_values_are_for_the_ai_not_the_caller(clinic):
    # Decision 38/40: a value the code can't use is refused with a note saying how to send
    # it; that note is an instruction for the AI and must not be read to the caller.
    s = to_booking(clinic)
    step(s, "change_choice", {"what": "language", "new_value": "Spanish French"})
    text = s.fill("{options}")
    told = " ".join(section(text, "Tell the caller first"))
    assert "Pass one language" not in told and "Spanish French" not in told


@pytest.mark.parametrize("place", ["near Downtown", "Atlantis"])
def test_caller_notes_carry_no_tool_instructions(clinic, place):
    # The booking stage says "First tell the caller anything under 'Tell the caller first'".
    # An instruction about how to send a value ("Pass just a place name") is for the AI;
    # the caller can't "pass" anything. ("near Downtown" is the AI's likely mistake for
    # place="Downtown", near=true: decision 39.)
    s = to_booking(clinic, SKIN_CHECK, NEW, place=place)
    told = section(s.fill("{options}"), "Tell the caller first")
    for line in told:
        for word in ("Pass ", "change_choice", "turn_down_doctors", "choose_option"):
            assert word not in line, f"tool instruction in a note for the caller: {line!r}"


def test_note_for_a_wish_nobody_can_meet_goes_to_the_caller(clinic):
    s = to_booking(clinic, SKIN_CHECK, NEW, language="Vietnamese")
    told = " ".join(section(s.fill("{options}"), "Tell the caller first"))
    # No new-patient dermatologist who offers a skin check speaks Vietnamese (catalog.json).
    assert not any("Vietnamese" in PROV[p]["languages"] for p in ("prov_001", "prov_027", "prov_035"))
    assert "Vietnamese" in told, told


def test_options_text_after_a_change_of_visit_type_shows_no_old_options(clinic):
    # Changing the visit type clears everything that depended on it (plan table, decision
    # 11), including the options on offer. {options} must not still show them.
    s = to_booking(clinic)
    old = {o.option_id for o in s.card.offered_options}
    step(s, "change_choice", {"what": "visit_type", "new_value": "flu shot"})
    assert not s.card.offered_options
    try:
        text = s.fill("{options}")
    except ValueError:
        return  # refusing to show stale options is fine
    assert not (set(option_lines(text)) & old), f"stale options still shown:\n{text}"


# ------------------------------------------------------------------ {outcome}
def test_outcome_after_booking_has_the_read_back(clinic):
    s = to_booking(clinic, KNEE_MRI, JAMES)
    rb = step(s, "choose_option", {"option_id": s.card.offered_options[0].option_id}).result["read_back"]
    step(s, "confirm_booking", {})
    assert rb in s.fill("{outcome}")


def test_outcome_after_hand_off_mentions_staff_and_no_booking(clinic):
    s = to_booking(clinic)
    step(s, "choose_option", {"option_id": s.card.offered_options[0].option_id})
    step(s, "hand_off", {"reason": "speak_to_staff"})
    text = s.fill("{outcome}")
    assert "staff" in text.lower()
    assert "Skin Cancer Screening with" not in text, "nothing was booked, so no read-back"


# ------------------------------------------------------------------ option numbers
def test_option_numbers_are_never_reused_through_a_long_call(clinic):
    s = to_booking(clinic, SKIN_CHECK, JAMES)
    seen = [o[0] for o in offered(s)]
    moves = [("change_choice", {"what": "time", "days": ["Thursday"]}),
             ("turn_down_doctors", {"on_offer": True}),
             ("change_choice", {"what": "location", "new_value": "Midtown"}),
             ("change_choice", {"what": "visit_type", "new_value": "full body skin exam"}),
             ("choose_visit_type", {"visit_type_id": "appt_028"}),
             ("change_choice", {"what": "language", "new_value": "Spanish"}),
             ("change_choice", {"what": "time", "days": [], "time_of_day": ""})]
    for tool, args in moves:
        assert step(s, tool, args).result.get("ok") is True, (tool, args)
        if s.stage == BOOKING:
            now_on_offer = [o[0] for o in offered(s)]
            assert not set(now_on_offer) & set(seen), f"reused numbers after {tool}: {now_on_offer} vs {seen}"
            seen += now_on_offer
    assert len(seen) == len(set(seen))
    assert [int(x) for x in seen] == sorted(int(x) for x in seen)
