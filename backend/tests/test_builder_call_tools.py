"""Builder tests for the tool layer (call/) and the agent wiring (agent_builder/).

The tools are driven exactly as the voice agent drives them (run_tool on a
CallSession), with a fixed clock and a temporary bookings file, so no AI is needed.
The last tests build the real OpenAI request (no network) to check what Pipecat sends.
"""

import asyncio
import json

import pytest

from agent_builder import AgentBuilder
from call import TOOLS, BookingsFileError, CallSession, Clinic, read_bookings, run_tool
from catalog_ids import (
    DANIEL_CHEN_DERM, DANIEL_SMITH_DERM, EMILY_BROWN, JAMES_WILSON, KENJI_KIM_DERM, KNEE_MRI, MIDTOWN,
    NEW_PATIENT_CONSULTATION, NOW, SKIN_CANCER_SCREENING,
)
from clinic import BOOKING, END, IDENTIFY, VISIT_TYPE, PatientDirectory, Schedule

AGENT_FILE = "clinic_agent.json"


@pytest.fixture
def clinic(catalog, patients, tmp_path):
    return Clinic(catalog, patients, Schedule(catalog), bookings_file=tmp_path / "bookings.jsonl",
                  log_dir=tmp_path / "logs")


def session_in(clinic, stage=IDENTIFY) -> CallSession:
    s = clinic.new_call(clock=lambda: NOW)
    s.enter_stage(stage, [])
    return s


def step(s: CallSession, tool: str, **args):
    """Run a tool and, like the builder does, enter the stage it moves to."""
    outcome = run_tool(s, tool, args)
    if outcome.next_stage:
        s.enter_stage(outcome.next_stage, [])
    return outcome


def new_caller_at_visit_type(clinic, **wishes) -> CallSession:
    s = session_in(clinic)
    assert step(s, "start_booking", full_name="Farhan Jida", returning=False, **wishes).next_stage == VISIT_TYPE
    return s


def new_caller_at_booking(clinic, visit_type_id=SKIN_CANCER_SCREENING, **wishes) -> CallSession:
    s = new_caller_at_visit_type(clinic, **wishes)
    assert step(s, "choose_visit_type", visit_type_id=visit_type_id).next_stage == BOOKING
    return s


def book_first_option(s: CallSession) -> str:
    step(s, "choose_option", option_id=s.card.offered_options[0].option_id)
    return step(s, "confirm_booking").result["booked"]


# ---------------------------------------------------------------- the demo paths
def test_garcia_skin_check_is_caught(clinic, catalog):
    """The baseline's mistake: a skin check with Dr. Garcia. No Garcia does them."""
    s = new_caller_at_booking(clinic, doctor_name="Dr. Garsha")
    text = s.fill("{options}")
    assert "No doctor matching 'Dr. Garsha' can do this" in text
    assert "Tell the caller first:" in text
    offered = [o.provider_id for o in s.card.offered_options]
    assert len(offered) == 3
    assert all(catalog.providers[p].specialty == "Dermatology" for p in offered)
    assert not any(catalog.providers[p].name.endswith("Garcia") for p in offered)


def test_full_booking_saves_one_line_in_clinic_time_and_is_never_offered_again(clinic, catalog, tmp_path):
    s = new_caller_at_booking(clinic)
    first = s.card.offered_options[0]
    read_back = step(s, "choose_option", option_id=first.option_id).result["read_back"]
    out = step(s, "confirm_booking")
    assert out.next_stage == END and out.result == {"ok": True, "booked": read_back}
    assert s.card.status == "booked"
    assert read_back in s.fill("{outcome}")

    lines = (tmp_path / "bookings.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    saved = json.loads(lines[0])
    assert (saved["provider_id"], saved["start"], saved["read_back"]) == (
        first.provider_id, first.start.isoformat(), read_back)
    assert saved["booked_at"] == NOW.isoformat(timespec="minutes")  # the call's clinic clock, not the computer's

    # A new agent started from the same file never offers that time again.
    reloaded = Clinic.load(bookings_file=tmp_path / "bookings.jsonl", log_dir=None)
    vt = catalog.visit_types[SKIN_CANCER_SCREENING]
    assert not reloaded.schedule.is_open(first.provider_id, first.location_id, vt.duration_min, first.start, NOW)


def test_knee_mri_refused_for_new_patient_with_an_alternative(clinic):
    s = new_caller_at_visit_type(clinic)
    out = step(s, "choose_visit_type", visit_type_id=KNEE_MRI)
    assert out.next_stage is None and out.result["ok"] is False
    assert out.result["reasons"] and out.result["alternatives"]
    assert "referral" in out.result["careful"]
    assert s.card.choices.visit_type_id == ""


def test_accepting_the_alternative_puts_it_on_the_card(clinic, catalog):
    """R4: the card says what was agreed, not the first words used."""
    s = new_caller_at_visit_type(clinic, visit_description="knee MRI")
    alternative = step(s, "choose_visit_type", visit_type_id=KNEE_MRI).result["alternatives"][0]
    step(s, "choose_visit_type", visit_type_id=alternative["id"])
    card = s.fill("{booking_card}")
    assert "knee MRI" not in card and f"visit: {alternative['name']}" in card


def test_knee_mri_for_james_wilson_offers_imaging_places_near_downtown_first(clinic, catalog):
    s = session_in(clinic)
    name, dob = JAMES_WILSON
    out = step(s, "start_booking", full_name=name, returning=True, date_of_birth=dob, place="Downtown", near=True)
    assert out.result == {"ok": True} and out.next_stage == VISIT_TYPE
    assert s.card.caller.referrals_on_file == ["Radiology", "Orthopedics"]
    assert step(s, "choose_visit_type", visit_type_id=KNEE_MRI).next_stage == BOOKING
    places = [catalog.locations[o.location_id].name for o in s.card.offered_options]
    assert places and places[0].startswith("Downtown")
    assert all("imaging" in catalog.locations[o.location_id].capabilities for o in s.card.offered_options)


def test_specialty_sent_early_lists_its_visit_types_in_stage_two(clinic):
    """R5: stage 2 opens with the visit types ready, so the AI can speak at once."""
    s = new_caller_at_visit_type(clinic, specialty="dermatologist")
    text = s.fill("{visit_types}")
    assert text.startswith("Dermatology visit types for this caller")
    assert f"- {SKIN_CANCER_SCREENING}: Skin Cancer Screening (30 min): can book" in text
    assert "Mole Removal: can't book" in text  # needs a referral
    assert new_caller_at_visit_type(clinic).fill("{visit_types}").startswith("Not looked up yet")


def test_unknown_specialty_is_refused(clinic):
    s = session_in(clinic)
    out = step(s, "start_booking", full_name="Farhan Jida", returning=False, specialty="astrology")
    assert out.result["ok"] is False and s.card.caller is None


# ---------------------------------------------------------------- identity
def test_identity_steps_then_register_as_new(clinic):
    s = session_in(clinic)
    name, _ = EMILY_BROWN
    statuses = [step(s, "start_booking", full_name=name, returning=True, date_of_birth="1990-01-01").result["status"]
                for _ in range(2)]
    assert statuses == ["try_again", "spell_last_name"]
    out = step(s, "start_booking", full_name=name, returning=True, date_of_birth="1990-01-01",
               spelled_last_name="BROWN")
    assert out.result["status"] == "offer_new_or_staff" and out.next_stage is None
    assert s.card.caller is None
    out = step(s, "start_booking", full_name=name, returning=False)
    assert out.next_stage == VISIT_TYPE and s.card.caller.is_new_patient


def test_wishes_said_during_a_failed_identity_try_are_kept(clinic):
    """K1: the caller isn't asked again for what they already said."""
    s = session_in(clinic)
    step(s, "start_booking", full_name="Emily Brown", returning=True, date_of_birth="1990-01-01",
         visit_description="skin check", days=["Friday"])
    assert s.card.caller is None
    assert (s.card.preferences.visit_description, s.card.preferences.days) == ("skin check", ["Friday"])


def test_same_name_and_birthday_goes_to_staff(catalog):
    twins = PatientDirectory([
        {"id": "a", "name": "Sam Lee", "date_of_birth": "1990-02-02"},
        {"id": "b", "name": "Sam Lee", "date_of_birth": "1990-02-02"},
    ])
    s = session_in(Clinic(catalog, twins, Schedule(catalog)))
    out = step(s, "start_booking", full_name="Sam Lee", returning=True, date_of_birth="1990-02-02")
    assert out.next_stage == END and s.card.status == "handed_off"
    assert "member of staff will call the caller back" in s.fill("{outcome}")


def test_new_caller_needs_a_full_name(clinic):
    s = session_in(clinic)
    out = step(s, "start_booking", full_name="Farhan", returning=False)
    assert out.result["ok"] is False and out.next_stage is None and s.card.caller is None


# ---------------------------------------------------------------- values from the AI
@pytest.mark.parametrize("args", [
    {"days": "Thursday"},                          # a string, not a list
    {"days": ["Thursday morning"]},                # a time in a day entry
    {"days": ["2024-10-15"]},                      # the wrong year
    {"time_of_day": "evening"},
    {"near": True},                                # near without a place
    {"doctor_name": "someone else"},               # not a name
    {"place": "not Downtown"},
    {"near": "true"},                              # text, not true/false
    {"language": "not Spanish"},                   # T1
    {"language": "Spanish French"},                # T1
    {"doctor": "Dr. Kenji Kim"},                   # T4: a field start_booking doesn't have
])
def test_bad_values_are_refused_and_change_nothing(clinic, args):
    s = session_in(clinic)
    out = step(s, "start_booking", full_name="Farhan Jida", returning=False, **args)
    assert out.result["ok"] is False and out.result["error"] and out.next_stage is None
    assert s.card.caller is None
    p = s.card.preferences
    assert (p.days, p.time_of_day, p.language, p.doctor_name_heard) == ([], "", "", "")


def test_a_wrong_year_gets_a_message_that_names_the_years(clinic):
    """R1: the AI must be able to see what was wrong."""
    s = session_in(clinic)
    error = step(s, "change_choice", days=["2024-10-15"]).result["error"]
    assert "15 October 2024 is outside the booking window (6 October to 20 October 2026)" in error
    assert "2026" in s.fill("{today}")


def test_wishes_travel_with_start_booking(clinic):
    s = session_in(clinic)
    step(s, "start_booking", full_name="Farhan Jida", returning=False, days=["Thursday", "friday"],
         time_of_day="morning", language="Spanish", soonest=True)
    p = s.card.preferences
    assert (p.days, p.time_of_day, p.language, p.soonest) == (["Thursday", "friday"], "morning", "Spanish", True)


@pytest.mark.parametrize("send, ok", [
    (lambda first: int(first), True),        # the number as a number
    (lambda first: first, True),             # the number as text
    (lambda first: f"Option {first}", False),
    (lambda first: "first", False),
])
def test_option_number_is_a_number_only(clinic, send, ok):
    s = new_caller_at_booking(clinic)
    first = s.card.offered_options[0].option_id
    assert step(s, "choose_option", option_id=send(first)).result["ok"] is ok


def test_answer_question_checks_its_values_and_says_ok(clinic):
    s = session_in(clinic)
    out = step(s, "answer_question", about="doctor", name="Maria Garcia")
    assert out.next_stage is None and out.result["ok"] is True and len(out.result["results"]) == 2
    assert step(s, "answer_question", about="doctor", name=["Dr. Chen"]).result["ok"] is False
    missing = step(s, "answer_question", about="doctor", name="Dr. Nobody").result
    assert missing == {"ok": False, "error": "No doctor matches 'Dr. Nobody'."}  # refusals use "error" (S10)


# ---------------------------------------------------------------- order of the call
def test_stage_tools_need_an_identified_caller(clinic):
    s = session_in(clinic)
    for tool, args in [("list_visit_types", {"specialty": "Dermatology"}),
                       ("choose_visit_type", {"visit_type_id": SKIN_CANCER_SCREENING}),
                       ("confirm_booking", {})]:
        out = step(s, tool, **args)
        assert out.result["ok"] is False and out.next_stage is None and "start_booking" in out.result["error"]


def test_a_finished_call_cannot_be_reopened(clinic):
    s = new_caller_at_booking(clinic)
    book_first_option(s)
    for tool, args in [("choose_visit_type", {"visit_type_id": SKIN_CANCER_SCREENING}),
                       ("choose_option", {"option_id": "1"}), ("confirm_booking", {}),
                       ("turn_down_doctors", {"current": True}), ("change_choice", {"days": ["Friday"]}),
                       ("start_booking", {"full_name": "Farhan Jida", "returning": False})]:
        out = step(s, tool, **args)
        assert out.result["ok"] is False and out.next_stage is None, tool
    assert s.card.status == "booked"
    assert step(s, "answer_question", about="location", name="Midtown").result["ok"] is True


# ---------------------------------------------------------------- changes and moves
def test_change_choice_in_identify_and_visit_type_records_without_moving(clinic):
    s = session_in(clinic)
    out = step(s, "change_choice", days=["Friday"])
    assert out.next_stage is None and s.card.preferences.days == ["Friday"]
    step(s, "start_booking", full_name="Farhan Jida", returning=False)
    out = step(s, "change_choice", language="Spanish")
    assert out.next_stage is None and s.stage == VISIT_TYPE and s.card.preferences.language == "Spanish"


def test_a_renamed_first_stage_still_cannot_skip_identification(clinic):
    """R6: whether a change moves depends on the card, not on a stage name."""
    s = session_in(clinic, stage="greeting")
    out = step(s, "change_choice", days=["Friday"])
    assert out.next_stage is None and s.card.caller is None


def test_time_change_in_booking_gives_fresh_options(clinic):
    s = new_caller_at_booking(clinic)
    before = {o.option_id for o in s.card.offered_options}
    out = step(s, "change_choice", days=["Friday"], time_of_day="afternoon")
    assert out.next_stage == BOOKING
    after = s.card.offered_options
    assert after and not before & {o.option_id for o in after}  # numbers never reused
    assert all(o.start.weekday() == 4 and o.start.hour >= 12 for o in after)


def test_several_changes_in_one_call_are_all_applied(clinic, catalog):
    """R3: "Friday afternoon at Midtown" in one breath."""
    s = new_caller_at_booking(clinic, NEW_PATIENT_CONSULTATION)
    out = step(s, "change_choice", days=["Friday"], time_of_day="afternoon", place="Midtown")
    assert out.next_stage == BOOKING
    p = s.card.preferences
    assert (p.days, p.time_of_day, p.location_hint, p.latest) == (["Friday"], "afternoon", "Midtown", "location")
    offered = s.card.offered_options
    assert offered and all(o.location_id == MIDTOWN and o.start.weekday() == 4 and o.start.hour >= 12
                           for o in offered)


def test_doctor_and_day_in_one_change(clinic):
    s = new_caller_at_booking(clinic)
    step(s, "change_choice", doctor_name="Dr. Kenji Kim", days=["Thursday"])
    assert s.card.preferences.days == ["Thursday"]
    assert all(o.provider_id == KENJI_KIM_DERM and o.start.weekday() == 3 for o in s.card.offered_options)


def test_any_drops_a_wish(clinic):
    s = new_caller_at_booking(clinic, days=["Friday"], time_of_day="morning", doctor_name="Dr. Kenji Kim")
    step(s, "change_choice", days=["any"], time_of_day="any", doctor_name="any")
    p = s.card.preferences
    assert (p.days, p.time_of_day, p.doctor_name_heard) == ([], "", "")


def test_change_choice_needs_something_to_change(clinic):
    s = new_caller_at_booking(clinic)
    before = list(s.card.offered_options)
    for args in [{}, {"what": "time"}, {"near": True}, {"place": "any", "near": True}, {"specialty": "Radiology"}]:
        out = step(s, "change_choice", **args)
        assert out.result["ok"] is False and out.next_stage is None, args
    assert s.card.offered_options == before


def test_doctor_change_in_booking(clinic):
    s = new_caller_at_booking(clinic)
    step(s, "choose_option", option_id=s.card.offered_options[0].option_id)
    assert step(s, "change_choice", doctor_name="Dr. Daniel Smith").next_stage == BOOKING
    assert s.card.choices.slot is None
    assert {o.provider_id for o in s.card.offered_options} == {DANIEL_SMITH_DERM}


def test_place_change_in_booking_keeps_the_chosen_doctor_as_a_wish(clinic, catalog):
    s = new_caller_at_booking(clinic, doctor_name="Dr. Kenji Kim")
    step(s, "choose_option", option_id=s.card.offered_options[0].option_id)
    assert step(s, "change_choice", place="Midtown").next_stage == BOOKING
    assert all((o.provider_id, o.location_id) == (KENJI_KIM_DERM, MIDTOWN) for o in s.card.offered_options)


def test_visit_type_change_goes_back_and_clears_the_old_search(clinic):
    s = new_caller_at_booking(clinic)
    step(s, "choose_option", option_id=s.card.offered_options[0].option_id)
    out = step(s, "change_choice", visit_type="knee MRI", specialty="Radiology")
    assert out.next_stage == VISIT_TYPE
    assert s.card.choices.visit_type_id == "" and s.card.choices.slot is None
    with pytest.raises(ValueError):
        s.fill("{options}")  # T7: the old options can't be shown again
    assert s.fill("{visit_types}").startswith("Radiology visit types")


def test_refused_visit_keeps_the_wishes_said_with_it(clinic):
    """Decision 54: a visit that can't be booked isn't a refused value."""
    s = new_caller_at_visit_type(clinic)
    out = step(s, "choose_visit_type", visit_type_id=KNEE_MRI, days=["Friday"])
    assert out.result["ok"] is False and s.card.preferences.days == ["Friday"]


def test_turn_down_doctors_on_offer(clinic):
    s = new_caller_at_booking(clinic, NEW_PATIENT_CONSULTATION)
    before = {o.provider_id for o in s.card.offered_options}
    assert step(s, "turn_down_doctors", on_offer=True).next_stage == BOOKING
    after = {o.provider_id for o in s.card.offered_options}
    assert after and not before & after


def test_turning_down_everyone_who_can_says_so(clinic):
    """For a new patient, only three dermatologists do skin checks: turning all three
    down brings them back, with a note saying nobody else can."""
    s = new_caller_at_booking(clinic)
    step(s, "turn_down_doctors", on_offer=True)
    assert "No other doctor can do Skin Cancer Screening for you" in s.fill("{options}")
    assert s.card.offered_options


def test_turn_down_by_a_name_several_doctors_share(clinic):
    s = new_caller_at_booking(clinic)
    out = step(s, "turn_down_doctors", doctor_name="Dr. Daniel")
    assert out.result["ok"] is False and out.next_stage is None
    ids = {d["doctor_id"] for d in out.result["which_one"]}
    assert {DANIEL_CHEN_DERM, DANIEL_SMITH_DERM} <= ids
    out = step(s, "turn_down_doctors", doctor_id=DANIEL_CHEN_DERM)
    assert out.next_stage == BOOKING
    assert DANIEL_CHEN_DERM not in {o.provider_id for o in s.card.offered_options}


def test_turn_down_before_any_options_is_kept(clinic):
    """R7: "anything but Dr. Kim", said at the start, is never offered."""
    s = session_in(clinic)
    out = step(s, "turn_down_doctors", doctor_name="Dr. Kenji Kim")
    assert out.result["ok"] is True and out.next_stage is None
    step(s, "start_booking", full_name="Farhan Jida", returning=False)
    step(s, "choose_visit_type", visit_type_id=SKIN_CANCER_SCREENING)
    assert KENJI_KIM_DERM not in {o.provider_id for o in s.card.offered_options}
    assert step(session_in(clinic), "turn_down_doctors", on_offer=True).result["ok"] is False


def test_time_taken_before_confirm_gives_fresh_options_and_keeps_soonest(clinic, catalog):
    s = new_caller_at_booking(clinic, soonest=True)
    o = s.card.offered_options[0]
    step(s, "choose_option", option_id=o.option_id)
    clinic.schedule.book(o.provider_id, o.start, catalog.visit_types[SKIN_CANCER_SCREENING].duration_min)
    out = step(s, "confirm_booking")
    assert out.next_stage == BOOKING and out.result["ok"] is False
    assert "That time is no longer available." in s.fill("{options}").split("Options on offer")[0]
    assert o.start not in {x.start for x in s.card.offered_options if x.provider_id == o.provider_id}
    assert s.card.status == "in_progress" and s.card.preferences.soonest is True  # R8


def test_confirm_needs_a_choice_and_only_happens_once(clinic):
    s = new_caller_at_booking(clinic)
    assert step(s, "confirm_booking").result["ok"] is False
    book_first_option(s)
    assert step(s, "confirm_booking").result["ok"] is False


@pytest.mark.parametrize("where", ["identify", "visit_type", "booking"])
def test_hand_off_from_every_stage(clinic, where):
    s = {"identify": lambda: session_in(clinic), "visit_type": lambda: new_caller_at_visit_type(clinic),
         "booking": lambda: new_caller_at_booking(clinic)}[where]()
    out = step(s, "hand_off", reason="speak_to_staff")
    assert out.next_stage == END and out.result == {"ok": True, "handed_off": True}
    assert s.card.status == "handed_off"
    outcome = s.fill("{outcome}")
    assert "member of staff will call the caller back" in outcome and "putting" not in outcome


def test_hand_off_after_a_booking_mentions_both(clinic):
    s = new_caller_at_booking(clinic)
    read_back = book_first_option(s)
    out = step(s, "hand_off", reason="reschedule")
    assert out.result == {"ok": True, "handed_off": False} and s.card.status == "booked"
    assert read_back in s.fill("{outcome}") and "member of staff" in s.fill("{outcome}")
    assert step(s, "hand_off", reason="because").result["ok"] is False


# ---------------------------------------------------------------- placeholders, log, bookings file
def test_placeholders_and_their_errors(clinic):
    s = session_in(clinic)
    assert "Dermatology" in s.fill("{specialties}")
    assert s.fill("{today}").startswith("Tuesday 6 October 2026 at 9 AM")
    with pytest.raises(ValueError):
        s.fill("{options}")       # no search yet
    with pytest.raises(ValueError):
        s.fill("{outcome}")       # no outcome yet
    with pytest.raises(ValueError):
        s.fill("{nonsense}")


def test_notes_for_the_ai_are_kept_apart_from_what_the_caller_hears(clinic):
    s = new_caller_at_booking(clinic)
    s.card.preferences.language = "Spanish French"   # as if sent without the tool's checks
    s.refresh_options()
    assert s.fill("{options}").startswith("Fix first (don't read this to the caller")
    s = new_caller_at_booking(clinic, place="Atlantis")   # T8: a place we don't know
    text = s.fill("{options}")
    assert "Atlantis" in text.split("Tell the caller first")[0] and text.startswith("Fix first")


def test_call_log_has_a_line_per_stage_and_tool(clinic):
    s = new_caller_at_booking(clinic)
    lines = [json.loads(line) for line in s.log_path.read_text(encoding="utf-8").splitlines()]
    events = [(e["event"], e.get("tool") or e.get("stage")) for e in lines]
    assert events == [("stage", IDENTIFY), ("tool", "start_booking"), ("stage", VISIT_TYPE),
                      ("tool", "choose_visit_type"), ("stage", BOOKING)]
    assert lines[-1]["card"]["choices"]["visit_type_id"] == SKIN_CANCER_SCREENING


def test_an_unexpected_error_is_logged_then_raised(clinic, monkeypatch):
    """R9: bugs aren't turned into refusals, but they do reach the call log."""
    s = session_in(clinic)

    def broken(session, args):
        raise RuntimeError("disk full")
    monkeypatch.setattr(TOOLS["answer_question"], "run", broken)
    with pytest.raises(RuntimeError):
        run_tool(s, "answer_question", {"about": "doctor", "name": "Chen"})
    last = json.loads(s.log_path.read_text(encoding="utf-8").splitlines()[-1])
    assert last["error"] == "RuntimeError: disk full"
    with pytest.raises(ValueError, match="No tool called"):
        run_tool(s, "book_anything", {})


def test_a_failed_save_holds_no_time(clinic, monkeypatch):
    """R9: the file is written before the time is marked taken."""
    s = new_caller_at_booking(clinic)
    o = s.card.offered_options[0]
    step(s, "choose_option", option_id=o.option_id)

    def failing_save(record):
        raise OSError("disk full")
    monkeypatch.setattr(clinic, "save_booking", failing_save)
    with pytest.raises(OSError):
        step(s, "confirm_booking")
    vt = s.catalog.visit_types[SKIN_CANCER_SCREENING]
    assert clinic.schedule.is_open(o.provider_id, o.location_id, vt.duration_min, o.start, NOW)


def test_nothing_is_saved_or_logged_when_the_clinic_has_no_paths(catalog, patients, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    s = session_in(Clinic(catalog, patients, Schedule(catalog)))
    step(s, "start_booking", full_name="Farhan Jida", returning=False)
    step(s, "choose_visit_type", visit_type_id=SKIN_CANCER_SCREENING)
    book_first_option(s)
    assert s.card.status == "booked" and s.log_path is None
    assert list(tmp_path.iterdir()) == []


def test_damaged_bookings_file_stops_start_up_naming_the_line(catalog, tmp_path):
    f = tmp_path / "bookings.jsonl"
    good = '{"provider_id": "prov_001", "start": "2026-10-07T09:00", "duration_min": 30}\n'
    for bad, message in [("not json", "line 3:.*not a JSON record"),
                         ('{"provider_id": "prov_001", "duration_min": 30}', "missing start"),
                         ('{"provider_id": "prov_999", "start": "2026-10-07T09:00", "duration_min": 30}',
                          "unknown doctor"),
                         ('{"provider_id": "prov_001", "start": "soon", "duration_min": 30}', "isn't a date"),
                         ('{"provider_id": "prov_001", "start": "2026-10-07T09:00", "duration_min": "x"}',
                          "isn't a number")]:
        f.write_text(good + "\n" + bad + "\n", encoding="utf-8")
        with pytest.raises(BookingsFileError, match=message):
            read_bookings(f, catalog)
    assert read_bookings(tmp_path / "missing.jsonl", catalog) == []


# ---------------------------------------------------------------- tool registry and agent file
def test_every_tool_schema_is_complete():
    for tool in TOOLS.values():
        assert tool.description and set(tool.required) <= set(tool.properties)
        for name, prop in tool.properties.items():
            assert "type" in prop, (tool.name, name)
            if prop["type"] == "array":
                assert "items" in prop, (tool.name, name)


def agent_dict():
    with open(AGENT_FILE, encoding="utf-8") as f:
        return json.load(f)


def test_agent_file_loads_and_resets_history():
    b = AgentBuilder.from_json(AGENT_FILE)
    assert b.config.history == "reset" and b.config.parallel_tool_calls is False
    assert {f.name for f in b.global_functions()} == {"answer_question", "change_choice", "turn_down_doctors",
                                                      "hand_off"}


@pytest.mark.parametrize("break_it, message", [
    (lambda d: d["nodes"][0]["tools"].append("book_anything"), "isn't in the tool registry"),
    (lambda d: d["global_tools"].append("nope"), "isn't in the tool registry"),
    (lambda d: d["nodes"][0]["task_messages"][0].update(content="{secret}"), "unknown placeholder"),
    (lambda d: d["nodes"][0]["task_messages"][0].update(content="{Options}"), "unknown placeholder"),
    (lambda d: d["nodes"][0]["task_messages"][0].update(content="{booking card}"), "unknown placeholder"),
    (lambda d: d.update(persona="Today is {today}."), "only work in task messages"),
    (lambda d: d["nodes"].pop(), "can move to stage 'end'"),
    (lambda d: d.update(history="forget"), "history must be"),
    (lambda d: d.update(parallel_tool_calls="no"), "parallel_tool_calls must be true or false"),
    (lambda d: d.update(global_tools="hand_off"), "must be a list of tool names"),
    (lambda d: d["nodes"].append(dict(d["nodes"][0])), "Two nodes are called 'identify'"),
    (lambda d: d["nodes"][0]["tools"].append("hand_off"), "list it once"),
    (lambda d: d["nodes"][0]["tools"].append("start_booking"), "listed twice"),
    (lambda d: (d.update(global_tools=[]), d["nodes"][3].update(tools=[])), "has no tools"),
])
def test_agent_file_problems_are_found_at_load(break_it, message):
    d = agent_dict()
    break_it(d)
    with pytest.raises(ValueError, match=message):
        AgentBuilder.from_dict(d)


class FakeFlowManager:
    def __init__(self, session):
        self.state = {"session": session}


def test_the_pipecat_wrapper_moves_with_filled_instructions(clinic):
    b = AgentBuilder.from_json(AGENT_FILE)
    s = clinic.new_call(clock=lambda: NOW)
    first = b.build_initial_node(s)
    assert first["name"] == IDENTIFY and "{" not in first["task_messages"][0]["content"]
    assert first["context_strategy"].strategy.value == "reset"
    start = next(f for f in first["functions"] if f.name == "start_booking")
    result, node = asyncio.run(start.handler(
        {"full_name": "Farhan Jida", "returning": False, "doctor_name": "Dr. Garsha", "specialty": "Dermatology"},
        FakeFlowManager(s)))
    assert result["ok"] is True and node["name"] == VISIT_TYPE and s.stage == VISIT_TYPE
    content = node["task_messages"][0]["content"]
    assert "Farhan Jida" in content and f"{SKIN_CANCER_SCREENING}: Skin Cancer Screening" in content

    choose = next(f for f in node["functions"] if f.name == "choose_visit_type")
    _, node = asyncio.run(choose.handler({"visit_type_id": SKIN_CANCER_SCREENING}, FakeFlowManager(s)))
    assert "No doctor matching 'Dr. Garsha' can do this" in node["task_messages"][0]["content"]

    # A tool that stays returns just the result: no move.
    ask = next(f for f in b.global_functions() if f.name == "answer_question")
    stay = asyncio.run(ask.handler({"about": "location", "name": "Midtown"}, FakeFlowManager(s)))
    assert isinstance(stay, dict) and stay["ok"] is True

    # choose_option stays too, but the code says the read-back, so it "moves" to the same stage (decision 66).
    pick = next(f for f in node["functions"] if f.name == "choose_option")
    picked, same = asyncio.run(pick.handler({"option_id": s.card.offered_options[0].option_id}, FakeFlowManager(s)))
    assert picked["ok"] is True and same["name"] == BOOKING and s.stage == BOOKING

    confirm = next(f for f in node["functions"] if f.name == "confirm_booking")
    _, end = asyncio.run(confirm.handler({}, FakeFlowManager(s)))
    assert end["post_actions"] == [{"type": "end_conversation"}]
    assert "Don't call any tool" in end["task_messages"][0]["content"]


def test_the_real_openai_request_sends_one_tool_at_a_time_in_every_stage(clinic):
    """K11 / R14: build the request the OpenAI service would send (no network) for each
    stage's tools, with the service set up as bot.py sets it up, and check the
    one-tool-at-a-time setting reaches it. (That every stage HAS tools is Pipecat Flows
    adding the global tools to every node, manager.py; the load check covers an agent
    with no global tools.)"""
    from pipecat.adapters.schemas.tools_schema import ToolsSchema
    from pipecat.processors.aggregators.llm_context import LLMContext
    from pipecat.services.openai.llm import OpenAILLMService

    b = AgentBuilder.from_json(AGENT_FILE)
    llm = OpenAILLMService(api_key="sk-test", settings=OpenAILLMService.Settings(
        model=b.config.model, extra={} if b.config.parallel_tool_calls else {"parallel_tool_calls": False}))
    s = clinic.new_call(clock=lambda: NOW)
    for name in ("identify", "visit_type", "booking", "end"):
        if name == "booking":
            s = new_caller_at_booking(clinic)
        if name == "end":
            book_first_option(s)
        node = b._make_node(b._nodes_by_name[name], s)
        tools = [f.to_function_schema() for f in b.global_functions() + node["functions"]]
        ctx = LLMContext(messages=node["task_messages"], tools=ToolsSchema(standard_tools=tools))
        params = llm.build_chat_completion_params(llm.get_llm_adapter().get_llm_invocation_params(
            ctx, system_instruction=b.config.persona, convert_developer_to_user=False))
        assert params["parallel_tool_calls"] is False and params["tools"], name


def test_the_starter_agent_still_loads():
    b = AgentBuilder.from_json("example_flow.json")
    assert b.build_initial_node()["name"] == "greeting"


# ---------------------------------------------------------------- round 2
def test_turning_a_doctor_down_early_keeps_the_doctor_asked_for(clinic):
    """S1: "Dr. Smith, please, but not Dr. Kim", before any options exist."""
    s = new_caller_at_visit_type(clinic, doctor_name="Dr. Daniel Smith")
    out = step(s, "turn_down_doctors", doctor_name="Dr. Kenji Kim")
    assert out.result["ok"] is True and out.next_stage is None
    p = s.card.preferences
    assert (p.doctor_name_heard, p.not_provider_ids, p.latest) == ("Dr. Daniel Smith", [KENJI_KIM_DERM], "")
    step(s, "choose_visit_type", visit_type_id=SKIN_CANCER_SCREENING)
    assert {o.provider_id for o in s.card.offered_options} == {DANIEL_SMITH_DERM}


def test_turning_down_the_doctor_asked_for_drops_that_wish(clinic):
    s = new_caller_at_visit_type(clinic, doctor_name="Dr. Kenji Kim")
    step(s, "turn_down_doctors", doctor_name="Dr. Kenji Kim")
    assert s.card.preferences.doctor_name_heard == ""
    step(s, "choose_visit_type", visit_type_id=SKIN_CANCER_SCREENING)
    assert KENJI_KIM_DERM not in {o.provider_id for o in s.card.offered_options}


@pytest.mark.parametrize("where", ["identify", "visit_type"])
def test_early_turn_downs_survive_a_visit_change(clinic, where):
    """S2: the list only starts again when an agreed visit is replaced."""
    s = session_in(clinic) if where == "identify" else new_caller_at_visit_type(clinic)
    step(s, "turn_down_doctors", doctor_name="Dr. Kenji Kim")
    step(s, "change_choice", visit_type="skin cancer check")
    assert s.card.preferences.not_provider_ids == [KENJI_KIM_DERM]
    if where == "identify":
        step(s, "start_booking", full_name="Farhan Jida", returning=False)
    step(s, "choose_visit_type", visit_type_id=SKIN_CANCER_SCREENING)
    assert KENJI_KIM_DERM not in {o.provider_id for o in s.card.offered_options}


def test_replacing_an_agreed_visit_starts_the_turned_down_list_again(clinic):
    s = new_caller_at_booking(clinic)
    step(s, "turn_down_doctors", on_offer=True)
    step(s, "change_choice", visit_type="knee MRI")
    assert s.card.preferences.not_provider_ids == []


def test_soonest_on_its_own_keeps_the_newer_place_choice(clinic):
    """S3: "whatever's soonest" isn't a new day or time wish."""
    s = new_caller_at_booking(clinic, NEW_PATIENT_CONSULTATION, days=["Friday"])
    step(s, "change_choice", place="Midtown")
    step(s, "change_choice", soonest=True)
    p = s.card.preferences
    assert (p.latest, p.soonest, p.days) == ("location", True, ["Friday"])
    assert all(o.location_id == MIDTOWN for o in s.card.offered_options)


def test_soonest_sent_with_a_time_change_is_kept(clinic):
    s = new_caller_at_booking(clinic)
    step(s, "change_choice", days=["Friday"], soonest=True)
    assert (s.card.preferences.soonest, s.card.preferences.latest) == (True, "time")


def test_choose_visit_type_refuses_once_a_visit_is_agreed(clinic):
    """S4: what's saved must be what was read back."""
    s = new_caller_at_booking(clinic)
    step(s, "choose_option", option_id=s.card.offered_options[0].option_id)
    out = step(s, "choose_visit_type", visit_type_id="appt_028")
    assert out.result["ok"] is False and "change_choice" in out.result["error"]
    assert s.card.choices.visit_type_id == SKIN_CANCER_SCREENING


def test_a_specialty_sent_with_a_failed_identity_try_is_kept(clinic):
    """S6: a later successful try without the specialty doesn't lose it."""
    s = session_in(clinic)
    name, dob = JAMES_WILSON
    step(s, "start_booking", full_name=name, returning=True, date_of_birth="1990-01-01", specialty="Radiology")
    step(s, "start_booking", full_name=name, returning=True, date_of_birth=dob)
    assert s.fill("{visit_types}").startswith("Radiology visit types")


def test_a_specialty_sent_in_stage_two_comes_back_with_its_visit_types(clinic):
    s = new_caller_at_visit_type(clinic)
    out = step(s, "change_choice", visit_type="skin check", specialty="Dermatology")
    assert out.next_stage is None
    assert SKIN_CANCER_SCREENING in {t["id"] for t in out.result["visit_types"]}


def test_visit_type_any_is_refused(clinic):
    """S8."""
    s = new_caller_at_booking(clinic)
    out = step(s, "change_choice", visit_type="any")
    assert out.result["ok"] is False and s.card.choices.visit_type_id == SKIN_CANCER_SCREENING


def test_each_stage_is_told_what_just_happened(clinic):
    """S13: stage 2 can tell a fresh start from a change of visit."""
    s = new_caller_at_visit_type(clinic)
    assert "just been identified as Farhan Jida (a new patient): thank them, by first name (Farhan)" in \
        s.fill("{just_happened}")
    step(s, "choose_visit_type", visit_type_id=SKIN_CANCER_SCREENING)
    assert s.fill("{just_happened}") == "The caller has just chosen Skin Cancer Screening."
    step(s, "change_choice", days=["Friday"], place="Midtown")
    assert s.fill("{just_happened}") == "The caller just changed: time, place. These options are fresh."
    step(s, "change_choice", visit_type="knee MRI")
    assert s.fill("{just_happened}") == "The caller asked for a different kind of visit."
    assert "thank" not in s.fill("{just_happened}")


def test_the_hand_off_goodbye_is_worded_as_done(clinic):
    """S5: nothing in the end stage reads like a request for the hand_off tool."""
    s = session_in(clinic)
    step(s, "hand_off", reason="reschedule")
    outcome = s.fill("{outcome}")
    assert outcome.startswith("This call has already been passed to staff (the caller wanted to reschedule an "
                              "appointment). A member of staff will call the caller back about this.")
    assert "ends the call" not in TOOLS["hand_off"].description


@pytest.mark.parametrize("break_it, message", [
    (lambda d: d["nodes"][2].update(tool=d["nodes"][2].pop("tools")), "Node 'booking': unknown key 'tool'"),
    (lambda d: d.update(global_tool=d.pop("global_tools")), "Unknown key 'global_tool'"),
    (lambda d: d["nodes"][0].update(role_messages=[{"role": "system", "content": "x"}]), "unknown key 'role_messages'"),
    (lambda d: d.update(history=["reset"]), "'history' must be text"),
    (lambda d: d.update(persona=5), "'persona' must be text"),
    (lambda d: d["nodes"][0].update(role_message=["x"]), "'role_message' must be text"),
    (lambda d: d["nodes"][0].update(task_messages=["hello"]), "'task_messages' must be a list of messages"),
    (lambda d: d["nodes"][0]["task_messages"][0].update(content="{{today}}"), "doubled braces"),
])
def test_agent_file_shape_problems_are_found_at_load(break_it, message):
    """S7, S9: a misspelt key or a wrong kind of value is a clear error at start-up."""
    d = agent_dict()
    break_it(d)
    with pytest.raises(ValueError, match=message):
        AgentBuilder.from_dict(d)



# ---------------------------------------------------------------- after Farhaan's first voice call
def test_the_greeting_is_spoken_by_the_code_at_once(clinic):
    """The first call had ~6 s of silence: 3.7 s of it was the AI writing a greeting. The code
    now speaks a fixed greeting the moment the call connects, and the AI waits for the caller."""
    b = AgentBuilder.from_json(AGENT_FILE)
    first = b.build_initial_node(clinic.new_call(clock=lambda: NOW))
    assert first["respond_immediately"] is False
    (say,) = first["pre_actions"]
    # Said with our own "say" action, which can't jam the call if the caller talks over it (review 2026-10-11, R2).
    assert say["type"] == "say" and say["text"].startswith("Hello, you've reached the clinics' scheduling line")
    assert say["text"] in first["task_messages"][0]["content"]  # the AI knows what was already said
    assert "respond_immediately" not in b._make_node(b._nodes_by_name["booking"], new_caller_at_booking(clinic))


def test_new_patients_names_are_spelled_back_and_nothing_is_promised_early():
    stages = {n["name"]: n["task_messages"][0]["content"] for n in agent_dict()["nodes"]}
    assert "spell their first and last name back letter by letter" in stages["identify"]
    assert "Don't say or suggest that any doctor, place or time is available" in stages["identify"]
    assert "Don't ask about doctor, place or time preferences here" in stages["visit_type"]


def test_respond_immediately_must_be_true_or_false():
    d = agent_dict()
    d["nodes"][0]["respond_immediately"] = "no"
    with pytest.raises(ValueError, match="'respond_immediately' must be true or false"):
        AgentBuilder.from_dict(d)


# ---------------------------------------------------------------- after Farhaan's second voice call
def test_days_description_says_a_particular_day_is_sent_as_a_date():
    """'Can we do it for tomorrow?' was sent as "Friday", which means any Friday: the caller
    was offered next week's Friday. The AI is now told to send "tomorrow" or the date."""
    for tool in ("start_booking", "choose_visit_type", "change_choice"):
        days = TOOLS[tool].properties["days"]["description"]
        assert "send \"today\", \"tomorrow\" or its date as YYYY-MM-DD" in days, tool
        assert "A weekday name (\"Friday\") means ANY Friday in the next two weeks" in days, tool


def test_stage_one_passes_a_doctors_name_on_unchecked():
    """In the second call, stage 1 looked Dr. Garcia up and asked "which one?", so the code's
    clear "none of them do skin checks" note was never reached."""
    identify = agent_dict()["nodes"][0]["task_messages"][0]["content"]
    assert "don't look the doctor up or ask which one now" in identify


def test_speech_to_text_is_english_only():
    """A name heard on its own was transcribed as Russian in the second call."""
    with open("bot.py", encoding="utf-8") as f:
        source = f.read()
    assert "ElevenLabsRealtimeSTTService.Settings(language=Language.EN)" in source
