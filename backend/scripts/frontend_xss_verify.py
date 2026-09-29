"""Real-browser verification of the player.html DOM-XSS hardening.

Loads the actual frontend page in headless Chrome and exercises the real
helper functions against known payloads, then proves that the sanitized
output cannot execute script when inserted via innerHTML.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
import uuid
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
CHROME = os.environ.get(
    "E2E_CHROME_PATH",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
)
PORT = int(os.environ.get("E2E_PORT", "8100"))
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
os.environ["LOG_LEVEL"] = "ERROR"
os.environ["ENVIRONMENT"] = "test"
os.environ["STORAGE_PROVIDER"] = "local"
os.environ["REDIS_URL"] = f"redis://{REDIS}/0"
os.environ["CELERY_BROKER_URL"] = f"redis://{REDIS}/1"
os.environ["CELERY_RESULT_BACKEND"] = f"redis://{REDIS}/2"
os.chdir(BACKEND)
sys.path.insert(0, str(BACKEND))

RESULTS: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" :: {detail}" if detail else ""), flush=True)


def main() -> int:
    import uvicorn

    from app.main import app as fastapi_app

    cfg = uvicorn.Config(fastapi_app, host="127.0.0.1", port=PORT,
                         log_level="critical", access_log=False)
    server = uvicorn.Server(cfg)
    threading.Thread(target=server.run, daemon=True).start()

    import urllib.request
    for _ in range(120):
        try:
            with urllib.request.urlopen(f"{BASE}/api/v1/health/live", timeout=2) as r:
                if r.status == 200:
                    break
        except Exception:
            time.sleep(1)
    else:
        print("SERVER DID NOT START", flush=True)
        return 2

    from playwright.sync_api import sync_playwright

    # The player page redirects anonymous visitors away and also bounces when no
    # `lesson` param is present, so seed a real session plus the param.
    token = ""
    user_obj: dict = {}
    try:
        with urllib.request.urlopen(
            urllib.request.Request(
                f"{BASE}/api/v1/auth/register",
                data=json.dumps({
                    "name": "XSS Probe",
                    "email": f"xss_{uuid.uuid4().hex[:8]}@example.com",
                    "password": "Str0ngPassw0rd!123",
                }).encode(),
                headers={"Content-Type": "application/json"},
            ),
            timeout=20,
        ) as r:
            payload = json.loads(r.read())
            token = payload["tokens"]["access_token"]
            user_obj = payload.get("user") or {
                "id": payload.get("user_id", "probe"), "name": "XSS Probe"}
    except Exception as exc:  # noqa: BLE001
        print(f"could not mint session: {exc}", flush=True)

    src = (BACKEND / "frontend" / "player.html").read_text(encoding="utf-8")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, executable_path=CHROME)
        page = browser.new_page()
        init = (
            "(() => { try {"
            f" localStorage.setItem('access_token', {json.dumps(token)});"
            f" localStorage.setItem('user', {json.dumps(json.dumps(user_obj))});"
            " } catch (e) {} })()"
        )
        page.add_init_script(init)
        page.goto(f"{BASE}/frontend/player.html?lesson=probe-lesson",
                  wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        record("player.html stayed on the player page",
               "player.html" in page.url, page.url)

        helpers = page.evaluate(
            "() => ({esc: typeof escHtml, san: typeof sanitizeSvgMarkup})")
        record("player.html exposes escHtml + sanitizeSvgMarkup",
               helpers["esc"] == "function" and helpers["san"] == "function",
               json.dumps(helpers))

        out = page.evaluate("""() => {
            const P1 = 'x" onmouseover="alert(1)';
            const P2 = "y' onclick='alert(2)";
            const P3 = 'z</span><img src=x onerror=alert(3)>';
            return {q: escHtml(P1), s: escHtml(P2), t: escHtml(P3)};
        }""")
        record("escHtml neutralises double quote (attribute breakout)",
               '"' not in out["q"] and "&quot;" in out["q"], out["q"])
        record("escHtml neutralises single quote (JS string breakout)",
               "'" not in out["s"] and "&#39;" in out["s"], out["s"])
        record("escHtml still neutralises angle brackets (text context)",
               "<img" not in out["t"] and "&lt;img" in out["t"], out["t"])

        svg = page.evaluate("""() => {
            const NS = 'http://www.w3.org/2000/svg';
            const parts = [
              '<svg xmlns="' + NS + '">',
              '<script>window.__pwned=1;</' + 'script>',
              '<rect width="10" height="10" onload="window.__pwned=2"/>',
              '<a href="javascript:window.__pwned=3"><text>x</text></a>',
              '<foreignObject><text onmouseover="window.__pwned=6">z</text></foreignObject>',
              '<animate attributeName="href" to="javascript:window.__pwned=5"/>',
              '<circle cx="5" cy="5" r="4" fill="red"/>',
              '</svg>'
            ];
            const evil = parts.join('');
            const d = new DOMParser().parseFromString(evil, 'image/svg+xml');
            const pe = d.querySelector('parsererror');
            return {
              evil: evil,
              out: sanitizeSvgMarkup(evil),
              rootName: d.documentElement ? d.documentElement.nodeName : null,
              parseErr: pe ? pe.textContent.slice(0, 200) : null
            };
        }""")
        low = (svg.get("out") or "").lower()
        record("sanitizeSvgMarkup output is non-empty for a well-formed SVG",
               bool(svg.get("out")),
               f"root={svg.get('rootName')} err={svg.get('parseErr')}")
        record("sanitizeSvgMarkup strips <script>", "<script" not in low, low[:110])
        record("sanitizeSvgMarkup strips on* handlers",
               "onload=" not in low and "onmouseover=" not in low, low[:120])
        record("sanitizeSvgMarkup strips javascript: URLs", "javascript:" not in low)
        record("sanitizeSvgMarkup strips <foreignObject>", "foreignobject" not in low)
        record("sanitizeSvgMarkup strips <animate>", "<animate" not in low)
        record("sanitizeSvgMarkup keeps benign drawing content",
               "<circle" in low and 'fill="red"' in low)

        inert = page.evaluate("""() => {
            const evilSvg =
              '<svg xmlns="http://www.w3.org/2000/svg">' +
              '<script>window.__pwned=1;<\\/script>' +
              '<rect onload="window.__pwned=2"/>' +
              '<foreignObject><text onmouseover="window.__pwned=6">z</text></foreignObject>' +
              '</svg>';
            const clean = sanitizeSvgMarkup(evilSvg);
            const host = document.createElement('div');
            host.id = 'xss-probe-host';
            document.body.appendChild(host);
            host.innerHTML = clean;
            const handlers = host.querySelectorAll('[onload],[onerror],[onmouseover]').length;
            const scripts = host.querySelectorAll('script').length;
            return {handlers, scripts, hasHost: !!host};
        }""")
        record("sanitized SVG inserts with zero live handlers/scripts",
               inert["handlers"] == 0 and inert["scripts"] == 0,
               json.dumps(inert))

        non_svg = page.evaluate(
            "() => sanitizeSvgMarkup('<div>not an svg</div>')")
        record("sanitizeSvgMarkup rejects non-SVG root", non_svg == "", repr(non_svg))

        malformed = page.evaluate(
            "() => sanitizeSvgMarkup('<svg><img src=x onerror=alert(1)></svg>')")
        record("sanitizeSvgMarkup fails closed on malformed XML", malformed == "",
               repr(malformed))

        browser.close()

    record("iframe sandbox no longer combines allow-scripts with allow-same-origin",
           'sandbox="allow-scripts allow-same-origin"' not in src
           and 'sandbox="allow-scripts"' in src)
    record("no unescaped raw svg_content concatenation remains",
           "'<div class=\"c3-visual-svg-wrap\">' + asset.svg_content" not in src)

    passed = sum(1 for _, ok, _ in RESULTS if ok)
    print(f"\n{passed}/{len(RESULTS)} frontend XSS hardening checks passed", flush=True)
    for n, ok, d in RESULTS:
        if not ok:
            print(f"  FAILED: {n} :: {d}", flush=True)
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
