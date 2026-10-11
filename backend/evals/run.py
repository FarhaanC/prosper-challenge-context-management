"""The test runs (decisions 84-88). From the backend folder, in PowerShell:

    $env:PYTHONUTF8 = "1"
    .venv\\Scripts\\python.exe -m evals.run plan      # checks everything, spends nothing
    .venv\\Scripts\\python.exe -m evals.run smoke     # 1 scenario on all 4 versions (part of round 1)
    .venv\\Scripts\\python.exe -m evals.run round1    # every scenario once, all 4 versions, + the check-in check
    .venv\\Scripts\\python.exe -m evals.run round2    # ours only (both models), second run
    .venv\\Scripts\\python.exe -m evals.run round3    # ours only, third run
    .venv\\Scripts\\python.exe -m evals.run all       # round1, round2, round3, in that order
    .venv\\Scripts\\python.exe -m evals.run results   # rebuild the results tables only

A finished run is never run again, so any command can be repeated after a stop: it carries
on where it left off. Every run is saved in docs/results/2026-10-12-testing/runs/, and the
results tables are rebuilt after every command.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from call import Clinic
from clinic import Catalog, PatientDirectory, Schedule

from .agents import AGENT_FILE, BACKEND_DIR, NaiveAgent, OurAgent
from .ai import OpenAIChat, openai_client
from .budget import Ledger
from .caller import CallerAI
from .conversation import FINISHED, run_conversation
from .results import build_results
from .scenarios import CHECK_IN_SCENARIO, SCENARIOS, Scenario
from .scoring import score

RESULTS_DIR = BACKEND_DIR.parent / "docs" / "results" / "2026-10-12-testing"

# Every run happens at the same clinic time, so every run sees the same open times:
# Tuesday 13 October 2026, 9 AM in San Francisco.
NOW = datetime(2026, 10, 13, 9, 0)

CALLER_MODEL = "gpt-4o-mini"   # decision 85

# Each version, and the model its agent runs on (decisions 16 and 68).
VERSIONS = {
    "naive": "gpt-4o",
    "naive_rules": "gpt-4o",
    "ours": "gpt-4o",
    "ours_mini": "gpt-4o-mini",
}

# What one whole conversation may cost before any of that version has run (agent plus
# caller, in dollars), used to check it fits under the stop. Afterwards the most a
# finished conversation of that version actually cost, plus 30%, is used if higher.
FIRST_GUESS = {"naive": 0.60, "naive_rules": 0.60, "ours": 0.25, "ours_mini": 0.04}

ROUNDS = {
    "smoke": [(s, v, 1) for s in SCENARIOS if s.id == "james_knee_mri_downtown" for v in VERSIONS],
    "round1": ([(s, v, 1) for s in SCENARIOS for v in VERSIONS]  # scenario by scenario, so a stop leaves
               + [(CHECK_IN_SCENARIO, "ours", 1)]),              # every version compared on the same ones
    "round2": [(s, v, 2) for s in SCENARIOS for v in ("ours", "ours_mini")],
    "round3": [(s, v, 3) for s in SCENARIOS for v in ("ours", "ours_mini")],
}
ROUNDS["all"] = ROUNDS["round1"] + ROUNDS["round2"] + ROUNDS["round3"]


def run_path(version: str, scenario: Scenario, number: int) -> Path:
    return RESULTS_DIR / "runs" / version / f"{scenario.id}__run{number}.json"


def finished(path: Path) -> bool:
    return path.exists() and json.loads(path.read_text(encoding="utf-8"))["ended_by"] in FINISHED


def make_agent(version: str, ai: OpenAIChat, clinic: Clinic):
    if version in ("ours", "ours_mini"):
        return OurAgent(ai, clinic, NOW)
    return NaiveAgent(ai, clinic, NOW, checks=(version == "naive_rules"))


def most_spent(version: str) -> float:
    """The most one finished conversation of this version has cost so far (agent plus caller)."""
    costs = []
    for path in (RESULTS_DIR / "runs" / version).glob("*.json"):
        run = json.loads(path.read_text(encoding="utf-8"))
        if run["ended_by"] in FINISHED:
            costs.append(run["totals"]["agent_cost"] + run["totals"]["caller_cost"])
    return max(costs, default=0.0)


def one_run(scenario: Scenario, version: str, number: int, client, ledger: Ledger,
            catalog: Catalog, patients: PatientDirectory) -> dict:
    path = run_path(version, scenario, number)
    path.parent.mkdir(parents=True, exist_ok=True)
    label = f"{version} {scenario.id} run {number}"
    with tempfile.TemporaryDirectory() as tmp:
        clinic = Clinic(catalog, patients, Schedule(catalog), bookings_file=Path(tmp) / "bookings.jsonl",
                        log_dir=path.parent / "call-logs" if version.startswith("ours") else None)
        agent = make_agent(version, OpenAIChat(client, VERSIONS[version], ledger, f"agent: {label}"), clinic)
        caller = CallerAI(OpenAIChat(client, CALLER_MODEL, ledger, f"caller: {label}"), scenario.persona)
        record = run_conversation(agent, caller, scenario.check_in_after_read_back)
    record = {"version": version, "model": VERSIONS[version], "caller_model": CALLER_MODEL,
              "scenario": scenario.id, "title": scenario.title, "run": number,
              "clinic_time": NOW.isoformat(timespec="minutes"),
              "ran_at": datetime.now().isoformat(timespec="seconds"), **record}
    if record["ended_by"] in FINISHED:
        record["score"] = score(scenario, record, catalog, patients, NOW)
    path.write_text(json.dumps(record, indent=1, ensure_ascii=False), encoding="utf-8")
    return record


def run_round(name: str, ledger: Ledger) -> None:
    from dotenv import load_dotenv

    load_dotenv(BACKEND_DIR / ".env", override=True)
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        sys.exit("No OPENAI_API_KEY in backend/.env.")
    client = openai_client(key)
    catalog, patients = Catalog.load(), PatientDirectory.load()
    todo = [(s, v, n) for s, v, n in ROUNDS[name] if not finished(run_path(v, s, n))]
    print(f"{name}: {len(todo)} conversation(s) to run, ${ledger.spent:.2f} spent of the ${ledger.stop_at:.2f} stop.")
    for i, (scenario, version, number) in enumerate(todo, start=1):
        need = max(FIRST_GUESS[version], most_spent(version) * 1.3)
        if ledger.spent + need > ledger.stop_at:
            print(f"Budget stop: ${ledger.spent:.2f} spent, and the next conversation ({version}) may cost up to "
                  f"${need:.2f}. Nothing more is run.")
            return
        print(f"[{i}/{len(todo)}] {version}, {scenario.id}, run {number} ...", flush=True)
        run = one_run(scenario, version, number, client, ledger, catalog, patients)
        t = run["totals"]
        if run["ended_by"] not in FINISHED:
            print(f"    STOPPED ({run['ended_by']}): {run['stopped_because'].strip().splitlines()[-1]}")
            print(f"    ${ledger.spent:.2f} spent. Saved what was done; nothing more is run.")
            return
        verdict = "PASS" if run["score"]["passed"] else "FAIL: " + run["score"]["reasons"][0]
        print(f"    {verdict}\n    {t['agent_passes']} AI passes, {t['agent_input_tokens']:,} input tokens, "
              f"slowest reply {t['slowest_reply_seconds']:.1f} s, ${t['agent_cost'] + t['caller_cost']:.3f}; "
              f"${ledger.spent:.2f} spent of ${ledger.stop_at:.2f}", flush=True)


def plan(ledger: Ledger) -> None:
    """Check everything a run needs, and say what each command would do. Spends nothing."""
    from dotenv import load_dotenv

    load_dotenv(BACKEND_DIR / ".env", override=True)
    print("Key in backend/.env:", "found" if os.environ.get("OPENAI_API_KEY") else "MISSING")
    catalog, patients = Catalog.load(), PatientDirectory.load()
    print(f"Catalog: {len(catalog.providers)} doctors, {len(catalog.locations)} locations, "
          f"{len(catalog.visit_types)} visit types; {len(patients.records)} fake patients.")
    try:
        from agent_builder import AgentBuilder
        AgentBuilder.from_json(AGENT_FILE)
        print("Agent file: clinic_agent.json passes the voice agent's own checks.")
    except ImportError:
        print("Agent file: the voice agent's checks need Pipecat, not installed here (skipped).")
    print(f"Clinic time for every run: {NOW:%A %d %B %Y, %H:%M} (San Francisco).")
    print(f"Spent so far: ${ledger.spent:.2f} of the ${ledger.stop_at:.2f} stop.")
    for name, items in ROUNDS.items():
        todo = [(s, v, n) for s, v, n in items if not finished(run_path(v, s, n))]
        guess = sum(max(FIRST_GUESS[v], most_spent(v) * 1.3) for _, v, _ in todo)
        print(f"  {name}: {len(todo)} of {len(items)} conversation(s) still to run, up to about ${guess:.2f}.")


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="The typed test runs (see docs/decisions.md 84-88).")
    parser.add_argument("command", choices=["plan", "results", *ROUNDS])
    args = parser.parse_args(argv)
    ledger = Ledger(RESULTS_DIR / "spending.jsonl")
    if args.command == "plan":
        plan(ledger)
        return
    if args.command != "results":
        run_round(args.command, ledger)
    out = build_results(RESULTS_DIR, ledger)
    print(f"Results: {out}")


if __name__ == "__main__":
    main()
