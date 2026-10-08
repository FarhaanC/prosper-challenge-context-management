"""Builder tests for the tool layer (call/) and the agent wiring (agent_builder/).

The tools are driven exactly as the voice agent drives them (run_tool on a
CallSession), with a fixed clock and a temporary bookings file, so no AI is needed.
"""

import asyncio
import json

import pytest

from agent_builder import AgentBuilder
from call import TOOLS, BookingsFileError, CallSession, Clinic, read_bookings, run_tool
from catalog_ids import (
    DANIEL_CHEN_DERM, DANIEL_SMITH_DERM, EMILY_BROWN, JAMES_WILSON, KENJI_KIM_DERM, KNEE_MRI, NEW_PATIENT_CONSULTATION, NOW,
    SKIN_CANCER_SCREENING,
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


def new_caller_at_booking(clinic, visit_type_id=SKIN_CANCER_SCREENING, **wishes) -> CallSession:
    s = session_in(clinic)
    assert step(s, "start_booking", full_name="Farhan Jida", returning=False, **wishes).next_stage == VISIT_TYPE
    assert step(s, "choose_visit_type", visit_type_id=visit_type_id).next_stage == BOOKING
    return s


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


def test_full_booking_saves_one_line_and_is_never_offered_again(clinic, catalog, patients, tmp_path):
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

    # A new agent started from the same file never offers that time again.
    reloaded = Clinic.load(bookings_file=tmp_path / "bookings.jsonl", log_dir=None)
    vt = catalog.visit_types[SKIN_CANCER_SCREENING]
    assert not reloaded.schedule.is_open(first.provider_id, first.location_id, vt.duration_min, first.start, NOW)


def test_knee_mri_refused_for_new_patient_with_an_alternative(clinic):
    s = session_in(clinic)
    step(s, "start_booking", full_name="Farhan Jida", returning=False)
    out = step(s, "choose_visit_type", visit_type_id=KNEE_MRI)
    assert out.next_stage is None and out.result["ok"] is False
    assert out.result["reasons"] and out.result["alternatives"]
    assert "referral" in out.result["careful"]
    assert s.card.choices.visit_type_id == ""


def test_knee_mri_for_james_wilson_offers_imaging_places_near_downtown_first(clinic, catalog):
    s = session_in(clinic)
    name, dob = JAMES_WILSON
    out = step(s, "start_booking", full_name=name, returning=True, date_of_birth=dob, place="Downtown", near=True)
    assert out.result == {"ok": True, "say": "Thank you, James. I've found your details."}
    assert s.card.caller.referrals_on_file == ["Radiology", "Orthopedics"]
    assert step(s, "choose_visit_type", visit_type_id=KNEE_MRI).next_stage == BOOKING
    places = [catalog.locations[o.location_id].name for o in s.card.offered_options]
    assert places and places[0].startswith("Downtown")
    assert all("imaging" in catalog.locations[o.location_id].capabilities for o in s.card.offered_options)


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


def test_same_name_and_birthday_goes_to_staff(catalog, tmp_path):
    twins = PatientDirectory([
        {"id": "a", "name": "Sam Lee", "date_of_birth": "1990-02-02"},
        {"id": "b", "name": "Sam Lee", "date_of_birth": "1990-02-02"},
    ])
    s = session_in(Clinic(catalog, twins, Schedule(catalog)))
    out = step(s, "start_booking", full_name="Sam Lee", returning=True, date_of_birth="1990-02-02")
    assert out.next_stage == END and s.card.status == "handed_off"
    assert "member of staff" in s.fill("{outcome}")


def test_new_caller_needs_a_full_name(clinic):
    s = session_in(clinic)
    out = step(s, "start_booking", full_name="Farhan", returning=False)
    assert out.result["ok"] is False and out.next_stage is None and s.card.caller is None


# ---------------------------------------------------------------- values from the AI
@pytest.mark.parametrize("args", [
    {"days": "Thursday"},                          # a string, not a list
    {"days": ["Thursday morning"]},                # a time in a day entry
    {"time_of_day": "evening"},
    {"near": True},                                # near without a place
    {"doctor_name": "someone else"},               # not a name
    {"place": "not Downtown"},
    {"near": "true"},                              # text, not true/false
])
def test_bad_values_are_refused_and_change_nothing(clinic, args):
    s = session_in(clinic)
    out = step(s, "start_booking", full_name="Farhan Jida", returning=False, **args)
    assert out.result["ok"] is False and out.result["error"] and out.next_stage is None
    assert s.card.caller is None
    assert s.card.preferences.days == [] and s.card.preferences.time_of_day == ""


def test_wishes_travel_with_start_booking(clinic):
    s = session_in(clinic)
    step(s, "start_booking", full_name="Farhan Jida", returning=False, days=["Thursday", "friday"],
         time_of_day="morning", language="Spanish", soonest=True)
    p = s.card.preferences
    assert (p.days, p.time_of_day, p.language, p.soonest) == (["Thursday", "friday"], "morning", "Spanish", True)


def test_option_number_may_come_as_a_number(clinic):
    s = new_caller_at_booking(clinic)
    out = step(s, "choose_option", option_id=int(s.card.offered_options[0].option_id))
    assert out.result["ok"] is True


# ---------------------------------------------------------------- changes and moves
def test_change_choice_in_identify_and_visit_type_records_without_moving(clinic):
    s = session_in(clinic)
    out = step(s, "change_choice", what="time", days=["Friday"])
    assert out.next_stage is None and s.card.preferences.days == ["Friday"]
    step(s, "start_booking", full_name="Farhan Jida", returning=False)
    out = step(s, "change_choice", what="language", new_value="Spanish")
    assert out.next_stage is None and s.stage == VISIT_TYPE and s.card.preferences.language == "Spanish"


def test_time_change_in_booking_gives_fresh_options(clinic):
    s = new_caller_at_booking(clinic)
    before = {o.option_id for o in s.card.offered_options}
    out = step(s, "change_choice", what="time", days=["Friday"], time_of_day="afternoon")
    assert out.next_stage == BOOKING
    after = s.card.offered_options
    assert after and not before & {o.option_id for o in after}  # numbers never reused
    assert all(o.start.weekday() == 4 and o.start.hour >= 12 for o in after)


def test_visit_type_change_goes_back_and_clears_choices(clinic):
    s = new_caller_at_booking(clinic)
    step(s, "choose_option", option_id=s.card.offered_options[0].option_id)
    out = step(s, "change_choice", what="visit_type", new_value="knee MRI")
    assert out.next_stage == VISIT_TYPE
    assert s.card.choices.visit_type_id == "" and s.card.choices.slot is None


def test_time_change_needs_days_or_time_of_day(clinic):
    s = new_caller_at_booking(clinic)
    assert step(s, "change_choice", what="time").result["ok"] is False
    assert step(s, "change_choice", what="time", new_value="Friday").result["ok"] is False


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


def test_turn_down_by_a_name_several_doctors_share(clinic, catalog):
    s = new_caller_at_booking(clinic)
    out = step(s, "turn_down_doctors", doctor_name="Dr. Daniel")
    assert out.result["ok"] is False and out.next_stage is None
    ids = {d["doctor_id"] for d in out.result["which_one"]}
    assert {DANIEL_CHEN_DERM, DANIEL_SMITH_DERM} <= ids
    out = step(s, "turn_down_doctors", doctor_id=DANIEL_CHEN_DERM)
    assert out.next_stage == BOOKING
    assert DANIEL_CHEN_DERM not in {o.provider_id for o in s.card.offered_options}


def test_turn_down_by_one_name(clinic):
    s = new_caller_at_booking(clinic)
    assert step(s, "turn_down_doctors", doctor_name="Dr. Kenji Kim").next_stage == BOOKING
    assert KENJI_KIM_DERM in s.card.preferences.not_provider_ids


def test_time_taken_before_confirm_gives_fresh_options(clinic, catalog):
    s = new_caller_at_booking(clinic)
    o = s.card.offered_options[0]
    step(s, "choose_option", option_id=o.option_id)
    clinic.schedule.book(o.provider_id, o.start, catalog.visit_types[SKIN_CANCER_SCREENING].duration_min)
    out = step(s, "confirm_booking")
    assert out.next_stage == BOOKING and out.result["ok"] is False
    assert "That time is no longer available." in s.fill("{options}").split("Options on offer")[0]
    assert o.start not in {x.start for x in s.card.offered_options if x.provider_id == o.provider_id}
    assert s.card.status == "in_progress"


def test_confirm_needs_a_choice_and_only_happens_once(clinic):
    s = new_caller_at_booking(clinic)
    assert step(s, "confirm_booking").result["ok"] is False
    step(s, "choose_option", option_id=s.card.offered_options[0].option_id)
    assert step(s, "confirm_booking").next_stage == END
    assert step(s, "confirm_booking").result["ok"] is False
    assert step(s, "change_choice", what="time", days=["Friday"]).result["ok"] is False


def test_hand_off_from_any_stage_and_after_booking(clinic):
    s = new_caller_at_booking(clinic)
    out = step(s, "hand_off", reason="speak_to_staff")
    assert out.next_stage == END and s.card.status == "handed_off"
    assert "member of staff" in s.fill("{outcome}")

    s = new_caller_at_booking(clinic)
    step(s, "choose_option", option_id=s.card.offered_options[0].option_id)
    read_back = step(s, "confirm_booking").result["booked"]
    step(s, "hand_off", reason="reschedule")
    assert s.card.status == "booked"
    assert read_back in s.fill("{outcome}") and "member of staff" in s.fill("{outcome}")
    assert step(s, "hand_off", reason="because").result["ok"] is False


def test_answer_question_is_a_plain_lookup(clinic):
    s = session_in(clinic)
    out = step(s, "answer_question", about="doctor", name="Maria Garcia")
    assert out.next_stage is None and len(out.result["results"]) == 2


# ---------------------------------------------------------------- placeholders, log, bookings file
def test_placeholders_and_their_errors(clinic):
    s = session_in(clinic)
    assert "Dermatology" in s.fill("{specialties}")
    assert s.fill("{today}").startswith("Tuesday 6 October at 9 AM")
    with pytest.raises(ValueError):
        s.fill("{options}")       # no search yet
    with pytest.raises(ValueError):
        s.fill("{outcome}")       # no outcome yet
    with pytest.raises(ValueError):
        s.fill("{nonsense}")


def test_bad_values_for_the_ai_are_kept_apart_from_what_the_caller_hears(clinic):
    s = new_caller_at_booking(clinic)
    s.card.preferences.language = "Spanish French"   # as if sent without the tool's checks
    s.refresh_options()
    text = s.fill("{options}")
    assert text.startswith("Fix first (don't read this to the caller")


def test_call_log_has_a_line_per_stage_and_tool(clinic):
    s = new_caller_at_booking(clinic)
    lines = [json.loads(line) for line in s.log_path.read_text(encoding="utf-8").splitlines()]
    events = [(e["event"], e.get("tool") or e.get("stage")) for e in lines]
    assert events == [("stage", IDENTIFY), ("tool", "start_booking"), ("stage", VISIT_TYPE),
                      ("tool", "choose_visit_type"), ("stage", BOOKING)]
    assert lines[-1]["card"]["choices"]["visit_type_id"] == SKIN_CANCER_SCREENING


def test_no_log_or_saving_when_the_clinic_has_no_paths(catalog, patients):
    c = Clinic(catalog, patients, Schedule(catalog))
    s = c.new_call(clock=lambda: NOW)
    s.enter_stage(IDENTIFY, [])
    assert s.log_path is None


def test_damaged_bookings_file_stops_start_up_naming_the_line(catalog, tmp_path):
    f = tmp_path / "bookings.jsonl"
    f.write_text('{"provider_id": "prov_001", "start": "2026-10-07T09:00", "duration_min": 30}\n\nnot json\n',
                 encoding="utf-8")
    with pytest.raises(BookingsFileError, match="line 3"):
        read_bookings(f, catalog)
    f.write_text('{"provider_id": "prov_999", "start": "2026-10-07T09:00", "duration_min": 30}\n', encoding="utf-8")
    with pytest.raises(BookingsFileError, match="unknown doctor"):
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
    assert {f.name for f in b.global_functions()} == {"answer_question", "change_choice", "hand_off"}


@pytest.mark.parametrize("break_it, message", [
    (lambda d: d["nodes"][0]["tools"].append("book_anything"), "isn't in the tool registry"),
    (lambda d: d["global_tools"].append("nope"), "isn't in the tool registry"),
    (lambda d: d["nodes"][0]["task_messages"][0].update(content="{secret}"), "unknown placeholder"),
    (lambda d: d["nodes"].pop(), "can move to stage 'end'"),
    (lambda d: d.update(history="forget"), "history must be"),
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
    assert first["name"] == IDENTIFY and "{today}" not in first["task_messages"][0]["content"]
    assert first["context_strategy"].strategy.value == "reset"
    start = next(f for f in first["functions"] if f.name == "start_booking")
    result, node = asyncio.run(start.handler(
        {"full_name": "Farhan Jida", "returning": False, "doctor_name": "Dr. Garsha"}, FakeFlowManager(s)))
    assert result["ok"] is True and node["name"] == VISIT_TYPE and s.stage == VISIT_TYPE
    assert "Farhan Jida" in node["task_messages"][0]["content"]

    choose = next(f for f in node["functions"] if f.name == "choose_visit_type")
    _, node = asyncio.run(choose.handler({"visit_type_id": SKIN_CANCER_SCREENING}, FakeFlowManager(s)))
    assert "No doctor matching 'Dr. Garsha' can do this" in node["task_messages"][0]["content"]

    # A tool that stays returns just the result: no move.
    pick = next(f for f in node["functions"] if f.name == "choose_option")
    stay = asyncio.run(pick.handler({"option_id": s.card.offered_options[0].option_id}, FakeFlowManager(s)))
    assert isinstance(stay, dict) and stay["ok"] is True


def test_the_starter_agent_still_loads():
    b = AgentBuilder.from_json("example_flow.json")
    assert b.build_initial_node()["name"] == "greeting"
