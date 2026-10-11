"""Silence, held calls and pocket dials (decision 64).

Plain Python, no Pipecat: agent_builder/call_watch.py connects this to Pipecat's
user-idle timer, and the typed test loop can ignore it (it has no silence).

- Silence is counted from when the agent stops speaking. After CHECK_IN_AFTER
  seconds of it, the code asks "Are you still there?".
- If the caller still says nothing for HANG_UP_AFTER seconds more, the code says
  a short goodbye and ends the call.
- When the caller says something (words, not just noise), the next count is the
  full CHECK_IN_AFTER again. A noise with no words gets no reply, so the count
  carries on from the end of the noise, and doesn't cancel a pending goodbye.
- Separately, every call ends after MAX_CALL_SECONDS, with its own goodbye,
  unless it's already finished (booked or handed to staff).

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
    """One call's silence count and time limit. Once it has hung up, it does nothing more.
    The timings can be shortened for tests; the call uses the constants above."""

    def __init__(self, check_in_after: float = CHECK_IN_AFTER, hang_up_after: float = HANG_UP_AFTER,
                 max_call_seconds: float = MAX_CALL_SECONDS) -> None:
        self.check_in_after = check_in_after
        self.hang_up_after = hang_up_after
        self.max_call_seconds = max_call_seconds
        self.checked_in = False   # "Are you still there?" said, and no words since
        self.ended = False        # the code has hung up (silence or time limit)

    def on_silence(self) -> Optional[Step]:
        """The caller has been silent for the current wait."""
        if self.ended:
            return None
        if not self.checked_in:
            self.checked_in = True
            return Step(CHECK_IN, hang_up=False, next_wait=self.hang_up_after)
        self.ended = True
        return Step(SILENCE_GOODBYE, hang_up=True)

    def on_caller_spoke(self) -> Optional[float]:
        """The caller said some words. Returns the wait to go back to, or None if it hasn't changed."""
        if self.checked_in and not self.ended:
            self.checked_in = False
            return self.check_in_after
        return None

    def on_time_limit(self, call_finished: bool) -> Optional[Step]:
        """The call has lasted max_call_seconds. A finished call (booked or handed to staff) is
        already saying its own goodbye, so it gets no second one."""
        if self.ended or call_finished:
            return None
        self.ended = True
        return Step(TIME_LIMIT_GOODBYE, hang_up=True)
