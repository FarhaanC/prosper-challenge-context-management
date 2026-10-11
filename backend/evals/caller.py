"""The AI that plays the caller (decision 85: gpt-4o-mini, the same for every version).

It only hears what the agent says, never the tool calls or the agent's instructions.
It plays a short persona with a goal, and says [HANG UP] when the call is over.
"""

from __future__ import annotations

from .ai import OpenAIChat
from .agents import AgentTurn

HANG_UP = "[HANG UP]"
LONGEST_LINE = 200   # tokens: a caller's line is a sentence or two; the cap only stops a runaway reply

CALLER_RULES = f"""You are role-playing a person who is phoning a healthcare clinic's scheduling line. You are the CALLER, not the assistant: the other side of this conversation is the clinic's scheduling agent.

How to talk: like a real person on the phone. One or two short sentences at a time, no lists, no stage directions. Answer what the agent asks; don't announce everything at once. Use only the details below; if you're asked something they don't cover, say you're not sure. If the agent asks you to spell your name, spell it letter by letter with commas, for example "F, A, R, H, A, A, N". Dates of birth: say them naturally ("March 12th, 1984").

When the call is over (the agent has said goodbye, or you have said goodbye), reply with exactly {HANG_UP} and nothing else.

Who you are and what you want:
"""


class CallerAI:
    def __init__(self, ai: OpenAIChat, persona: str):
        self.ai = ai
        self.system = CALLER_RULES + persona
        self.messages: list = []   # from the caller's side: the agent is "user", the caller "assistant"
        self.cost = 0.0
        self.input_tokens = 0
        self.output_tokens = 0

    def next_line(self, agent_said: str) -> tuple:
        """(what the caller says, whether they hung up)."""
        self.messages.append({"role": "user", "content": agent_said or "(silence)"})
        reply = self.ai.reply([{"role": "system", "content": self.system}] + self.messages)
        self.cost += reply.cost
        self.input_tokens += reply.usage.input_tokens
        self.output_tokens += reply.usage.output_tokens
        text = reply.text.strip()
        self.messages.append({"role": "assistant", "content": text})
        hung_up = HANG_UP in text
        return text.replace(HANG_UP, "").strip(), hung_up


def heard(turn: AgentTurn) -> str:
    """Everything the agent said in one turn, as the caller hears it."""
    return " ".join(s.strip() for s in turn.said if s.strip())
