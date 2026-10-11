"""The scale test: does the design still work with a much bigger catalog?

    .venv\\Scripts\\python.exe -m evals.scale            # everything (about $0.30 of OpenAI)
    .venv\\Scripts\\python.exe -m evals.scale --free     # everything that costs nothing

1. A big fake catalog: the real 8 locations and 50 doctors, plus made-up ones up to
   500 locations and 2,000 doctors, with the same 82 visit types and booking rules.
   Made from a fixed seed, so it's the same every time. No made-up doctor is called
   Garcia, so "no Garcia does skin checks" stays true.
2. The code's search, timed on both catalogs (free): the choose_visit_type step, which
   runs the search for options, for the demo's cases.
3. What the AI is given, on both catalogs (free): the size of each stage's instructions
   for ours, and the naive version's one set of instructions.
4. The naive version's size in tokens, measured (free): one request with the big catalog,
   which OpenAI refuses as too large; its refusal says how many tokens it was.
5. Ours on the big catalog (paid, skipped with --free): two scenarios, one run each.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import statistics
import time
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from call import Clinic, run_tool
from clinic import Catalog, PatientDirectory, Schedule

from .agents import AGENT_FILE, DATA_DIR, OurAgent, naive_instructions
from .ai import OpenAIChat, openai_client
from .budget import Ledger
from .caller import CallerAI
from .conversation import FINISHED, run_conversation
from .run import CALLER_MODEL, NOW, RESULTS_DIR
from .scenarios import BOOKED, BY_ID, Expected
from .scoring import score

SCALE_DIR = RESULTS_DIR / "scale"
BIG_LOCATIONS, BIG_DOCTORS = 500, 2000
SEED = 2026
GPT_4O_LIMIT = 128_000   # tokens gpt-4o can read in one request

FIRST_NAMES = ["Aisha", "Ben", "Carla", "David", "Elena", "Farid", "Grace", "Hiro", "Ines", "Jamal", "Kavya", "Liam",
               "Mei", "Noah", "Olga", "Pedro", "Quinn", "Rosa", "Sam", "Tara", "Umar", "Vera", "Wen", "Yusuf", "Zoe"]
LAST_NAMES = ["Abbott", "Bauer", "Castro", "Dimitrov", "Evans", "Fischer", "Gupta", "Haddad", "Ito", "Jensen",
              "Kowalski", "Lopez", "Mensah", "Novak", "Okafor", "Patel", "Quiroga", "Reyes", "Silva", "Tanaka",
              "Ueda", "Varga", "Weber", "Xu", "Young", "Zhang"]   # no Garcia (see the top of this file)
NAME_START = ["Al", "Bren", "Cor", "Dun", "Elm", "Fen", "Gal", "Hol", "Ives", "Jor", "Kel", "Lor", "Mar", "Nor",
              "Ost", "Pel", "Quil", "Ros", "Sel", "Tam", "Ulm", "Ver", "Wil", "Yar"]
NAME_END = ["ford", "wick", "dale", "mont", "ridge", "haven", "brook", "field", "stead", "worth", "ton", "by"]
KINDS = ["Health Center", "Medical Group", "Care Center", "Community Clinic", "Specialty Center"]
HOURS = ["Mon-Fri 8:00-17:00", "Mon-Fri 9:00-18:00", "Mon-Sat 8:00-16:00"]
CAPABILITIES = ["lab", "imaging", "surgery", "physical_therapy", "dental"]
LANGUAGES = ["Spanish", "Mandarin", "Vietnamese", "Hindi", "Arabic", "Portuguese"]


def make_big_catalog(out_dir: Path, data_dir: Path = DATA_DIR) -> Path:
    """Write catalog.json, location_extras.json and visit_type_notes.json for the big catalog."""
    rng = random.Random(SEED)
    raw = json.loads((data_dir / "catalog.json").read_text(encoding="utf-8"))
    extras = json.loads((data_dir / "location_extras.json").read_text(encoding="utf-8"))
    places = [f"{a}{b}" for a in NAME_START for b in NAME_END]
    rng.shuffle(places)

    for i in range(len(raw["locations"]), BIG_LOCATIONS):
        place = places[i % len(places)]
        loc_id = f"loc_{i:03d}"
        raw["locations"].append({
            "id": loc_id, "name": f"{place} {KINDS[i % len(KINDS)]}",
            "address": f"{rng.randint(100, 9999)} {rng.choice(places)} Way", "city": "San Francisco",
            "phone": f"(415) 555-{rng.randint(0, 9999):04d}", "hours": rng.choice(HOURS),
            "capabilities": sorted(c for c in CAPABILITIES if rng.random() < 0.35)})
        extras["locations"][loc_id] = {"neighbourhood": place, "also_called": [],
                                       "lat": round(rng.uniform(37.71, 37.81), 4),
                                       "lon": round(rng.uniform(-122.51, -122.38), 4)}

    # Each specialty's doctors offer what the real catalog's doctors of that specialty offer.
    menus, weights = {}, {}
    for p in raw["providers"]:
        menus.setdefault(p["specialty"], set()).update(p["appointment_type_ids"])
        weights[p["specialty"]] = weights.get(p["specialty"], 0) + 1
    specialties = sorted(menus)
    location_ids = [loc["id"] for loc in raw["locations"]]
    for i in range(len(raw["providers"]), BIG_DOCTORS):
        specialty = rng.choices(specialties, [weights[s] for s in specialties])[0]
        raw["providers"].append({
            "id": f"prov_{i:04d}", "name": f"Dr. {rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}", "title": "MD",
            "specialty": specialty, "location_ids": sorted(rng.sample(location_ids, rng.randint(1, 4))),
            "accepting_new_patients": rng.random() < 0.7,
            "languages": ["English"] + ([rng.choice(LANGUAGES)] if rng.random() < 0.3 else []),
            "appointment_type_ids": sorted(menus[specialty])})

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "catalog.json").write_text(json.dumps(raw, indent=1), encoding="utf-8")
    (out_dir / "location_extras.json").write_text(json.dumps(extras, indent=1), encoding="utf-8")
    (out_dir / "visit_type_notes.json").write_bytes((data_dir / "visit_type_notes.json").read_bytes())
    return out_dir


# The demo's searches: (who, visit type, wishes sent with it).
SEARCHES = [
    ("James Wilson's knee MRI near Downtown", {"full_name": "James Wilson", "returning": True,
                                                "date_of_birth": "1984-03-12"},
     "appt_065", {"place": "Downtown", "near": True}),
    ("A new patient's skin check with Dr. Garcia", {"full_name": "Lena Park", "returning": False,
                                                     "spelled_first_name": "L, E, N, A",
                                                     "spelled_last_name": "P, A, R, K"},
     "appt_027", {"doctor_name": "Dr. Garcia"}),
    ("A new patient's check-up with Dr. Maria Garcia", {"full_name": "Priya Nair", "returning": False,
                                                         "spelled_first_name": "P, R, I, Y, A",
                                                         "spelled_last_name": "N, A, I, R"},
     "appt_002", {"doctor_name": "Dr. Maria Garcia"}),
]
REPEATS = 20


def time_searches(catalog: Catalog, patients: PatientDirectory) -> list:
    """Milliseconds for choose_visit_type (which runs the search), the middle of REPEATS tries, per case."""
    rows = []
    for title, who, visit_type, wishes in SEARCHES:
        times, sizes = [], []
        for _ in range(REPEATS):
            session = Clinic(catalog, patients, Schedule(catalog)).new_call(clock=lambda: NOW)
            assert run_tool(session, "start_booking", who).result["ok"], title
            started = time.perf_counter()
            outcome = run_tool(session, "choose_visit_type", {"visit_type_id": visit_type, **wishes})
            times.append((time.perf_counter() - started) * 1000)
            assert outcome.result["ok"], (title, outcome.result)
            sizes.append(len(session.fill("{options}")))
        rows.append({"search": title, "milliseconds": round(statistics.median(times), 1),
                     "options_text_characters": sizes[0]})
    return rows


def stage_sizes(catalog: Catalog, patients: PatientDirectory) -> dict:
    """Characters of instructions each stage of ours gives the AI, on James Wilson's knee MRI path,
    filled from the booking card exactly as at each stage move."""
    nodes = {n["name"]: n for n in json.loads(AGENT_FILE.read_text(encoding="utf-8"))["nodes"]}
    session = Clinic(catalog, patients, Schedule(catalog)).new_call(clock=lambda: NOW)

    def size(stage: str) -> int:
        return sum(len(session.fill(m["content"])) for m in nodes[stage]["task_messages"])

    sizes = {"identify": size("identify")}
    run_tool(session, "start_booking", {**SEARCHES[0][1], "specialty": "Radiology"})
    sizes["visit_type"] = size("visit_type")
    run_tool(session, "choose_visit_type", {"visit_type_id": SEARCHES[0][2], **SEARCHES[0][3]})
    sizes["booking"] = size("booking")
    return sizes


def naive_size_in_tokens(client, model: str, instructions: str) -> dict:
    """Ask OpenAI once with the naive instructions; it refuses a request that's too big and says how big.
    A refused request isn't charged. One token of reply at most, in case it's ever accepted."""
    import openai

    try:
        response = client.chat.completions.create(model=model, max_tokens=1,
                                                  messages=[{"role": "developer", "content": instructions}])
        return {"refused": False, "tokens": response.usage.prompt_tokens, "said": ""}
    except (openai.BadRequestError, openai.RateLimitError) as e:
        said = str(e)
        m = re.search(r"resulted in (\d+) tokens", said) or re.search(r"[Rr]equested (\d+)", said)
        return {"refused": True, "tokens": int(m.group(1)) if m else None, "said": said[:400]}
    except openai.APIConnectionError:
        return {"refused": None, "tokens": None, "said": "OpenAI couldn't be reached from here."}


def run_ours_on_big(big: Catalog, patients: PatientDirectory, client, ledger: Ledger) -> list:
    """Two scenarios, one run each, scored for what still holds on any catalog: the right visit type,
    a booking that passes every rule, and (Garcia) no doctor called Garcia."""
    rows = []
    for scenario_id in ("garcia_skin_check", "james_knee_mri_downtown"):
        scenario = BY_ID[scenario_id]
        scenario = replace(scenario, expected=Expected(BOOKED, scenario.expected.visit_types))
        path = SCALE_DIR / "runs" / f"{scenario_id}.json"
        if path.exists() and json.loads(path.read_text(encoding="utf-8"))["ended_by"] in FINISHED:
            rows.append(json.loads(path.read_text(encoding="utf-8")))
            continue
        ledger.check_room(0.40, f"ours on the big catalog ({scenario_id})")
        clinic = Clinic(big, patients, Schedule(big))
        agent = OurAgent(OpenAIChat(client, "gpt-4o", ledger, f"agent: scale {scenario_id}"), clinic, NOW)
        caller = CallerAI(OpenAIChat(client, CALLER_MODEL, ledger, f"caller: scale {scenario_id}"),
                          scenario.persona)
        record = {"version": "ours", "model": "gpt-4o", "scenario": scenario_id, "catalog": "big",
                  **run_conversation(agent, caller)}
        if record["ended_by"] in FINISHED:
            record["score"] = score(scenario, record, big, patients, NOW)
            if scenario_id == "garcia_skin_check":
                garcia = [b for b in record["outcome"]["bookings"]
                          if "garcia" in big.providers[b["provider_id"]].name.lower()]
                if garcia:
                    record["score"]["passed"] = False
                    record["score"]["reasons"].append("Booked a Dr. Garcia for a skin check.")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record, indent=1, ensure_ascii=False), encoding="utf-8")
        rows.append(record)
    return rows


def naive_first_pass_tokens():
    """From round 1: the input tokens of the naive version's first AI pass (its instructions, tools, the
    greeting and the caller's first line), measured by OpenAI. None until round 1 has run."""
    for path in sorted((RESULTS_DIR / "runs" / "naive").glob("*__run1.json")):
        run = json.loads(path.read_text(encoding="utf-8"))
        first = next((t["agent"] for t in run["turns"] if t.get("agent") and t["agent"]["passes"]), None)
        if first:
            return first["input_tokens"] / first["passes"]
    return None


def write_summary(report: dict) -> Path:
    """scale.md: the scale numbers in plain words."""
    c, s = report["catalogs"], report["ours_stage_characters"]
    n_chars = report["naive_instruction_characters"]
    lines = ["# Scale test", "", "Made by `python -m evals.scale` (see the top of `backend/evals/scale.py`).", "",
             f"Catalogs: the real one ({c['normal']['doctors']} doctors, {c['normal']['locations']} locations) and a "
             f"made-up big one ({c['big']['doctors']} doctors, {c['big']['locations']} locations), both with "
             f"{c['big']['visit_types']} visit types and the same rules.", "",
             "## What the AI is given", "",
             "| | Real catalog | Big catalog |", "| --- | --- | --- |"]
    for stage in ("identify", "visit_type", "booking"):
        lines.append(f"| Ours, {stage} stage (characters) | {s['normal'][stage]:,} | {s['big'][stage]:,} |")
    lines.append(f"| Naive, its one set of instructions (characters) | {n_chars['normal']:,} | {n_chars['big']:,} |")
    measured = report.get("naive_big_tokens", {}).get("tokens")
    first_pass = naive_first_pass_tokens()
    if measured:
        lines.append(f"| Naive, in tokens (big: measured by OpenAI's refusal) | | {measured:,} |")
    elif first_pass:
        estimate = first_pass / n_chars["normal"] * n_chars["big"]
        lines.append(f"| Naive, in tokens (real: round 1's first AI pass; big: worked out from the characters) "
                     f"| {first_pass:,.0f} | about {estimate:,.0f} |")
    lines += ["", f"gpt-4o reads at most {GPT_4O_LIMIT:,} tokens per request.", "",
              "## The code's search (choose_visit_type, which finds the options)", "",
              "| Search | Real catalog | Big catalog |", "| --- | --- | --- |"]
    for normal, big in zip(report["search_ms"]["normal"], report["search_ms"]["big"]):
        lines.append(f"| {normal['search']} | {normal['milliseconds']} ms | {big['milliseconds']} ms |")
    if report.get("ours_on_big"):
        lines += ["", "## Ours on the big catalog (real AI, one run each)", "",
                  "| Scenario | Result | AI passes | Input tokens per call | Input tokens per AI pass |",
                  "| --- | --- | --- | --- | --- |"]
        for r in report["ours_on_big"]:
            result = "not counted: " + r["ended_by"] if r["passed"] is None else (
                "pass" if r["passed"] else "fail: " + " ".join(r["reasons"]))
            per = r["agent_input_tokens"] / r["agent_passes"] if r["agent_passes"] else 0
            lines.append(f"| {r['scenario']} | {result} | {r['agent_passes']} | {r['agent_input_tokens']:,} "
                         f"| {per:,.0f} |")
    path = SCALE_DIR / "scale.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="The scale test (see the top of evals/scale.py).")
    parser.add_argument("--free", action="store_true", help="skip the paid part (ours on the big catalog)")
    args = parser.parse_args(argv)
    from dotenv import load_dotenv

    patients = PatientDirectory.load()
    normal = Catalog.load()
    big_dir = make_big_catalog(SCALE_DIR / "big-catalog")
    big = Catalog.load(big_dir)
    print(f"Big catalog: {len(big.providers)} doctors, {len(big.locations)} locations, "
          f"{len(big.visit_types)} visit types.")
    report = {"made_at": datetime.now().isoformat(timespec="seconds"),
              "catalogs": {"normal": {"doctors": len(normal.providers), "locations": len(normal.locations),
                                      "visit_types": len(normal.visit_types)},
                           "big": {"doctors": len(big.providers), "locations": len(big.locations),
                                   "visit_types": len(big.visit_types)}},
              "search_ms": {"normal": time_searches(normal, patients), "big": time_searches(big, patients)},
              "ours_stage_characters": {"normal": stage_sizes(normal, patients), "big": stage_sizes(big, patients)}}
    clinic = Clinic(normal, patients, Schedule(normal))
    report["naive_instruction_characters"] = {"normal": len(naive_instructions(clinic, NOW)),
                                              "big": len(naive_instructions(clinic, NOW, big_dir))}
    load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=True)
    key = os.environ.get("OPENAI_API_KEY")
    if key:
        client = openai_client(key)
        report["naive_big_tokens"] = naive_size_in_tokens(client, "gpt-4o", naive_instructions(clinic, NOW, big_dir))
        if not args.free:
            ledger = Ledger(RESULTS_DIR / "spending.jsonl")
            runs = run_ours_on_big(big, patients, client, ledger)
            report["ours_on_big"] = [{"scenario": r["scenario"], "ended_by": r["ended_by"],
                                      "passed": r.get("score", {}).get("passed"),
                                      "reasons": r.get("score", {}).get("reasons", []), **r["totals"]} for r in runs]
    else:
        print("No OPENAI_API_KEY in backend/.env: the token count and the paid runs are skipped.")
    (SCALE_DIR / "scale.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(f"Scale results: {write_summary(report)}")


if __name__ == "__main__":
    main()
