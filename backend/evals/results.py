"""The results tables and readable transcripts, rebuilt from the saved runs.

Only finished, scored runs count (the caller hung up, the agent said goodbye, or the turn
limit was reached); runs cut short by the budget stop or an error, or whose scoring failed,
are listed but left out.
"""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from pathlib import Path

from .budget import Ledger
from .conversation import FINISHED
from .scenarios import CHECK_IN_SCENARIO, SCENARIOS

LABELS = {
    "naive": "1. Naive: whole catalog, no checks (gpt-4o)",
    "naive_rules": "2. Naive + rule checks (gpt-4o)",
    "ours": "3. Ours: stages and small slices (gpt-4o)",
    "ours_mini": "3b. Ours on the smaller model (gpt-4o-mini)",
}
ORDER = list(LABELS)


def load_runs(results_dir: Path) -> list:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted((results_dir / "runs").glob("*/*.json"))]


def _row(label: str, runs: list) -> str:
    t = [r["totals"] for r in runs]
    passes = sum(x["agent_passes"] for x in t)
    tokens = sum(x["agent_input_tokens"] for x in t)
    cached = sum(x["agent_cached_tokens"] for x in t)
    slowest = [x["slowest_reply_seconds"] for x in t]
    passed = sum(1 for r in runs if r["score"]["passed"])
    return (f"| {label} | {passed} of {len(runs)} | {sum(r['score']['bad_bookings'] for r in runs)} "
            f"| {tokens / len(runs):,.0f} | {tokens / passes:,.0f} | {100 * cached / tokens:.0f}% "
            f"| {passes / len(runs):.1f} | {max(slowest):.1f} s ({statistics.median(slowest):.1f} s) "
            f"| ${sum(x['agent_cost'] for x in t) / len(runs):.3f} |")


TABLE_HEAD = ("| Version | Scenarios passed | Bad bookings | Input tokens per call | Input tokens per AI pass | Of which "
              "cached | AI passes per call | Slowest reply: worst (typical) | Agent cost per call |\n"
              "| --- | --- | --- | --- | --- | --- | --- | --- | --- |")


def build_results(results_dir: Path, ledger: Ledger) -> Path:
    runs = load_runs(results_dir)
    done = [r for r in runs if r["ended_by"] in FINISHED and r.get("score")]
    stopped = [r for r in runs if r not in done]
    by_version = defaultdict(list)
    for r in done:
        if r["scenario"] != CHECK_IN_SCENARIO.id:
            by_version[r["version"]].append(r)

    out = ["# Test results: AI-played callers against three versions of the agent (and ours on a smaller model)", "",
           "Built by `python -m evals.run results` from the saved runs in `runs/`. How the runs work, and why: "
           "`docs/decisions.md` 16, 20, 22, 68, 84-88. Each run is a typed call: an AI (gpt-4o-mini) plays the "
           "caller from a short persona; the agent is one of the versions below; the result is checked by code "
           "against what was saved.", "",
           "**Reading the columns.** *Scenarios passed*: the expected outcome, checked in code. *Bad bookings*: saved "
           "bookings that break a booking rule for the real caller. *Input tokens*: what the AI read, from "
           "OpenAI's usage figures (a token is roughly 3/4 of a word); *cached* is the part OpenAI had already "
           "seen and charges half for. *AI passes*: each time the AI read everything and replied. *Slowest "
           "reply*: the longest time from the caller's line to the agent's whole answer, AI and tool time only "
           "(a voice call adds about 1 s of speech); worst run, and the middle run in brackets. *Agent cost*: "
           "the agent's AI only, not the AI playing the caller.", ""]

    # Round 1 compares the versions on the same scenarios only: a scenario counts once every version that
    # has run has finished it (a budget stop part-way through could otherwise compare different sets).
    first = {v: [r for r in by_version[v] if r["run"] == 1] for v in ORDER}
    ran = [v for v in ORDER if first[v]]
    shared = set.intersection(*[{r["scenario"] for r in first[v]} for v in ran]) if ran else set()
    if shared:
        out += ["## All versions, on the same scenarios, each once (round 1)", "", TABLE_HEAD]
        out += [_row(LABELS[v], [r for r in first[v] if r["scenario"] in shared]) for v in ran]
        left_out = sorted({r["scenario"] for v in ran for r in first[v]} - shared)
        if left_out:
            out.append(f"\nLeft out because not every version has run them: {', '.join(left_out)}.")
        out.append("")
    if any(len(by_version[v]) > len(first[v]) for v in ("ours", "ours_mini")):
        out += ["## Our agent over every run (up to 3 per scenario)", "", TABLE_HEAD]
        out += [_row(LABELS[v], by_version[v]) for v in ("ours", "ours_mini") if by_version[v]]
        out.append("")

    out += ["## Passes by scenario (all runs)", "",
            "| Scenario | " + " | ".join(LABELS[v].split(":")[0].split(" (")[0] for v in ORDER) + " |",
            "| --- |" + " --- |" * len(ORDER)]
    for s in SCENARIOS:
        cells = []
        for v in ORDER:
            mine = [r for r in by_version[v] if r["scenario"] == s.id]
            cells.append(f"{sum(r['score']['passed'] for r in mine)} of {len(mine)}" if mine else "-")
        out.append(f"| {s.title} | " + " | ".join(cells) + " |")
    out.append("")

    check_in = [r for r in done if r["scenario"] == CHECK_IN_SCENARIO.id]
    if check_in:
        r = check_in[0]
        out += ["## The check-in after the read-back (decision 71)", "",
                f"{CHECK_IN_SCENARIO.title}: **{'pass' if r['score']['passed'] else 'fail'}**"
                + ("" if r["score"]["passed"] else f" ({' '.join(r['score']['reasons'])})"), ""]

    failed = [r for r in done if not r["score"]["passed"]]
    out += ["## Every failed run, and why", ""]
    out += [f"- {LABELS[r['version']]}, {r['scenario']}, run {r['run']}: {' '.join(r['score']['reasons'])}"
            for r in failed] or ["None."]
    out.append("")
    if stopped:
        out += ["## Runs not counted", ""]
        out += [f"- {r['version']}, {r['scenario']}, run {r['run']}: "
                + (r["ended_by"] if r["ended_by"] not in FINISHED else "scoring failed (see score_error)")
                for r in stopped]
        out.append("")
    out += DIFFERENCES

    by_model = defaultdict(float)
    if ledger.path.exists():
        for line in ledger.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                entry = json.loads(line)
                by_model[entry["model"]] += entry["dollars"]
    out += ["## Spending", "",
            f"${ledger.spent:.2f} of the ${ledger.stop_at:.2f} stop (decision 84): "
            + ", ".join(f"{m} ${d:.2f}" for m, d in sorted(by_model.items())) + ".", ""]

    path = results_dir / "results.md"
    path.write_text("\n".join(out), encoding="utf-8")
    _write_transcripts(results_dir, runs)
    return path


DIFFERENCES = [
    "## What else differs, besides what each version is given", "",
    "Said here so nobody has to find it in the code (independent review, 12 Oct, R7 and R15):", "",
    "- **Ours spells new patients' names back** letter by letter (decisions 59, 77). That's extra turns and tokens "
    "the naive versions don't spend.",
    "- **Ours ends the call itself** after its goodbye; the naive versions can't, so a caller who says goodbye "
    "without hanging up can cost them one more AI pass.",
    "- **Searching**: ours finds valid options in one code call; the naive versions' find_open_times returns times "
    "for one doctor, or for every doctor the catalog lists for a visit type, with no rule checks.",
    "", "## How these typed calls differ from a voice call", "",
    "- No speech: no mishearing, no talking over each other, no silence (the check-in is said by the loop in one "
    "run only).",
    "- Timing is to the whole written reply; in a call the voice starts after the first sentence, and speech adds "
    "about 1 s.",
    "- When the AI says something and calls a tool in one reply, the loop keeps them as two messages; Pipecat may "
    "keep one. A few tokens.",
    "- If the AI asks for two tools at once (it's told one at a time), the loop runs the first and notes it.", ""]


def _write_transcripts(results_dir: Path, runs: list) -> None:
    folder = results_dir / "transcripts"
    folder.mkdir(parents=True, exist_ok=True)
    by_version = defaultdict(list)
    for r in runs:
        by_version[r["version"]].append(r)
    for version, mine in by_version.items():
        lines = [f"# Transcripts: {LABELS[version]}", ""]
        for r in sorted(mine, key=lambda r: (r["scenario"], r["run"])):
            if r["ended_by"] not in FINISHED or not r.get("score"):
                verdict = "not counted: " + (r["ended_by"] if r["ended_by"] not in FINISHED else "scoring failed")
            else:
                verdict = "PASS" if r["score"]["passed"] else "FAIL: " + " ".join(r["score"]["reasons"])
            lines += [f"## {r['title']} (run {r['run']})", "", f"**{verdict}**", ""]
            if r["greeting"]:
                lines += _agent_lines(r["greeting"])
            for turn in r["turns"]:
                lines.append(f"> **Caller:** {turn['caller']}")
                lines.append("")
                if turn.get("agent"):
                    lines += _agent_lines(turn["agent"])
                if turn.get("check_in_said"):
                    lines += [f"**Agent (the code, after silence):** {turn['check_in_said']}", ""]
            t = r["totals"]
            lines += [f"*Ended by: {r['ended_by']}. {t['agent_passes']} AI passes, {t['agent_input_tokens']:,} input "
                      f"tokens, slowest reply {t['slowest_reply_seconds']:.1f} s, agent ${t['agent_cost']:.3f}.*",
                      "", "---", ""]
        (folder / f"{version}.md").write_text("\n".join(lines), encoding="utf-8")


def _agent_lines(turn: dict) -> list:
    """The agent's turn in the order it happened: what it said, and each tool it called."""
    lines = []
    for event in turn.get("order", []):
        if "said" in event:
            lines += [f"**Agent:** {event['said']}", ""]
        else:
            tool = turn["tools"][event["tool"]]
            result = json.dumps(tool["result"], ensure_ascii=False)
            lines += [f"- *tool* `{tool['tool']}` {json.dumps(tool['args'], ensure_ascii=False)} -> "
                      f"{result[:300] + ' ...' if len(result) > 300 else result}", ""]
    for problem in turn.get("problems", []):
        lines += [f"*Noticed: {problem}*", ""]
    return lines
