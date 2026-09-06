"""P16 browser E2E — async learner-owned video projects.

Drives the vanilla SPA in a real browser against the seeded server and the
deterministic mock render backend (``VIDEO_RENDER_BACKEND=mock`` in the test
env), closing the P16 loop exactly as a learner would:

1. ``test_p16_create_video_project_full_loop`` — sign in as a fresh learner,
   open ``videos.html``, create a video project, watch the async render go
   ``ready`` in the UI, then load the produced ``/uploads/videos/<id>.mp4``
   over HTTP and confirm the project surfaces in the learner's list.
2. ``test_p16_video_projects_learner_isolation`` — user B cannot list, read or
   re-render user A's project: list is empty, ``GET``/``POST render`` on A's
   ``public_id`` both 404-equalize (no cross-user ID oracle).
"""

from __future__ import annotations

import re
import uuid

import pytest


@pytest.fixture(scope="session")
def browser_context_args():
    return {
        "viewport": {"width": 1280, "height": 900},
        "ignore_https_errors": True,
    }


@pytest.fixture(scope="session")
def browser_type_launch_args():
    return {
        "headless": True,
        "channel": "chrome",
        "args": [
            "--no-sandbox",
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--disable-web-security",
        ],
    }


def _register_learner(page, base_url: str, tag: str) -> dict[str, str]:
    """Register a fresh learner via the API and return credentials."""
    email = f"p16_{tag}_{uuid.uuid4().hex[:8]}@example.com"
    password = "P16Test1234!"
    name = "P16 Learner"
    result = page.evaluate(
        """async ([base, email, password, name]) => {
            const regRes = await fetch(base + '/api/v1/auth/register', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, password, name }),
            });
            const regData = await regRes.json();
            return { status: regRes.status, user: regData.user, tokens: regData.tokens };
        }""",
        [base_url, email, password, name],
    )
    assert result["status"] == 201, f"register failed: {result}"
    return {"email": email, "password": password, "name": name}


def _sign_in(page, base_url: str, email: str, password: str) -> None:
    page.goto(f"{base_url}/frontend/signin.html")
    page.wait_for_load_state("domcontentloaded")
    page.fill("#email", email)
    page.fill("#password", password)
    page.click("#submitBtn")
    page.wait_for_url("**/upload.html", timeout=20_000)
    page.wait_for_load_state("domcontentloaded")


def _api_call(page, base_url: str, method: str, path: str, body: dict | None = None) -> dict:
    return page.evaluate(
        """async ([base, method, path, body]) => {
            const token = localStorage.getItem('access_token') || '';
            const res = await fetch(base + '/api/v1' + path, {
                method: method,
                headers: {
                    'Authorization': 'Bearer ' + token,
                    ...(body ? { 'Content-Type': 'application/json' } : {}),
                },
                ...(body ? { body: JSON.stringify(body) } : {}),
            });
            let payload = null;
            try { payload = await res.json(); } catch (e) {}
            return { ok: res.ok, status: res.status, body: payload };
        }""",
        [base_url, method, path, body],
    )


def _wait_for_ready_player(page) -> dict:
    """Wait until the page shows a playable video and return its src + public_id."""
    page.wait_for_selector("#renderBox", state="visible", timeout=15_000)
    page.wait_for_function(
        """() => {
            const wrap = document.getElementById('playerWrap');
            const v = document.getElementById('videoPlayer');
            return wrap && wrap.style.display !== 'none' && v && v.src && v.src.endsWith('.mp4');
        }""",
        timeout=30_000,
    )
    src = page.locator("#videoPlayer").get_attribute("src")
    assert src, "video player has no src"
    return {"src": src}


def _use_real_auth() -> None:
    """Let the live server resolve real JWT identities.

    The root conftest installs an autouse ``get_current_user`` override (all API
    consumers become the fake TEST_USER_ID) for unit/integration tests. The E2E
    server shares the same app object, so without removing the override every
    browser-driven request would resolve to the same fake user — which would
    make a *cross-user* leakage test vacuous. Popping it lets login cookies +
    Authorization headers resolve to the genuinely distinct registered users.
    """
    from app.core.dependencies import get_current_user
    from app.main import app as _app

    _app.dependency_overrides.pop(get_current_user, None)


def test_p16_create_video_project_full_loop(page, server_env) -> None:
    base_url = server_env["base_url"]
    _use_real_auth()
    learner = _register_learner(page, base_url, "a")

    _sign_in(page, base_url, learner["email"], learner["password"])
    page.goto(f"{base_url}/frontend/videos.html")
    page.wait_for_load_state("domcontentloaded")

    page.fill("#topicInput", "How photosynthesis converts light into chemical energy")
    page.click("#createBtn")

    ready = _wait_for_ready_player(page)
    assert re.search(r"/uploads/videos/video_[a-f0-9]+\.mp4$", ready["src"]), ready["src"]

    file_resp = page.evaluate(
        """async ([base, src]) => {
            const res = await fetch(base + src);
            return { ok: res.ok, status: res.status };
        }""",
        [base_url, ready["src"]],
    )
    assert file_resp["ok"], f"rendered file returned not-ok: {file_resp}"
    assert file_resp["status"] == 200, f"rendered file not served: {file_resp}"

    listed = _api_call(page, base_url, "GET", "/video-projects")
    assert listed["ok"] is True
    items = listed["body"]["data"]
    assert len(items) == 1
    assert items[0]["status"] == "ready"
    assert items[0]["progress_percentage"] == 100.0
    assert items[0]["playable_url"] == ready["src"]
    assert items[0]["public_id"].startswith("vproj_")


def test_p16_video_projects_learner_isolation(
    page, browser, server_env
) -> None:
    base_url = server_env["base_url"]
    _use_real_auth()
    learner_a = _register_learner(page, base_url, "a")

    _sign_in(page, base_url, learner_a["email"], learner_a["password"])
    page.goto(f"{base_url}/frontend/videos.html")
    page.wait_for_load_state("domcontentloaded")
    page.fill("#topicInput", "A's private video")
    page.click("#createBtn")
    _wait_for_ready_player(page)

    own = _api_call(page, base_url, "GET", "/video-projects")
    a_public_id = own["body"]["data"][0]["public_id"]
    assert a_public_id.startswith("vproj_")

    # User B signs in from a fully fresh browser context: no A cookies, so
    # get_current_user resolves B purely from the Authorization header (the
    # P15-documented multi-user pattern for browser tests).
    ctx = browser.new_context()
    try:
        bp = ctx.new_page()
        b_boot = _register_learner(bp, base_url, "b")

        raw = bp.evaluate(
            """async ([base, login]) => {
                const loginRes = await fetch(base + '/api/v1/auth/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(login),
                });
                const loginData = await loginRes.json();
                const btok = loginData.tokens.access_token;
                const listRes = await fetch(base + '/api/v1/video-projects', {
                    method: 'GET',
                    credentials: 'omit',
                    headers: { 'Authorization': 'Bearer ' + btok },
                });
                const listBody = await listRes.json();
                const listTokenSub = (() => {
                    try { return JSON.parse(atob(btok.split('.')[1])).sub; } catch (e) { return null; }
                })();
                return { loginStatus: loginRes.status, listStatus: listRes.status, listBody, listTokenSub };
            }""",
            [base_url, {"email": b_boot["email"], "password": b_boot["password"]}],
        )
        print("P16-RAW-B", raw)
        assert raw["listStatus"] == 200, raw
        assert raw["listBody"]["data"] == [], f"B leaked A's projects: {raw}"

        _sign_in(bp, base_url, b_boot["email"], b_boot["password"])
        bp.goto(f"{base_url}/frontend/videos.html")
        bp.wait_for_load_state("domcontentloaded")
        bp.wait_for_timeout(2500)
        b_list = _api_call(bp, base_url, "GET", "/video-projects")
        assert b_list["ok"] is True
        assert b_list["body"]["data"] == [], f"B SPA list leaked A's projects: {b_list}"
        bp.wait_for_selector("#emptyState", state="visible", timeout=15_000)
        assert bp.locator("#videoList").locator(".vitem").count() == 0

        b_read = _api_call(bp, base_url, "GET", f"/video-projects/{a_public_id}")
        assert b_read["status"] == 404, f"B could read A's project: {b_read}"

        b_render = _api_call(
            bp, base_url, "POST", f"/video-projects/{a_public_id}/render", body={"force": True}
        )
        assert b_render["status"] == 404, f"B could re-render A's project: {b_render}"
    finally:
        ctx.close()
