"""What the test runs cost, and the hard stop (decision 84).

Every AI reply's cost is worked out from OpenAI's own usage figures (input tokens,
the part of them OpenAI had already seen and charges less for, and output tokens)
and added to a spending record: one line per reply, in a file kept across runs, so
running the command again never forgets what was already spent.

Before each conversation the runner asks whether a whole conversation of that kind
still fits under the stop; before each AI request it checks there's room for one
more reply. If not, it stops and keeps what's finished.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

# The hard stop for the whole testing step, in US dollars (decision 84). Not a setting:
# raising it means changing this line, which shows in the record.
STOP_AT_DOLLARS = 7.00

# Room kept for one more AI reply before any request: the biggest single reply in these
# runs is a naive gpt-4o pass (about 12,000 input tokens, about $0.03), with margin.
ONE_REPLY_DOLLARS = 0.10

# US dollars per million tokens, OpenAI's standard prices for these models as far as we
# know (October 2026); "cached" is input OpenAI had already seen, charged at half price.
PRICES = {
    "gpt-4o": {"input": 2.50, "cached": 1.25, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "cached": 0.075, "output": 0.60},
}


class BudgetStop(RuntimeError):
    """There isn't room under the stop for what comes next."""


@dataclass(frozen=True)
class Usage:
    input_tokens: int
    cached_tokens: int
    output_tokens: int

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(self.input_tokens + other.input_tokens, self.cached_tokens + other.cached_tokens,
                     self.output_tokens + other.output_tokens)


NO_USAGE = Usage(0, 0, 0)


def dollars(model: str, usage: Usage) -> float:
    """The cost of one reply. An unknown model is an error, never a guess."""
    if model not in PRICES:
        raise ValueError(f"No price for model {model!r}; known: {', '.join(PRICES)}.")
    p = PRICES[model]
    fresh = usage.input_tokens - usage.cached_tokens
    return (fresh * p["input"] + usage.cached_tokens * p["cached"] + usage.output_tokens * p["output"]) / 1_000_000


class Ledger:
    """The spending record: one JSON line per AI reply, kept in `path` across runs."""

    def __init__(self, path: Path, stop_at: float = STOP_AT_DOLLARS):
        self.path = Path(path)
        self.stop_at = stop_at
        self.spent = 0.0
        if self.path.exists():
            for number, line in enumerate(self.path.read_text(encoding="utf-8").splitlines(), start=1):
                if not line.strip():
                    continue
                try:
                    self.spent += json.loads(line)["dollars"]
                except (ValueError, KeyError) as e:
                    raise ValueError(f"{self.path}, line {number}, can't be read (perhaps cut off when a run was "
                                     "stopped): fix or remove that line by hand. Spending is never guessed.") from e

    def check_room(self, needed: float, what: str) -> None:
        if self.spent + needed > self.stop_at:
            raise BudgetStop(f"Stopped before {what}: ${self.spent:.2f} spent of the ${self.stop_at:.2f} stop, "
                             f"and it may need up to ${needed:.2f}.")

    def record(self, model: str, usage: Usage, what: str) -> float:
        cost = dollars(model, usage)
        self.spent += cost
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"at": datetime.now().isoformat(timespec="seconds"), "model": model,
                                "input_tokens": usage.input_tokens, "cached_tokens": usage.cached_tokens,
                                "output_tokens": usage.output_tokens, "dollars": round(cost, 6),
                                "what": what}) + "\n")
        return cost
