"""Playwright end-to-end fixtures: a real uvicorn server (fresh SQLite DB, mock providers) and Chromium."""
import os
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

import httpx
import pytest
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
PW = "e2e-password-12345"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def base_url():
    port, tmp = _free_port(), tempfile.mkdtemp()
    env = {**os.environ, "APP_ENV": "development", "DATABASE_URL": f"sqlite:///{tmp}/e2e.db", "JWT_SECRET": "e2e-secret-e2e-secret-e2e-secret-1234",
           "LLM_PROVIDER": "heuristic", "EMAIL_PROVIDER": "mock", "WHATSAPP_PROVIDER": "mock", "CALENDAR_PROVIDER": "mock", "STT_PROVIDER": "none",
           "RUN_WORKER": "true", "WORKER_INTERVAL_SECONDS": "0.4", "LOG_JSON": "false", "UPLOAD_DIR": f"{tmp}/up", "SERVE_FRONTEND": "true"}
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port), "--log-level", "warning"], cwd=ROOT / "backend", env=env)
    url = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            if httpx.get(f"{url}/api/health", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.2)
    else:
        proc.kill()
        raise RuntimeError("server did not start")
    yield url
    proc.terminate()
    proc.wait(timeout=10)


@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


class Account:
    def __init__(self, base_url, email, token, wid):
        self.base_url, self.email, self.token, self.wid = base_url, email, token, wid
        self.h = {"Authorization": f"Bearer {token}"}

    def api(self, method, path, **kw):
        r = httpx.request(method, f"{self.base_url}/api/w/{self.wid}{path}", headers=self.h, timeout=20, **kw)
        assert r.status_code < 400, f"{method} {path}: {r.status_code} {r.text}"
        return r.json() if r.content else None


@pytest.fixture()
def account(base_url):
    email = f"u{uuid.uuid4().hex[:8]}@example.com"
    r = httpx.post(f"{base_url}/api/auth/register", json={"email": email, "name": "Eve Tester", "password": PW, "workspace_name": "E2E Co"}, timeout=20).json()
    return Account(base_url, email, r["token"], r["workspaces"][0]["id"])


class Page:
    """A page with error collection; tests assert the collections are empty."""

    def __init__(self, ctx, base_url):
        self.page = ctx.new_page()
        self.base_url, self.errors, self.failed = base_url, [], []
        self.page.on("console", lambda m: self.errors.append(m.text) if m.type == "error" else None)
        self.page.on("pageerror", lambda e: self.errors.append(str(e)))
        self.page.on("response", lambda r: self.failed.append(f"{r.status} {r.url}") if r.status >= 500 else None)

    def login(self, acct):
        self.page.goto(f"{self.base_url}/#/login")
        self.page.evaluate("(a) => { sessionStorage.setItem('maa.token', a.t); sessionStorage.setItem('maa.wid', a.w); }", {"t": acct.token, "w": str(acct.wid)})
        self.page.goto(f"{self.base_url}/#/dashboard")
        self.page.wait_for_selector(".shell")


@pytest.fixture()
def ui(browser, base_url):
    ctx = browser.new_context(viewport={"width": 1280, "height": 800})
    p = Page(ctx, base_url)
    yield p
    ctx.close()
