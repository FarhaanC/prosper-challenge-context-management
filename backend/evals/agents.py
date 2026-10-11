"""The versions being compared (decisions 16, 68, 86).

- OurAgent: the real agent. It runs clinic_agent.json's stages with the tool code in
  call/, exactly as the voice agent's builder sets them up (agent_builder/builder.py).
- NaiveAgent: one stage, never wiped, with the whole catalog and the six rules pasted
  into its instructions, and four tools for data (find_patient, find_open_times) and
  actions (book_appointment, hand_off). With checks=False the booking tool saves
  anything (version 1); with checks=True it runs our final rule check, check_booking,
  and refuses with its reasons (version 2).

Both take turns the same way: the caller's line goes in, AI passes run until the
agent waits for the caller (or the call ends), and everything the caller would hear
comes back in an AgentTurn.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from call import TOOLS, Clinic, run_tool
from clinic import Caller, check_booking, spoken_time
from clinic.slots import booking_days

from .ai import OpenAIChat, Reply, tool_arguments
from .budget import NO_USAGE, Usage

BACKEND_DIR = Path(__file__).resolve().parent.parent
AGENT_FILE = BACKEND_DIR / "clinic_agent.json"
DATA_DIR = BACKEND_DIR / "data"

# A turn that needs more AI passes than this is stuck in a loop: the turn ends and the
# run records it. Our design needs at most 2 per turn (decision 9); 6 leaves room.
MAX_PASSES_PER_TURN = 6


@dataclass
class AgentTurn:
    """One agent turn: what the caller hears, and what it took."""

    said: list = field(default_factory=list)      # lines the caller hears, in order
    passes: int = 0                               # AI passes
    seconds: float = 0.0                          # AI time plus tool time (no rate-limit waits)
    usage: Usage = NO_USAGE
    cost: float = 0.0
    tools: list = field(default_factory=list)     # {"tool", "args", "result", "stage", "next_stage"}
    problems: list = field(default_factory=list)  # things the loop noticed (see the run's transcript)
    order: list = field(default_factory=list)     # what happened, in order: {"said": text} or {"tool": index}

    def say(self, text: str) -> None:
        self.said.append(text)
        self.order.append({"said": text})

    def tool(self, entry: dict) -> None:
        self.order.append({"tool": len(self.tools)})
        self.tools.append(entry)

    def add(self, reply: Reply) -> None:
        self.passes += 1
        self.seconds += reply.seconds
        self.usage = self.usage + reply.usage
        self.cost += reply.cost

    def to_dict(self) -> dict:
        return {"said": self.said, "passes": self.passes, "seconds": round(self.seconds, 3),
                "input_tokens": self.usage.input_tokens, "cached_tokens": self.usage.cached_tokens,
                "output_tokens": self.usage.output_tokens, "cost": round(self.cost, 6),
                "tools": self.tools, "problems": self.problems, "order": self.order}


def tool_schema(name: str, description: str, properties: dict, required: list) -> dict:
    """A tool as OpenAI receives it: the shape Pipecat sends (FunctionSchema.to_default_dict)."""
    return {"type": "function", "function": {
        "name": name, "description": description,
        "parameters": {"type": "object", "properties": properties, "required": required}}}


class _Agent:
    """What both versions share: asking the AI, and keeping the conversation."""

    def __init__(self, ai: OpenAIChat):
        self.ai = ai
        self.system = ""
        self.messages: list = []
        self.tools: list = []
        self.one_tool_at_a_time = True
        self.ended = False

    def add_spoken_line(self, text: str) -> None:
        """A line the code says outside a turn (the silence check-in): it joins the conversation."""
        self.messages.append({"role": "assistant", "content": text})

    def respond(self, caller_text: str) -> AgentTurn:
        turn = AgentTurn()
        self.messages.append({"role": "user", "content": caller_text})
        self._run_passes(turn)
        return turn

    def _run_passes(self, turn: AgentTurn) -> None:
        for _ in range(MAX_PASSES_PER_TURN):
            reply = self._pass(turn)
            if not reply.tool_calls:
                return
            if not self._use_tool(turn, reply) or self.ended:
                return
        turn.problems.append(f"More than {MAX_PASSES_PER_TURN} AI passes in one turn; the turn was ended.")

    def _pass(self, turn: AgentTurn) -> Reply:
        reply = self.ai.reply([{"role": "system", "content": self.system}] + self.messages, self.tools,
                              self.one_tool_at_a_time)
        turn.add(reply)
        if reply.text:
            turn.say(reply.text)
            self.messages.append({"role": "assistant", "content": reply.text})
        return reply

    def _take_tool_call(self, turn: AgentTurn, reply: Reply):
        """The tool call to run (the first; one at a time is asked for), added to the conversation."""
        if len(reply.tool_calls) > 1:
            turn.problems.append(f"The AI asked for {len(reply.tool_calls)} tool calls at once; only the first "
                                 "was run.")
        call = reply.tool_calls[0]
        self.messages.append({"role": "assistant", "tool_calls": [
            {"id": call.id, "type": "function", "function": {"name": call.name, "arguments": call.arguments}}]})
        return call

    def _give_result(self, call, result: dict) -> None:
        self.messages.append({"role": "tool", "tool_call_id": call.id,
                              "content": json.dumps(result, ensure_ascii=False)})

    def _use_tool(self, turn: AgentTurn, reply: Reply) -> bool:
        """Run the tool; True if another AI pass follows straight away."""
        raise NotImplementedError


# ---------------------------------------------------------------- ours
class OurAgent(_Agent):
    """clinic_agent.json run as the voice agent's builder runs it, with the same tool code."""

    def __init__(self, ai: OpenAIChat, clinic: Clinic, now: datetime, agent_file: Path = AGENT_FILE):
        super().__init__(ai)
        self.config = json.loads(Path(agent_file).read_text(encoding="utf-8"))
        self.nodes = {n["name"]: n for n in self.config["nodes"]}
        unsupported = [n["name"] for n in self.config["nodes"]
                       if n.get("edges") or n.get("post_actions")
                       or any(a.get("type") != "tts_say" for a in n.get("pre_actions", []))]
        if unsupported:
            # The typed loop only copies what clinic_agent.json uses; say so rather than run it wrongly.
            raise ValueError(f"The typed loop doesn't run arrows, post-actions or actions other than tts_say "
                             f"(stages: {', '.join(unsupported)}).")
        self.reset = self.config.get("history", "keep") == "reset"
        self.one_tool_at_a_time = self.config.get("parallel_tool_calls", True) is False
        self.clinic = clinic
        self.session = clinic.new_call(clock=lambda: now)
        self._start_stage = self.config["initial_node"]

    def start(self) -> AgentTurn:
        """The call connects: the first stage starts (the code says the greeting)."""
        turn = AgentTurn()
        said, respond_now = self._enter(self._start_stage)
        for line in said:
            turn.say(line)
        if respond_now:
            self._run_passes(turn)
        return turn

    def _enter(self, stage: str) -> tuple:
        """Start a stage as the builder does: fill its instructions from the card, wipe or keep the
        conversation, say its tts_say lines. Returns (lines said, whether the AI answers now)."""
        node = self.nodes[stage]
        contents = [self.session.fill(m.get("content", "")) for m in node.get("task_messages", [])]
        self.session.enter_stage(stage, contents)
        task = [{**m, "content": c} for m, c in zip(node.get("task_messages", []), contents)]
        self.messages = task if self.reset else self.messages + task
        said = [a["text"] for a in node.get("pre_actions", [])]
        self.messages += [{"role": "assistant", "content": s} for s in said]
        self.system = node.get("role_message") or self.config["persona"]
        names = self.config.get("global_tools", []) + node.get("tools", [])  # Pipecat: always-available first
        self.tools = [tool_schema(t.name, t.description, t.properties, t.required) for t in (TOOLS[n] for n in names)]
        return said, node.get("respond_immediately", True)

    def _use_tool(self, turn: AgentTurn, reply: Reply) -> bool:
        call = self._take_tool_call(turn, reply)
        stage = self.session.stage
        started = time.perf_counter()
        args, problem = tool_arguments(call)
        outcome = None
        if problem:
            result = {"status": "error", "error": problem}
        else:
            try:
                outcome = run_tool(self.session, call.name, args)
                result = outcome.result
            except Exception as e:  # Pipecat Flows gives the AI this result when a tool's code fails
                result = {"status": "error", "error": str(e)}
                turn.problems.append(f"{call.name} failed in the code: {type(e).__name__}: {e}")
        turn.seconds += time.perf_counter() - started
        self._give_result(call, result)
        next_stage = outcome.next_stage if outcome else None
        turn.tool({"tool": call.name, "args": args, "result": result, "stage": stage, "next_stage": next_stage})
        if next_stage:
            said, respond_now = self._enter(next_stage)
            for line in said:
                turn.say(line)
            if self.nodes[next_stage].get("end"):
                self._goodbye(turn)
                return False
            return respond_now
        if outcome and outcome.say_now:
            # Decision 66: the code says the read-back as the agent's turn; no second AI pass.
            self.messages.append({"role": "assistant", "content": outcome.say_now})
            turn.say(outcome.say_now)
            return False
        return True

    def _goodbye(self, turn: AgentTurn) -> None:
        """The end stage: one AI pass for the goodbye, then the call ends (post-action end_conversation)."""
        reply = self._pass(turn)
        if reply.tool_calls:
            turn.problems.append("The AI called a tool instead of saying goodbye: the call would end without a "
                                 "goodbye (decision 50).")
        self.ended = True

    def outcome(self) -> dict:
        """What the call ended with, read from the booking card (decision 20): its status, and once it's
        booked, the booking confirm_booking saved from it (the same fields)."""
        card = self.session.card
        bookings = []
        if card.status == "booked":
            c = card.choices
            bookings.append({"caller": card.caller.name, "patient_id": card.caller.patient_id,
                             "visit_type_id": c.visit_type_id, "provider_id": c.provider_id,
                             "location_id": c.location_id, "start": c.slot.isoformat(),
                             "duration_min": self.clinic.catalog.visit_types[c.visit_type_id].duration_min})
        return {"status": card.status, "bookings": bookings,
                "name_confirmed": card.caller.name_confirmed if card.caller else None}


# ---------------------------------------------------------------- naive
def _greeting(agent_file: Path = AGENT_FILE) -> str:
    """The line the code says when a call connects, taken from the agent file, so every version greets
    the caller the same way."""
    config = json.loads(Path(agent_file).read_text(encoding="utf-8"))
    first = next(n for n in config["nodes"] if n["name"] == config["initial_node"])
    return " ".join(a["text"] for a in first.get("pre_actions", []) if a.get("type") == "tts_say")


GREETING = _greeting()
HAND_OFF_REASONS = TOOLS["hand_off"].properties["reason"]["enum"]   # the same reasons ours accepts
MAX_TIMES = 6   # open times find_open_times gives back at most

NAIVE_PERSONA = (
    "You are a warm, efficient scheduling assistant for a group of healthcare clinics in San Francisco. Your "
    "replies are spoken aloud: no emojis, lists or symbols, and keep each reply to one or two short sentences. "
    "Ask one question at a time. Never make up a fact, a doctor, a place or a time: use only the catalog in your "
    "instructions and what your tools return.")

NAIVE_INSTRUCTIONS = """Now: {today}.

The caller has already heard this greeting: "{greeting}" Don't greet them again.

Your job is to book one appointment that follows every booking rule below, or to explain plainly why it can't be done.
1. Find out the caller's full name and whether they've been a patient with us before. For a returning patient, also ask their date of birth and call find_patient: their record shows any referrals on file. New patients have no referrals on file.
2. Find out what they need, and help them choose a visit type from the catalog.
3. Choose a doctor and location that fit the visit, the caller and the rules, call find_open_times, and offer the caller up to three times.
4. Read the booking back (visit, doctor, location, day and time) and ask whether to book it. Only after they say yes, call book_appointment.
5. Then confirm it in one short sentence, thank them and say goodbye.
If they want to reschedule or cancel, or ask for a person, call hand_off and tell them a member of staff will call them back.

Booking rules:
{rules}

The clinics' catalog (JSON):
{catalog}

Our notes on the locations (neighbourhood, other names, map point):
{places}

Descriptions of visit types that sound alike:
{visit_notes}"""

NAIVE_TOOLS = [
    tool_schema("find_patient", "Look up a returning patient by full name and date of birth.", {
        "full_name": {"type": "string", "description": "First and last name."},
        "date_of_birth": {"type": "string", "description": "YYYY-MM-DD."}}, ["full_name", "date_of_birth"]),
    tool_schema("find_open_times", (
        "Open appointment times for a visit type over the next two weeks, soonest first: for one doctor, or, "
        "without provider_id, for every doctor who offers that visit type. Each time comes with the doctor and "
        f"the location the doctor is at that day. Returns up to {MAX_TIMES} times (at most 2 per doctor when it's "
        "for every doctor)."), {
        "visit_type_id": {"type": "string", "description": "The visit type's id from the catalog."},
        "provider_id": {"type": "string", "description": "Only this doctor (an id from the catalog). Leave out "
                                                          "for every doctor who offers the visit type."},
        "days": {"type": "array", "items": {"type": "string"},
                 "description": "Only these dates, YYYY-MM-DD. Leave out for any day."},
        "time_of_day": {"type": "string", "enum": ["morning", "afternoon"],
                        "description": "Only mornings (before noon) or afternoons. Leave out for any time."}},
        ["visit_type_id"]),
    tool_schema("book_appointment", "Book the appointment, after the caller said yes to the read-back.", {
        "patient_name": {"type": "string", "description": "The caller's full name."},
        "patient_id": {"type": "string", "description": "Returning patients: the id find_patient gave."},
        "visit_type_id": {"type": "string"},
        "provider_id": {"type": "string"},
        "location_id": {"type": "string"},
        "start": {"type": "string", "description": "The start time exactly as find_open_times gave it."}},
        ["patient_name", "visit_type_id", "provider_id", "location_id", "start"]),
    tool_schema("hand_off", "Pass the call to staff, who will call the caller back.", {
        "reason": {"type": "string", "enum": HAND_OFF_REASONS}}, ["reason"]),
]


def naive_instructions(clinic: Clinic, now: datetime, data_dir: Path = DATA_DIR) -> str:
    """The naive version's one set of instructions: the rules and every catalog file, pasted whole."""
    raw = json.loads((data_dir / "catalog.json").read_text(encoding="utf-8"))
    extras = json.loads((data_dir / "location_extras.json").read_text(encoding="utf-8"))
    notes = json.loads((data_dir / "visit_type_notes.json").read_text(encoding="utf-8"))
    compact = {"separators": (",", ":"), "ensure_ascii": False}
    return NAIVE_INSTRUCTIONS.format(
        today=clinic.new_call(clock=lambda: now).fill("{today}"), greeting=GREETING,
        rules="\n".join(f"- {r}" for r in raw["policies"]),
        catalog=json.dumps(raw, **compact), places=json.dumps(extras["locations"], **compact),
        visit_notes=json.dumps(notes, **compact))


class NaiveAgent(_Agent):
    def __init__(self, ai: OpenAIChat, clinic: Clinic, now: datetime, checks: bool, data_dir: Path = DATA_DIR):
        super().__init__(ai)
        self.clinic = clinic
        self.now = now
        self.checks = checks
        self.status = "in_progress"
        self.bookings: list = []
        self.system = NAIVE_PERSONA
        self.messages = [{"role": "developer", "content": naive_instructions(clinic, now, data_dir)}]
        self.tools = NAIVE_TOOLS

    def start(self) -> AgentTurn:
        self.messages.append({"role": "assistant", "content": GREETING})
        turn = AgentTurn()
        turn.say(GREETING)
        return turn

    def _use_tool(self, turn: AgentTurn, reply: Reply) -> bool:
        call = self._take_tool_call(turn, reply)
        started = time.perf_counter()
        args, problem = tool_arguments(call)
        handler = {"find_patient": self._find_patient, "find_open_times": self._find_open_times,
                   "book_appointment": self._book, "hand_off": self._hand_off}.get(call.name)
        if problem:
            result = {"ok": False, "error": problem}
        elif handler is None:
            result = {"ok": False, "error": f"There's no tool called {call.name}."}
        else:
            result = handler(args)
        turn.seconds += time.perf_counter() - started
        self._give_result(call, result)
        turn.tool({"tool": call.name, "args": args, "result": result, "stage": "naive", "next_stage": None})
        return True

    # ---- the four tools ----------------------------------------------------
    def _find_patient(self, args: dict) -> dict:
        found = self.clinic.patients.lookup(args.get("full_name"), args.get("date_of_birth"))
        if found.status != "found":
            return {"found": False, "why": "No single patient matches that full name and date of birth "
                                           "(send the date as YYYY-MM-DD)."}
        c = found.caller
        return {"found": True, "patient_id": c.patient_id, "name": c.name, "referrals_on_file": c.referrals_on_file}

    def _find_open_times(self, args: dict) -> dict:
        """The same fake schedule ours uses, with no rule checks: the doctors are the ones the catalog lists
        for the visit type (or the one asked for), each at the location the schedule puts them that day."""
        catalog, schedule = self.clinic.catalog, self.clinic.schedule
        vt_id, provider_id = args.get("visit_type_id"), args.get("provider_id")
        vt = catalog.visit_types.get(vt_id) if isinstance(vt_id, str) else None
        if provider_id is None:
            doctors = catalog.providers_offering(vt.id) if vt else []
        else:
            doctor = catalog.providers.get(provider_id) if isinstance(provider_id, str) else None
            doctors = [doctor] if doctor else []
        if vt is None or not doctors:
            return {"ok": False, "error": "Send a visit_type_id from the catalog, and a provider_id from the "
                                          "catalog or none."}
        wanted = set(args.get("days") or [])
        part = args.get("time_of_day")
        each = MAX_TIMES if len(doctors) == 1 else 2   # several doctors: a few times from each
        found = []
        for doctor in doctors:
            mine = []
            for day in booking_days(self.now):
                location_id = schedule.location_on(doctor.id, day)
                if (wanted and day.isoformat() not in wanted) or location_id is None:
                    continue
                for start in schedule.open_slots_on(doctor.id, location_id, vt.duration_min, day, self.now):
                    if part and (start.hour < 12) != (part == "morning"):
                        continue
                    mine.append((start, doctor, location_id))
                    if len(mine) == each:
                        break
                if len(mine) == each:
                    break
            found += mine
        found.sort(key=lambda x: (x[0], x[1].id))
        return {"ok": True, "times": [
            {"start": start.isoformat(timespec="minutes"), "spoken": spoken_time(start), "provider_id": doctor.id,
             "doctor": doctor.name, "location_id": location_id, "location": catalog.locations[location_id].name}
            for start, doctor, location_id in found[:MAX_TIMES]]}

    def _book(self, args: dict) -> dict:
        record = {k: args.get(k) for k in ("patient_name", "patient_id", "visit_type_id", "provider_id",
                                           "location_id", "start")}
        if self.checks:
            problems = self._rule_problems(record)
            if problems:
                return {"ok": False, "problems": problems}
            vt = self.clinic.catalog.visit_types[record["visit_type_id"]]  # check_booking passed: a real id
            self.clinic.schedule.book(record["provider_id"], datetime.fromisoformat(record["start"]), vt.duration_min)
        self.bookings.append(record)
        self.status = "booked"
        return {"ok": True, "booked": record}

    def _rule_problems(self, record: dict) -> list:
        """Version 2: our final rule check, with the caller the record names."""
        patient_id = record.get("patient_id")
        caller: Optional[Caller] = Caller(name=str(record.get("patient_name") or ""))
        if patient_id:
            r = next((r for r in self.clinic.patients.records if r["id"] == patient_id), None)
            if r is None:
                return [f"There's no patient with id {patient_id!r}."]
            caller = Caller(name=r["name"], patient_id=r["id"], is_new_patient=False,
                            referrals_on_file=list(r.get("referrals_on_file", [])))
        try:
            start = datetime.fromisoformat(str(record.get("start")))
        except ValueError:
            start = None
        return check_booking(self.clinic.catalog, self.clinic.schedule, caller, record.get("visit_type_id"),
                             record.get("provider_id"), record.get("location_id"), start, self.now)

    def _hand_off(self, args: dict) -> dict:
        if args.get("reason") not in HAND_OFF_REASONS:  # refused as ours refuses it
            return {"ok": False, "error": f"reason must be one of: {', '.join(HAND_OFF_REASONS)}."}
        if self.status == "in_progress":
            self.status = "handed_off"
        return {"ok": True}

    def outcome(self) -> dict:
        return {"status": self.status, "bookings": self.bookings, "name_confirmed": None}
