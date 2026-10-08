"""S5: what the AI sees in the end stage after a hand-off, and the tools Pipecat Flows
still offers it there (Flows adds every global tool to every node: manager.py:662).
The only "caller intent" left in the reset context is the reason sentence, which
matches the hand_off tool's own trigger words."""
import asyncio
import json

from _setup import BACKEND, call

from agent_builder import AgentBuilder

b = AgentBuilder.from_json(BACKEND / "clinic_agent.json")
for reason in ("reschedule", "speak_to_staff"):
    s = call()

    class FM:
        state = {"session": s}

    first = b.build_initial_node(s)
    funcs = {f.name: f for f in [*first["functions"], *b.global_functions()]}
    _, end = asyncio.run(funcs["hand_off"].handler({"reason": reason}, FM()))
    print(f"--- end stage after hand_off({reason})")
    print("system (persona):", end["role_message"])
    print("developer:", json.dumps(end["task_messages"][0]["content"]))
    print("tools offered by Flows:", [f.name for f in b.global_functions()] + [f.name for f in end["functions"]])
print("--- hand_off's description, as the AI reads it:")
print(next(f.description for f in b.global_functions() if f.name == "hand_off"))
