"""One AI reply from OpenAI, timed, costed and recorded.

The same request the voice agent's OpenAI service makes (messages, tools, one tool
call at a time, OpenAI's default settings), without streaming: the reply's timing
is the time to the whole reply, slightly longer than a voice call's wait for the
first words. Every version is timed the same way.

OpenAI's rate limit (tokens per minute) can make a request wait. Those waits are
not counted in the timing: they come from the account's limit, not the agent.
Running out of credit stops the run at once.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from .budget import NO_USAGE, ONE_REPLY_DOLLARS, Ledger, Usage, dollars

MAX_WAITS = 8          # rate-limit or connection waits for one request before giving up
LONGEST_WAIT = 60.0    # seconds; OpenAI's own retry-after is used when it gives one


class OutOfCredit(RuntimeError):
    """OpenAI says the account has no credit left."""


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str  # JSON text, exactly as the AI wrote it


@dataclass
class Reply:
    text: str
    tool_calls: list = field(default_factory=list)
    usage: Usage = NO_USAGE
    seconds: float = 0.0   # the successful request only, without rate-limit waits
    cost: float = 0.0


def openai_client(api_key: str):
    """OpenAI's client with its own retries off: this module waits and retries itself, so
    the timing of each reply never includes a wait."""
    from openai import OpenAI
    return OpenAI(api_key=api_key, max_retries=0, timeout=90)


def _wait_from(error) -> Optional[float]:
    """How long OpenAI asked us to wait, from its headers or its message."""
    response = getattr(error, "response", None)
    headers = getattr(response, "headers", None) or {}
    for key, scale in (("retry-after-ms", 0.001), ("retry-after", 1.0)):
        value = headers.get(key)
        if value:
            try:
                return float(value) * scale
            except ValueError:
                pass
    m = re.search(r"try again in (\d+(?:\.\d+)?)(ms|s)", str(error))
    if m:
        return float(m.group(1)) / (1000 if m.group(2) == "ms" else 1)
    return None


class OpenAIChat:
    """Asks one model for replies. `label` names the spender in the spending record."""

    def __init__(self, client, model: str, ledger: Ledger, label: str, max_tokens: Optional[int] = None,
                 sleep: Callable[[float], None] = time.sleep, say: Callable[[str], None] = print):
        """`max_tokens` caps each reply's length: set for the caller, left unset for the agents, as in the
        voice agent."""
        self.client = client
        self.model = model
        self.max_tokens = max_tokens
        self.ledger = ledger
        self.label = label
        self._sleep = sleep
        self._say = say

    def reply(self, messages: list, tools: Optional[list] = None, one_tool_at_a_time: bool = True) -> Reply:
        import openai

        dollars(self.model, NO_USAGE)  # an unpriced model is refused here, before anything is paid for
        self.ledger.check_room(ONE_REPLY_DOLLARS, f"the next {self.label} reply")
        params = {"model": self.model, "messages": messages}
        if self.max_tokens:
            params["max_tokens"] = self.max_tokens
        if tools:
            params["tools"] = tools
            if one_tool_at_a_time:
                params["parallel_tool_calls"] = False
        waits = 0
        while True:
            started = time.perf_counter()
            try:
                response = self.client.chat.completions.create(**params)
                seconds = time.perf_counter() - started
                break
            except openai.RateLimitError as e:
                if getattr(e, "code", None) == "insufficient_quota" or "insufficient_quota" in str(e):
                    raise OutOfCredit("OpenAI says the account has no credit left.") from e
                waits = self._wait(waits, _wait_from(e), "OpenAI's rate limit")
            except (openai.APIConnectionError, openai.InternalServerError) as e:
                waits = self._wait(waits, None, f"a connection problem ({type(e).__name__})")

        message = response.choices[0].message
        u = response.usage
        details = getattr(u, "prompt_tokens_details", None)
        usage = Usage(u.prompt_tokens, (getattr(details, "cached_tokens", 0) or 0) if details else 0,
                      u.completion_tokens)
        cost = self.ledger.record(self.model, usage, self.label)
        calls = [ToolCall(c.id, c.function.name, c.function.arguments) for c in (message.tool_calls or [])]
        return Reply(message.content or "", calls, usage, seconds, cost)

    def _wait(self, waits: int, asked: Optional[float], why: str) -> int:
        if waits >= MAX_WAITS:
            raise RuntimeError(f"Gave up after {MAX_WAITS} waits for {why}.")
        wait = min(asked if asked is not None else 2.0 * 2 ** waits, LONGEST_WAIT) + 0.5
        self._say(f"    waiting {wait:.0f}s for {why}")
        self._sleep(wait)
        return waits + 1


def tool_arguments(call: ToolCall) -> tuple:
    """(arguments as a dict, problem). The AI almost always writes valid JSON; if it doesn't,
    the problem goes back to it as the tool's result, as an error would in a call."""
    try:
        args = json.loads(call.arguments or "{}")
    except ValueError as e:
        return {}, f"The arguments weren't valid JSON: {e}"
    if not isinstance(args, dict):
        return {}, "The arguments must be a JSON object."
    return args, ""
