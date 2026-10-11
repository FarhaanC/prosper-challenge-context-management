"""Silence, held calls and pocket dials (decision 64).

Plain Python, no Pipecat: bot.py connects this to Pipecat's user-idle timer, and
the typed test loop can ignore it (it has no silence).

- After CHECK_IN_AFTER seconds of silence, counted from when the agent stops
  speaking, the code asks "Are you still there?".
- If the caller still says nothing for HANG_UP_AFTER seconds more, the code says
  a short goodbye and ends the call.
- Anything the caller says starts the count again from CHECK_IN_AFTER.
- Separately, every call ends after MAX_CALL_SECONDS, with its own goodbye.

Why: the AI costs nothing while it waits, but the speech services keep running,
and Pipecat on its own only ends a silent call after 5 minutes. On a pocket dial,
background noise can be heard as speech and set off paid AI replies.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

CHECK_IN_AFTER = 20.0          # seconds of silence before "Are you still there?"
HANG_UP_AFTER = 15.0           # seconds more before the goodbye
MAX_CALL_SECONDS = 10 * 60     # every call ends after 10 minutes

CHECK_IN = "Are you still there?"
SILENCE_GOODBYE = "I haven't heard anything, so I'll end the call now. Please call back any time. Goodbye."
TIME_LIMIT_GOODBYE = ("I'm sorry, we've reached the time limit for this call. "
                      "Please call back if you still need help. Goodbye.")


@dataclass
class Step:
    """What the code does now: say this, then either hang up or wait next_wait seconds."""

    say: str
    hang_up: bool
    next_wait: Optional[float] = None


class CallWatch:
    """One call's silence count and time limit. Once it has hung up, it does nothing more."""

    def __init__(self) -> None:
        self.checked_in = False   # "Are you still there?" said, and no reply yet
        self.ended = False        # the code has hung up (silence or time limit)

    def on_silence(self) -> Optional[Step]:
        """The caller has been silent for the current wait."""
        if self.ended:
            return None
        if not self.checked_in:
            self.checked_in = True
            return Step(CHECK_IN, hang_up=False, next_wait=HANG_UP_AFTER)
        self.ended = True
        return Step(SILENCE_GOODBYE, hang_up=True)

    def on_caller_spoke(self) -> Optional[float]:
        """The caller said something. Returns the wait to go back to, or None if it hasn't changed."""
        if self.checked_in and not self.ended:
            self.checked_in = False
            return CHECK_IN_AFTER
        return None

    def on_time_limit(self) -> Optional[Step]:
        """The call has lasted MAX_CALL_SECONDS."""
        if self.ended:
            return None
        self.ended = True
        return Step(TIME_LIMIT_GOODBYE, hang_up=True)
