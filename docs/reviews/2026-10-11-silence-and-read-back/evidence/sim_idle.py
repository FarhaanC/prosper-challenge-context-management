"""Drive Pipecat 1.4's real UserIdleController the way bot.py relies on it."""
import asyncio
from pipecat.frames.frames import (BotStartedSpeakingFrame, BotStoppedSpeakingFrame, UserStartedSpeakingFrame,
                                   UserStoppedSpeakingFrame, UserIdleTimeoutUpdateFrame)
from pipecat.turns.user_idle_controller import UserIdleController
from pipecat.utils.asyncio.task_manager import TaskManager, TaskManagerParams

async def scenario(name, steps):
    c = UserIdleController(user_idle_timeout=0.2)   # 0.2 s stands for 20 s
    tm = TaskManager(); tm.setup(TaskManagerParams(loop=asyncio.get_running_loop()))
    await c.setup(tm)
    fired = []
    @c.event_handler("on_user_turn_idle")
    async def idle(_):
        fired.append(round(asyncio.get_running_loop().time() - t0, 2))
    t0 = asyncio.get_running_loop().time()
    for s in steps:
        if isinstance(s, float):
            await asyncio.sleep(s)
        else:
            await c.process_frame(s)
    await asyncio.sleep(1.0)
    print(f"{name}: idle event fired at {fired or 'never'}")
    await c.cleanup()

async def main():
    await scenario("greeting then silence", [BotStartedSpeakingFrame(), 0.05, BotStoppedSpeakingFrame()])
    await scenario("bot stops, caller makes a noise (no words, so no reply), then silence",
                   [BotStoppedSpeakingFrame(), 0.05, UserStartedSpeakingFrame(), 0.05, UserStoppedSpeakingFrame()])
    await scenario("check-in said with 0.15 wait queued first",
                   [UserIdleTimeoutUpdateFrame(timeout=0.15), BotStartedSpeakingFrame(), 0.05, BotStoppedSpeakingFrame()])

asyncio.run(main())
