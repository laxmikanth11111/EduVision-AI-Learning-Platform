"""Real-browser E2E for EduVision AI: learner journey + cross-user isolation.

Runs the actual FastAPI app in-process (uvicorn thread) against a dedicated
PostgreSQL database, and drives real headless Chrome via Playwright.

Env vars are set BEFORE app import so Settings picks them up.
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
import threading
import time
import traceback
import uuid
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
CHROME = os.environ.get(
    "E2E_CHROME_PATH",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
)
PORT = int(os.environ.get("E2E_PORT", "8099"))
BASE = f"http://127.0.0.1:{PORT}"
DB_URL = os.environ.get(
    "E2E_DATABASE_URL",
    "postgresql+asyncpg://eduvision:eduvision@127.0.0.1:55432/eduvision_e2e",
)
REDIS = os.environ.get("E2E_REDIS_HOSTPORT", "127.0.0.1:6380")

os.environ["PYTHONPATH"] = str(BACKEND)
os.environ["DATABASE_URL"] = DB_URL
os.environ["APP_SECRET_KEY"] = "browser-e2e-app-secret-key-000000000000000000"
os.environ["JWT_SECRET_KEY"] = "browser-e2e-jwt-secret-key-000000000000000000"
os.environ["COOKIE_SECURE"] = "false"
os.environ["CELERY_TASK_ALWAYS_EAGER"] = "true"
os.environ["AI_PROVIDER"] = "local"
os.environ["LOG_LEVEL"] = "WARNING"
os.environ["ENVIRONMENT"] = "test"
os.environ["STORAGE_PROVIDER"] = "local"
os.environ["ALLOW_AI_FALLBACK"] = "false"
os.environ["REDIS_URL"] = f"redis://{REDIS}/0"
os.environ["CELERY_BROKER_URL"] = f"redis://{REDIS}/1"
os.environ["CELERY_RESULT_BACKEND"] = f"redis://{REDIS}/2"
os.chdir(BACKEND)
sys.path.insert(0, str(BACKEND))

RESULTS: list[tuple[str, bool, str]] = []
CONSOLE: dict[str, list[str]] = {}


def record(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" :: {detail}" if detail else ""), flush=True)


def step(name):
    def deco(fn):
        def wrapper(*a, **kw):
            try:
                fn(*a, **kw)
            except Exception as exc:  # noqa: BLE001
                record(name, False, f"{type(exc).__name__}: {exc}")
                traceback.print_exc()
        wrapper.__name__ = fn.__name__
        return wrapper
    return deco


def watch(page, tag: str) -> None:
    CONSOLE.setdefault(tag, [])
    page.on("console", lambda m: CONSOLE[tag].append(f"{m.type}: {m.text[:160]}")
            if m.type in ("error", "warning") else None)
    page.on("pageerror", lambda e: CONSOLE[tag].append(f"pageerror: {str(e)[:200]}"))
    page.on("requestfailed", lambda r: CONSOLE[tag].append(
        f"reqfail: {r.method} {r.url[:120]}"))


def settle(page, tries: int = 25, pause: float = 0.6) -> str:
    """Wait until the page stops navigating (app does multi-step redirects)."""
    last = None
    stable = 0
    for _ in range(tries):
        try:
            cur = page.url
        except Exception:
            cur = "?"
        if cur == last:
            stable += 1
            if stable >= 3:
                break
        else:
            stable = 0
            last = cur
        time.sleep(pause)
    with contextlib.suppress(Exception):
        page.wait_for_load_state("domcontentloaded", timeout=15000)
    return page.url


def main() -> int:
    import uvicorn

    from app.main import app as fastapi_app

    cfg = uvicorn.Config(fastapi_app, host="127.0.0.1", port=PORT,
                         log_level="critical", access_log=False)
    server = uvicorn.Server(cfg)
    threading.Thread(target=server.run, daemon=True).start()

    import urllib.request
    last = ""
    for _ in range(120):
        try:
            with urllib.request.urlopen(f"{BASE}/api/v1/health/live", timeout=2) as r:
                if r.status == 200:
                    break
                last = f"status={r.status} body={r.read()[:200]!r}"
        except Exception as exc:
            last = f"{type(exc).__name__}: {exc}"
        time.sleep(1)
    else:
        print(f"SERVER DID NOT START: {last}", flush=True)
        return 2
    print("server up", flush=True)

    from playwright.sync_api import sync_playwright

    ua = f"e2e_{uuid.uuid4().hex[:8]}@example.com"
    ub = f"e2e_{uuid.uuid4().hex[:8]}@example.com"
    pw = f"Str0ngPassw0rd!{uuid.uuid4().hex[:6]}"
    pres_id: str | None = None

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, executable_path=CHROME)
        ctx_a = browser.new_context()
        ctx_b = browser.new_context()
        page_a = ctx_a.new_page()
        page_b = ctx_b.new_page()
        watch(page_a, "A")
        watch(page_b, "B")

        @step("A: signup via real signup.html form")
        def _signup_a():
            page_a.goto(f"{BASE}/frontend/signup.html", wait_until="domcontentloaded")
            page_a.fill("#name", "Alice Learner")
            page_a.fill("#email", ua)
            page_a.fill("#password", pw)
            page_a.check("#terms")
            page_a.click("#submitBtn")
            page_a.wait_for_function(
                "() => !!localStorage.getItem('access_token')", timeout=20000)
            tok = page_a.evaluate("() => localStorage.getItem('access_token')")
            record("A: signup via real signup.html form", bool(tok),
                   f"token_len={len(tok or '')}")

        @step("B: signup via real signup.html form")
        def _signup_b():
            page_b.goto(f"{BASE}/frontend/signup.html", wait_until="domcontentloaded")
            page_b.fill("#name", "Mallory Intruder")
            page_b.fill("#email", ub)
            page_b.fill("#password", pw)
            page_b.check("#terms")
            page_b.click("#submitBtn")
            page_b.wait_for_function(
                "() => !!localStorage.getItem('access_token')", timeout=20000)
            record("B: signup via real signup.html form", True)

        @step("A: create presentation through live API from browser session")
        def _create():
            nonlocal pres_id
            settle(page_a)
            out = page_a.evaluate("""async () => {
                const t = localStorage.getItem('access_token');
                const r = await fetch('/api/v1/presentations/manual', {
                  method: 'POST',
                  headers: {'Content-Type':'application/json',
                            'Authorization': 'Bearer ' + t},
                  body: JSON.stringify({title: 'Secret Deck Alpha',
                                         topics: ['Photosynthesis','Cell Biology']})
                });
                return {status: r.status, body: await r.text()};
            }""")
            ok = out["status"] in (200, 201)
            raw = out["body"]
            try:
                parsed = json.loads(raw)
            except Exception:
                parsed = {}
            payload = parsed.get("data", parsed) if isinstance(parsed, dict) else {}
            if ok:
                pres_id = payload.get("id") or payload.get("public_id")
            record("A: create presentation through live API from browser session",
                   bool(ok and pres_id),
                   f"status={out['status']} id={pres_id} keys={sorted(payload)[:8]} raw={raw[:180]}")

        @step("A: dashboard.html renders A's presentation in DOM")
        def _dash_a():
            page_a.goto(f"{BASE}/frontend/dashboard.html", wait_until="domcontentloaded")
            page_a.wait_for_function(
                "() => document.body.innerText.includes('Secret Deck Alpha')",
                timeout=25000)
            record("A: dashboard.html renders A's presentation in DOM", True)

        @step("A: player.html loads A's deck and reports slides")
        def _player_a():
            page_a.goto(f"{BASE}/frontend/player.html?pres_id={pres_id}",
                        wait_until="domcontentloaded")
            settle(page_a)
            page_a.wait_for_timeout(4000)
            counter = page_a.inner_text("#counter") if page_a.query_selector("#counter") else ""
            deck = page_a.inner_text("#deckName") if page_a.query_selector("#deckName") else ""
            body = page_a.inner_text("body")
            ok = "Secret Deck Alpha" in body or "Photosynthesis" in body
            record("A: player.html loads A's deck and reports slides", ok,
                   f"counter={counter!r} deck={deck!r}")

        @step("B: dashboard.html does NOT leak A's presentation")
        def _dash_b():
            settle(page_b)
            page_b.goto(f"{BASE}/frontend/dashboard.html", wait_until="domcontentloaded")
            settle(page_b)
            page_b.wait_for_timeout(4000)
            txt = page_b.inner_text("body")
            leaked = "Secret Deck Alpha" in txt
            record("B: dashboard.html does NOT leak A's presentation", not leaked,
                   f"leaked={leaked} url={page_b.url}")

        @step("B: API GET A's presentation is rejected (404/403)")
        def _api_b():
            out = page_b.evaluate("""async (pid) => {
                const t = localStorage.getItem('access_token');
                const r = await fetch('/api/v1/presentations/' + pid,
                    {headers: {'Authorization': 'Bearer ' + t}});
                return {status: r.status, body: (await r.text()).slice(0, 200)};
            }""", pres_id)
            ok = out["status"] in (401, 403, 404)
            record("B: API GET A's presentation is rejected (404/403)", ok,
                   f"status={out['status']} body={out['body'][:120]}")

        @step("B: player.html direct-nav to A's deck does not render A's content")
        def _player_b():
            page_b.goto(f"{BASE}/frontend/player.html?pres_id={pres_id}",
                        wait_until="domcontentloaded")
            settle(page_b)
            page_b.wait_for_timeout(4000)
            txt = page_b.inner_text("body")
            leaked = "Secret Deck Alpha" in txt or "Photosynthesis" in txt
            record("B: player.html direct-nav to A's deck does not render A's content",
                   not leaked, f"leaked={leaked} pres_id={pres_id}")

        @step("A: logout clears session and blocks protected API")
        def _logout():
            page_a.goto(f"{BASE}/frontend/dashboard.html", wait_until="domcontentloaded")
            page_a.wait_for_timeout(2500)
            if page_a.query_selector("#logoutBtn"):
                page_a.click("#logoutBtn")
                page_a.wait_for_timeout(3000)
            tok = page_a.evaluate("() => localStorage.getItem('access_token')")
            out = page_a.evaluate("""async () => {
                const t = localStorage.getItem('access_token');
                const r = await fetch('/api/v1/auth/me',
                    {headers: t ? {'Authorization':'Bearer '+t} : {}});
                return r.status;
            }""")
            ok = (tok is None) or out in (401, 403)
            record("A: logout clears session and blocks protected API", ok,
                   f"token_after={tok!r} me_status={out}")

        for fn in (_signup_a, _signup_b, _create, _dash_a, _player_a,
                   _dash_b, _api_b, _player_b, _logout):
            fn()

        browser.close()

    print("\n===== CONSOLE / NETWORK NOISE =====", flush=True)
    for tag, msgs in CONSOLE.items():
        uniq = list(dict.fromkeys(msgs))[:12]
        print(f"--- context {tag} ({len(msgs)} msgs) ---", flush=True)
        for m in uniq:
            print("   ", m, flush=True)

    print("\n===== SUMMARY =====", flush=True)
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    print(f"{passed}/{len(RESULTS)} browser E2E checks passed", flush=True)
    for n, ok, d in RESULTS:
        if not ok:
            print(f"  FAILED: {n} :: {d}", flush=True)
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
