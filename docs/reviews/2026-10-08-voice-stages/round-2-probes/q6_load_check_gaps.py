"""S7: load-time checks that still let a typo through, or crash with a raw Python error."""
import copy
import json

from _setup import BACKEND

from agent_builder import AgentBuilder

AGENT = json.loads((BACKEND / "clinic_agent.json").read_text(encoding="utf-8"))


def node(d, name):
    return next(n for n in d["nodes"] if n["name"] == name)


def try_load(label, change):
    d = copy.deepcopy(AGENT)
    change(d)
    try:
        b = AgentBuilder.from_dict(d)
        booking = b._nodes_by_name.get("booking")
        print(f"LOADED   {label}" + (f"  (booking stage tools now: {booking.tools})" if booking else ""))
    except ValueError as e:
        print(f"refused  {label}: {str(e).splitlines()[-1]}")
    except Exception as e:  # noqa: BLE001
        print(f"CRASH    {label}: {type(e).__name__}: {e}")


def rename_tools(d):
    n = node(d, "booking")
    n["tool"] = n.pop("tools")


try_load("booking stage 'tools' misspelt 'tool'", rename_tools)
try_load("stage 'role_messages' (Pipecat's plural) with {today}",
         lambda d: node(d, "identify").__setitem__("role_messages", [{"role": "system", "content": "{today}"}]))
try_load("top-level 'global_tool' misspelt, plus a tool in the end stage",
         lambda d: (d.__setitem__("global_tool", d.pop("global_tools")), node(d, "end").__setitem__("tools", ["hand_off"]),
                    node(d, "identify")["tools"].append("hand_off")))
try_load("history as a list", lambda d: d.__setitem__("history", ["reset"]))
try_load("persona as a number", lambda d: d.__setitem__("persona", 5))
try_load("role_message as a list", lambda d: node(d, "identify").__setitem__("role_message", ["x"]))
try_load("a task message that's plain text", lambda d: node(d, "identify")["task_messages"].append("Say hello."))
try_load("doubled braces {{today}}", lambda d: node(d, "identify")["task_messages"][0].__setitem__(
    "content", node(d, "identify")["task_messages"][0]["content"] + " {{today}}"))
