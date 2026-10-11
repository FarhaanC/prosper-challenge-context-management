"""One phone call: the tools the AI calls, and the call's working state.

Plain Python, no Pipecat (decision 22): the voice agent reaches these through
agent_builder, and the typed test loop will call them directly.

    session.py  Clinic (data every call shares, saved bookings) and CallSession
                (one call: booking card, options on offer, stage, call log)
    tools.py    the tools, their descriptions for the AI, and the stages each can move to
    silence.py  what the code says and does when the caller goes quiet, and the 10-minute cap
"""

from .session import (
    BOOKINGS_FILE, CALL_LOG_DIR, PLACEHOLDER, PLACEHOLDERS, BookingsFileError, CallSession, Clinic, read_bookings,
)
from .silence import CallWatch, Step
from .tools import TOOLS, Outcome, Tool, run_tool

__all__ = [
    "BOOKINGS_FILE", "CALL_LOG_DIR", "PLACEHOLDER", "PLACEHOLDERS", "BookingsFileError", "CallSession", "Clinic",
    "read_bookings", "TOOLS", "Outcome", "Tool", "run_tool", "CallWatch", "Step",
]
