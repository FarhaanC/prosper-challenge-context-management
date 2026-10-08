"""Probe 1: drive a whole call through the real Pipecat wrappers (AgentBuilder handlers)
and print exactly what the AI is given at each stage, plus each tool's reply.

Run from backend/:  python3 ../docs/reviews/2026-10-08-voice-stages/review-probes/p1_what_the_ai_sees.py
"""
import asyncio
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "backend" / "tests"))

from agent_builder import AgentBuilder  # noqa: E402
from call import Clinic  # noqa: E402
from clinic import Catalog, PatientDirectory, Schedule  # noqa: E402

NOW = datetime(2026, 10, 6, 9, 0)
AGENT = Path(__file__).resolve().parents[4] / "backend" / "clinic_agent.json"


class FM:
    def __init__(self, s):
        self.state = {"session": s}


def call(node, name, args, s):
    f = next(f for f in node["functions"] if f.name == name)
    out = asyncio.run(f.handler(args, FM(s)))
    if isinstance(out, tuple):
        result, nxt = out
        print(f"\n>>> {name}({args}) -> {result}  [MOVES to {nxt['name']}]")
        print(f"--- instructions for stage '{nxt['name']}' ---\n{nxt['task_messages'][0]['content']}")
        return nxt
    print(f"\n>>> {name}({args}) -> {out}  [stays]")
    return node


def main():
    cat = Catalog.load()
    clinic = Clinic(cat, PatientDirectory.load(), Schedule(cat))
    b = AgentBuilder.from_json(AGENT)
    s = clinic.new_call(clock=lambda: NOW)
    node = b.build_initial_node(s)
    print(f"--- instructions for stage '{node['name']}' ---\n{node['task_messages'][0]['content']}")
    print("tools offered in identify (node only, globals are added by FlowManager):",
          [f.name for f in node["functions"]])
    node = call(node, "start_booking", {"full_name": "James Wilson", "returning": True,
                                        "date_of_birth": "1984-03-12", "visit_description": "knee MRI",
                                        "place": "Downtown", "near": True}, s)
    node = call(node, "list_visit_types", {"specialty": "Radiology"}, s)
    node = call(node, "choose_visit_type", {"visit_type_id": "appt_065"}, s)
    opt = s.card.offered_options[0].option_id
    node = call(node, "choose_option", {"option_id": opt}, s)
    node = call(node, "confirm_booking", {}, s)
    print("\nend node post_actions:", node.get("post_actions"))


if __name__ == "__main__":
    main()
