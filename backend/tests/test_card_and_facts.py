"""The booking card (what a change clears), the read-back, and answer_question."""

from clinic import BOOKING, VISIT_TYPE, BookingCard, Preferences, answer_question, find_options
from conftest import DOWNTOWN, KNEE_MRI, LINDA_RAMIREZ_RADIOLOGY, NOW, SKIN_CANCER_SCREENING


def _card_with_choices(caller, vt=SKIN_CANCER_SCREENING, provider="prov_027", location=DOWNTOWN):
    card = BookingCard(caller=caller)
    card.choices.specialty = "Dermatology"
    card.choices.visit_type_id = vt
    card.choices.provider_id = provider
    card.choices.location_id = location
    card.choices.slot = NOW.replace(day=8, hour=10)
    return card


def test_changing_visit_type_clears_everything_that_depended_on_it(new_caller):
    card = _card_with_choices(new_caller)
    stage = card.change_choice("visit type", "knee MRI")
    assert stage == VISIT_TYPE
    c = card.choices
    assert (c.specialty, c.visit_type_id, c.provider_id, c.location_id, c.slot) == ("", "", "", "", None)
    assert card.preferences.visit_description == "knee MRI"
    # The old doctor is remembered as a wish, so the next search can say honestly whether it still fits.
    assert card.preferences.preferred_provider_id == "prov_027"


def test_changing_time_keeps_doctor_and_location_as_wishes(new_caller):
    card = _card_with_choices(new_caller)
    stage = card.change_choice("time", days=["Thursday"], time_of_day="afternoon")
    assert stage == BOOKING
    assert card.choices.visit_type_id == SKIN_CANCER_SCREENING and card.choices.slot is None
    assert card.preferences.preferred_provider_id == "prov_027"
    assert card.preferences.preferred_location_id == DOWNTOWN
    assert card.preferences.days == ["Thursday"]


def test_changing_doctor_keeps_location_as_a_wish(new_caller):
    card = _card_with_choices(new_caller)
    assert card.change_choice("doctor", "Dr. Daniel Chen") == BOOKING
    assert card.choices.provider_id == "" and card.choices.location_id == ""
    assert card.preferences.doctor_name_heard == "Dr. Daniel Chen"
    assert card.preferences.preferred_location_id == DOWNTOWN


def test_skin_check_with_garcia_then_knee_mri(catalog, schedule, james):
    """Farhaan's catch on the baseline call: switching to the MRI must not quietly keep
    or quietly drop Dr. Garcia. The agent should SAY he can't do it, and offer who can."""
    card = BookingCard(caller=james, preferences=Preferences(visit_description="skin check", doctor_name_heard="Garcia"))
    card.choices.visit_type_id = SKIN_CANCER_SCREENING
    assert card.change_choice("visit type", "knee MRI") == VISIT_TYPE
    card.choices.visit_type_id = KNEE_MRI  # what choose_visit_type will do in stage 2
    r = find_options(catalog, schedule, james, KNEE_MRI, card.preferences, NOW)
    assert any("Garcia" in n and "MRI - Knee" in n for n in r.notes)
    assert {catalog.providers[o.provider_id].specialty for o in r.options} == {"Radiology"}


def test_read_back_is_built_from_the_card(catalog, james):
    card = _card_with_choices(james, vt=KNEE_MRI, provider=LINDA_RAMIREZ_RADIOLOGY, location=DOWNTOWN)
    text = card.read_back(catalog)
    assert text == ("MRI - Knee with Dr. Linda Ramirez at Downtown Health Center, 4455 Geary Blvd, "
                    "on Thursday 8 October at 10 AM. It takes about 45 minutes.")


def test_answer_question(catalog):
    loc = answer_question(catalog, "location", "Downtown")
    assert loc["results"][0]["address"].startswith("4455 Geary Blvd")
    doc = answer_question(catalog, "doctor", "Maria Garcia")
    assert len(doc["results"]) == 2 and "Several doctors" in doc["message"]
    vt = answer_question(catalog, "visit_type", "knee MRI")
    assert vt["results"][0]["name"] == "MRI - Knee" and vt["results"][0]["needs_referral"] is True
    assert answer_question(catalog, "doctor", "Dr. Nobody Atall")["found"] is False
