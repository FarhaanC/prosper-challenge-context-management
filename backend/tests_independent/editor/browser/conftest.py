"""Browser test setup: a throwaway server per test (fresh copy of the agent file and of the
real call logs), and a fresh Chromium page (no remembered box positions).

Run with a Python that has Playwright and pytest, from this folder:
    VENV_PYTHON=<python with fastapi/uvicorn/pipecat> python3 -m pytest --confcutdir=. -q
"""

import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[2]
REPO = BACKEND.parent
DIST = REPO / "frontend" / "dist"
VENV_PYTHON = os.environ.get("VENV_PYTHON", sys.executable)
PORT = int(os.environ.get("EDITOR_TEST_PORT", "7871"))
SHOTS = HERE / "screenshots"


class Served:
    def __init__(self, root: Path):
        self.root = root
        self.agent_file = root / "clinic_agent.json"
        self.log_dir = root / "call_logs"
        self.url = f"http://127.0.0.1:{PORT}"

    def agent_bytes(self) -> bytes:
        return self.agent_file.read_bytes()


def _wait_for_port(port, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.1)
    raise RuntimeError(f"server didn't start on {port}")


def start_server(tmp_path: Path, agent_text: bytes = None, copy_logs: bool = True, env: dict = None) -> tuple:
    root = tmp_path / "served"
    root.mkdir()
    s = Served(root)
    s.agent_file.write_bytes(agent_text if agent_text is not None else (BACKEND / "clinic_agent.json").read_bytes())
    s.log_dir.mkdir()
    if copy_logs:
        for f in (BACKEND / "call_logs").glob("*.jsonl"):
            shutil.copy(f, s.log_dir / f.name)
    with socket.socket() as probe:
        assert probe.connect_ex(("127.0.0.1", PORT)) != 0, f"port {PORT} is busy"
    proc = subprocess.Popen([VENV_PYTHON, str(HERE / "serve.py"), str(BACKEND), str(DIST), str(s.agent_file),
                             str(s.log_dir), str(PORT)], cwd=str(root),
                            env={**os.environ, **(env or {})})
    _wait_for_port(PORT)
    return s, proc


@pytest.fixture
def served(tmp_path):
    s, proc = start_server(tmp_path)
    yield s
    proc.terminate()
    proc.wait(10)


@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture
def page(browser):
    context = browser.new_context(viewport={"width": 1600, "height": 1000})
    pg = context.new_page()
    pg.errors = []
    pg.on("pageerror", lambda e: pg.errors.append(str(e)))
    yield pg
    context.close()


def shot(page, name):
    SHOTS.mkdir(exist_ok=True)
    page.screenshot(path=str(SHOTS / f"{name}.png"))
