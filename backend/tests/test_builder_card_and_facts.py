"""The booking card (what a change clears), the read-back, clinic time, and answer_question."""

from datetime import datetime, timedelta

import pytest

from catalog_ids import DOWNTOWN, KNEE_MRI, LINDA_RAMIREZ_RADIOLOGY, NOW, SKIN_CANCER_SCREENING
from clinic import BOOKING, VISIT_TYPE, BookingCard, Preferences, answer_question, clinic_now, find_options


def _card(caller, vt=SKIN_CANCER_SCREENING, provider="prov_027", location=DOWNTOWN):
    card = BookingCard(caller=caller)
    card.choices.specialty = "Dermatology"
    card.choices.visit_type_id = vt
    card.choices.provider_id = provider
    card.choices.location_id = location
    card.choices.slot = NOW.replace(day=8, hour=10)
    return card


def test_changing_visit_type_clears_everything_that_depended_on_it(new_caller):
    card = _card(new_caller)
    assert card.change_choice("visit type", "knee MRI") == VISIT_TYPE
    c = card.choices
    assert (c.specialty, c.visit_type_id, c.provider_id, c.location_id, c.slot) == ("", "", "", "", None)
    assert card.preferences.visit_description == "knee MRI"
    assert card.preferences.preferred_provider_id == "prov_027"  # carried over as a weaker wish


def test_changing_time_carries_doctor_and_place_over(new_caller):
    card = _card(new_caller)
    assert card.change_choice("time", days=["Thursday"], time_of_day="afternoon") == BOOKING
    p = card.preferences
    assert (p.preferred_provider_id, p.preferred_location_id, p.days, p.latest) == (
        "prov_027", DOWNTOWN, ["Thursday"], "time")


def test_one_doctor_wish_at_a_time(new_caller):
    card = _card(new_caller)
    card.preferences.doctor_name_heard = "Dr. Kim"
    card.change_choice("location", "Midtown")
    # the chosen doctor replaces the heard name, so the card never holds two doctor wishes
    assert (card.preferences.preferred_provider_id, card.preferences.doctor_name_heard) == ("prov_027", "")


def test_unknown_change_is_refused_before_anything_is_cleared(new_caller):
    card = _card(new_caller)
    with pytest.raises(ValueError):
        card.change_choice("insurance", "Aetna")
    assert card.choices.provider_id == "prov_027"


def test_skin_check_with_garcia_then_knee_mri(catalog, schedule, james):
    """Farhaan's catch on the baseline call: switching to the MRI must not quietly keep
    or quietly drop Dr. Garcia. The agent should SAY he can't do it, and offer who can."""
    card = BookingCard(caller=james, preferences=Preferences(visit_description="skin check", doctor_name_heard="Garcia"))
    card.choices.visit_type_id = SKIN_CANCER_SCREENING
    assert card.change_choice("visit type", "knee MRI") == VISIT_TYPE
    card.choices.visit_type_id = KNEE_MRI
    r = find_options(catalog, schedule, james, KNEE_MRI, card.preferences, NOW)
    assert any("Garcia" in n and "MRI - Knee" in n for n in r.notes)
    assert {catalog.providers[o.provider_id].specialty for o in r.options} == {"Radiology"}


def test_read_back_is_built_from_the_card(catalog, james):
    card = _card(james, vt=KNEE_MRI, provider=LINDA_RAMIREZ_RADIOLOGY, location=DOWNTOWN)
    assert card.read_back(catalog) == ("MRI - Knee with Dr. Linda Ramirez at Downtown Health Center, 4455 Geary Blvd, "
                                       "on Thursday 8 October at 10 AM. It takes about 45 minutes.")


def test_read_back_refuses_an_incomplete_card(catalog, james):  # 15
    with pytest.raises(ValueError, match="isn't complete"):
        BookingCard(caller=james).read_back(catalog)


def test_summary_has_one_line_per_wish(catalog, new_caller):  # 15
    card = BookingCard(caller=new_caller, preferences=Preferences(doctor_name_heard="Garcia"))
    assert card.summary(catalog).count("doctor:") == 1


def test_clinic_now_is_san_francisco_time():  # 9
    from zoneinfo import ZoneInfo
    expected = datetime.now(ZoneInfo("America/Los_Angeles")).replace(tzinfo=None)
    assert abs(clinic_now() - expected) < timedelta(minutes=2)


def test_answer_question(catalog):
    loc = answer_question(catalog, "location", "Downtown")
    assert loc["results"][0]["address"].startswith("4455 Geary Blvd")
    vt = answer_question(catalog, "visit_type", "knee MRI")
    assert vt["results"][0]["name"] == "MRI - Knee" and vt["results"][0]["needs_referral"] is True
    assert answer_question(catalog, "doctor", "Dr. Nobody Atall")["found"] is False


def test_answer_question_lists_every_doctor_sharing_a_name(catalog):  # 10
    r = answer_question(catalog, "doctor", "Dr. Chen")
    assert len(r["results"]) == 7 and "7 doctors" in r["message"]


def test_answer_question_closest_location_uses_real_distance(catalog):  # 6
    r = answer_question(catalog, "location", "the Castro")
    assert r["results"][0]["name"] == "Mission District Family Clinic"
