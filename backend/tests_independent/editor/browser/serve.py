# Test helper: serve the editor's routes and built page the way bot.py does, without the
# voice agent. Usage: python serve.py <backend dir> <dist dir> <agent file> <log dir> <port>
import sys
from pathlib import Path

backend, dist, agent_file, log_dir, port = sys.argv[1:6]
sys.path.insert(0, backend)

import uvicorn  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.responses import HTMLResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from editor_api import editor_routes  # noqa: E402

app = FastAPI()

# For the "slow server" test: hold every inspector request this many seconds.
SLOW = float(__import__("os").environ.get("EDITOR_TEST_SLOW_LATEST", "0"))
if SLOW:
    import asyncio

    @app.middleware("http")
    async def slow_latest(request, call_next):
        if request.url.path.endswith("/calls/latest"):
            await asyncio.sleep(SLOW)
        return await call_next(request)
app.include_router(editor_routes(Path(agent_file), Path(log_dir)))
app.mount("/editor", StaticFiles(directory=dist, html=True), name="editor")


@app.get("/client/", response_class=HTMLResponse)
def client():
    return "<p id='stand-in'>(Pipecat's call page would be here)</p>"


uvicorn.run(app, host="127.0.0.1", port=int(port), log_level="warning")
