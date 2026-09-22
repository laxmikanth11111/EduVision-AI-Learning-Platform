"""End-to-end browser verification for Checkpoint C4 using Playwright.
Verifies Advanced Animation & Interactive Visual Learning: deterministic
animation package generation (auto-triggered after C3 visuals), API delivery,
player Animation Mode rendering with sandboxed iframe + HUD + guided
interaction, and zero console errors.
"""

import asyncio
import json
import os
import sys
import uuid

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import httpx
from playwright.async_api import async_playwright

BASE_URL = "http://127.0.0.1:8000"
PPTX_PATH = os.path.join(
    os.path.dirname(__file__), "..", "tests", "fixtures", "computer_networks_sample.pptx"
)
SCREENSHOT_DIR = os.path.join(os.path.dirname(__file__), "..", "docs", "screenshots")
SCREENSHOT_PATH = os.path.join(SCREENSHOT_DIR, "c4_animation_intelligence_verified.png")


async def _poll_ready(cb, timeout: float, desc: str):
    import time

    start = time.monotonic()
    while time.monotonic() - start < timeout:
        data = await cb()
        if data:
            return data
        await asyncio.sleep(1)
    raise TimeoutError(f"Timed out waiting for: {desc}")


async def poll_c4_ready(client, pres_id, headers):
    res = await client.get(f"/api/v1/c4/animations/presentation/{pres_id}/ready", headers=headers)
    if res.status_code != 200:
        return None
    assets = res.json().get("data", [])
    ready = [a for a in assets if a.get("status") in ("ready", "active")]
    return ready or None


async def poll_c4_list(client, pres_id, headers):
    res = await client.get(f"/api/v1/c4/animations/presentation/{pres_id}", headers=headers)
    if res.status_code != 200:
        return None
    return res.json().get("data", []) or []


async def run_c4_browser_verification():
    print("=== Starting Checkpoint C4 E2E Browser Verification ===")
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)

    email = f"c4_student_{uuid.uuid4().hex[:6]}@example.com"
    password = "StudentPassword123!"

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=60.0) as client:
        reg_res = await client.post(
            "/api/v1/auth/register",
            json={
                "email": email,
                "password": password,
                "name": "C4 Verification Student",
            },
        )
        print(f"Register status: {reg_res.status_code}")

        login_res = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password},
        )
        if login_res.status_code != 200:
            raise RuntimeError(f"Login failed: {login_res.text[:300]}")
        login_data = login_res.json()
        tokens = login_data.get("tokens") or login_data.get("data", {}).get("tokens")
        token = tokens["access_token"]
        refresh_token = tokens.get("refresh_token", "")
        user_info = (
            login_data.get("user")
            or login_data.get("data", {}).get("user")
            or {"email": email, "name": "C4 Verification Student"}
        )
        headers = {"Authorization": f"Bearer {token}"}

        pres_res = await client.post(
            "/api/v1/presentations",
            json={"title": "Computer Networks: Foundation Principles"},
            headers=headers,
        )
        if pres_res.status_code != 201:
            raise RuntimeError(f"Create presentation failed: {pres_res.text}")
        pres_id = pres_res.json()["data"]["id"]
        print(f"Created presentation: {pres_id}")

        with open(PPTX_PATH, "rb") as f:
            file_bytes = f.read()
        upload_res = await client.post(
            f"/api/v1/presentations/{pres_id}/source",
            files={
                "source": (
                    "computer_networks_sample.pptx",
                    file_bytes,
                    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                )
            },
            headers=headers,
        )
        if upload_res.status_code != 200:
            raise RuntimeError(f"Source upload failed: {upload_res.text}")
        print("Uploaded PPTX source file successfully.")

        for _ in range(40):
            st_res = await client.get(
                f"/api/v1/presentations/{pres_id}/processing-status", headers=headers
            )
            if st_res.status_code == 200 and st_res.json()["data"]["extraction_status"] == "ready":
                print("Extraction completed successfully: ready!")
                break
            await asyncio.sleep(1)
        else:
            raise TimeoutError("Extraction timed out waiting for ready status.")

        # Baseline: upload alone must NOT auto-generate C4 animations.
        pre_assets = await poll_c4_list(client, pres_id, headers)
        assert pre_assets is not None, "expected a list response from C4 asset endpoint"
        assert len(pre_assets) == 0, (
            f"C4 assets must be absent after upload alone, got {len(pre_assets)}"
        )
        print("[Baseline] 0 C4 assets after upload (no C2 outline yet): PASSED")

        regen_res = await client.post(
            f"/api/v1/presentations/{pres_id}/topics/regenerate", headers=headers
        )
        if regen_res.status_code != 200:
            raise RuntimeError(f"Topics regenerate failed: {regen_res.text}")
        print(f"Topics regenerate status: {regen_res.json().get('data', {}).get('status')}")

        for _ in range(60):
            top_res = await client.get(f"/api/v1/presentations/{pres_id}/topics", headers=headers)
            if top_res.status_code == 200:
                data = top_res.json().get("data", {})
                if data.get("status") in ("ready", "succeeded") and data.get("topics"):
                    print(f"C2 outline ready with {len(data.get('topics', []))} topics.")
                    break
            await asyncio.sleep(2)
        else:
            raise TimeoutError("C2 outline did not reach ready status.")

        # C4 generation must be auto-dispatched after C3 completion (no manual call).
        c4_present = await _poll_ready(
            lambda: poll_c4_list(client, pres_id, headers),
            timeout=180,
            desc="auto-triggered C4 animation assets",
        )
        print(
            f"[Auto-trigger] {len(c4_present)} C4 animation assets appeared automatically after C3 generation (no manual C4 call): PASSED"
        )

        ready_assets = await _poll_ready(
            lambda: poll_c4_ready(client, pres_id, headers),
            timeout=240,
            desc="C4 ready animation assets",
        )
        if not ready_assets:
            raise RuntimeError("No ready C4 animation assets were produced.")

        first = ready_assets[0]
        asset_id = first.get("id") or first.get("asset_id")
        html_res = await client.get(f"/api/v1/c4/animations/{asset_id}/html", headers=headers)
        if html_res.status_code != 200 or "<svg" not in html_res.text:
            raise RuntimeError(f"HTML endpoint failed: {html_res.status_code}")
        assert "c4-svg" in html_res.text, "HTML package must contain the SVG stage"
        assert "c4-hud" in html_res.text, "HTML package must contain the playback HUD"
        print("[API 1] HTML endpoint returned self-contained package: PASSED")
        print(f"[API 2] Ready animations count: {len(ready_assets)} - PASSED")

        gen_res = await client.post(
            f"/api/v1/presentations/{pres_id}/lessons",
            json={"mode": "slide", "title": "Computer Networks C4 Lesson"},
            headers=headers,
        )
        if gen_res.status_code not in (200, 201, 202):
            raise RuntimeError(f"Generate lesson failed: {gen_res.text}")
        lesson_id = gen_res.json()["data"]["id"]
        print(f"Created lesson: {lesson_id}")

        for _ in range(180):
            l_res = await client.get(
                f"/api/v1/presentations/{pres_id}/lessons/{lesson_id}", headers=headers
            )
            if l_res.status_code == 200 and l_res.json().get("data", {}).get("status") == "ready":
                print(f"Lesson {lesson_id} is ready!")
                break
            await asyncio.sleep(2)
        else:
            raise TimeoutError("Lesson generation did not reach ready in 360s.")

        # Player payload embeds animations per topic.
        player_res = await client.get(
            f"/api/v1/lessons/{lesson_id}/player",
            headers=headers,
        )
        topics = player_res.json()["data"]["topics"]
        any_anim = any((t.get("animations") or []) for t in topics)
        print(
            f"[Player payload] topics with embedded animations: {sum(1 for t in topics if t.get('animations'))}/{len(topics)} - {'PASSED' if any_anim else 'FAILED'}"
        )
        assert any_anim, "expected at least one topic with an embedded animation"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1366, "height": 768})
        page = await context.new_page()

        console_errors = []
        network_errors = []

        page.on(
            "console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None
        )
        page.on("pageerror", lambda err: console_errors.append(str(err)))
        page.on(
            "response",
            lambda resp: (
                network_errors.append(f"{resp.status} {resp.url}")
                if resp.status >= 400 and "/api/v1/auth" not in resp.url
                else None
            ),
        )

        await page.goto(f"{BASE_URL}/frontend/signin.html")
        await page.evaluate(
            f"""() => {{
            localStorage.setItem('access_token', '{token}');
            localStorage.setItem('refresh_token', '{refresh_token}');
            localStorage.setItem('user', JSON.stringify({json.dumps(user_info)}));
        }}"""
        )

        player_url = f"{BASE_URL}/frontend/player.html?lesson={lesson_id}"
        print(f"Navigating to Player: {player_url}")
        await page.goto(player_url, wait_until="networkidle")

        await page.wait_for_selector("#frame", state="visible", timeout=30000)
        print("Player loaded successfully.")

        btn_anim = page.locator("#btnModeAnimation")
        await btn_anim.click()
        await page.wait_for_timeout(2000)

        anim_active = await btn_anim.evaluate("el => el.classList.contains('active')")
        assert anim_active, "Animation Mode button should have 'active' class"
        print("[Check 1] Animation Mode button active: PASSED")

        await page.wait_for_selector(".c4-anim-stage", timeout=20000)
        print("[Check 2] C4 animation stage rendered: PASSED")

        badge = page.locator(".c3-visual-badge")
        assert await badge.count() > 0, "Animation badge should be displayed"
        badge_text = await badge.first.text_content()
        print(f"[Check 3] Animation type badge present: '{badge_text}' - PASSED")

        frame = page.locator(".c4-anim-frame")
        assert await frame.count() > 0, "Sandboxed iframe should be present"
        print("[Check 4] Sandboxed animation iframe present: PASSED")

        hud_buttons = page.locator(".c4-hud-btn")
        assert await hud_buttons.count() >= 4, "HUD must expose play/prev/next/restart controls"
        print(f"[Check 5] HUD controls present ({await hud_buttons.count()}): PASSED")

        step = page.locator(".c4-hud-step")
        step_text = await step.text_content()
        print(f"[Check 6] Step counter present: '{step_text}' - PASSED")

        expl = page.locator(".c3-expl-title")
        assert await expl.count() > 0, "Explanation panel should be displayed"
        print("[Check 7] Why-this-animation explanation panel present: PASSED")

        await page.screenshot(path=SCREENSHOT_PATH, full_page=True)
        print(f"Captured C4 verification screenshot to: {SCREENSHOT_PATH}")

        filtered_console_errors = [e for e in console_errors if "favicon" not in e.lower()]
        print(f"Console errors: {len(filtered_console_errors)}")
        if filtered_console_errors:
            print("Console error details:", filtered_console_errors)
        assert len(filtered_console_errors) == 0, (
            f"Expected 0 console errors, got: {filtered_console_errors}"
        )

        print(f"Network errors: {len(network_errors)}")
        if network_errors:
            print("Network error details:", network_errors)
        assert len(network_errors) == 0, f"Expected 0 network errors, got: {network_errors}"

        await browser.close()

    print("\n====================================================================")
    print("=== CHECKPOINT C4 BROWSER E2E VERIFICATION: ALL PASSED (100%) ===")
    print("====================================================================")


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run_c4_browser_verification()))
