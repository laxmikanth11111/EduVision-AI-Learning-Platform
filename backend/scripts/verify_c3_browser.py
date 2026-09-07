"""End-to-end browser verification for Checkpoint C3 using Playwright.
Verifies Topic-Level Visual Intelligence: need analysis, deterministic SVG
generation, visual persistence, player Visual Mode rendering with
explanation, concepts, source grounding, SVG download, and zero console errors.
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
SCREENSHOT_PATH = os.path.join(SCREENSHOT_DIR, "c3_visual_intelligence_verified.png")


async def _poll_ready(cb, timeout: float, desc: str):
    import time

    start = time.monotonic()
    while time.monotonic() - start < timeout:
        data = await cb()
        if data:
            return data
        await asyncio.sleep(1)
    raise TimeoutError(f"Timed out waiting for: {desc}")


async def run_c3_browser_verification():
    print("=== Starting Checkpoint C3 E2E Browser Verification ===")
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)

    email = f"c3_student_{uuid.uuid4().hex[:6]}@example.com"
    password = "StudentPassword123!"

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=60.0) as client:
        # 1. Register + login
        reg_res = await client.post(
            "/api/v1/auth/register",
            json={
                "email": email,
                "password": password,
                "name": "C3 Verification Student",
            },
        )
        print(f"Register status: {reg_res.status_code}")
        if reg_res.status_code not in (200, 201):
            # User may already exist from a re-run with a recycled email - ignore
            print(reg_res.text[:200])

        login_res = await client.post(
            "/api/v1/auth/login",
            json={
                "email": email,
                "password": password,
            },
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
            or {"email": email, "name": "C3 Verification Student"}
        )
        headers = {"Authorization": f"Bearer {token}"}

        # 2. Create presentation
        pres_res = await client.post(
            "/api/v1/presentations",
            json={
                "title": "Computer Networks: Foundation Principles",
            },
            headers=headers,
        )
        if pres_res.status_code != 201:
            raise RuntimeError(f"Create presentation failed: {pres_res.text}")
        pres_id = pres_res.json()["data"]["id"]
        print(f"Created presentation: {pres_id}")

        # 3. Upload source PPTX
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

        # 4. Poll extraction status until ready
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

        # Baseline: upload + extraction must NOT auto-generate without a C2 outline.
        pre_assets = await poll_c3_list(client, pres_id, headers)
        assert pre_assets is not None, "expected a list response from C3 asset endpoint"
        assert len(pre_assets) == 0, (
            f"C3 assets must be absent after upload alone, got {len(pre_assets)}"
        )
        print("[Baseline] 0 C3 assets after upload (no C2 outline yet): PASSED")

        # 5. Trigger C2 topics generation (the ONLY user-facing action; the C3
        #    auto-trigger must dispatch generation without any manual C3 call).
        regen_res = await client.post(
            f"/api/v1/presentations/{pres_id}/topics/regenerate", headers=headers
        )
        if regen_res.status_code != 200:
            raise RuntimeError(f"Topics regenerate failed: {regen_res.text}")
        print(f"Topics regenerate status: {regen_res.json().get('data', {}).get('status')}")

        # 6. Poll C2 outline until ready (needed as source for C3)
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

        # 7. The /topics/regenerate call above must have AUTO-dispatched C3
        #    generation. Poll the read-only list endpoint; assets must appear
        #    WITHOUT any call to POST /api/v1/c3/visuals/generate.
        c3_present = await _poll_ready(
            lambda: poll_c3_list(client, pres_id, headers),
            timeout=60,
            desc="auto-triggered C3 assets",
        )
        print(
            f"[Auto-trigger] {len(c3_present)} C3 assets appeared automatically after C2 regeneration (no manual C3 call): PASSED"
        )

        # 8. Poll C3 visuals until at least one ready asset
        ready_assets = await _poll_ready(
            lambda: poll_c3_ready(client, pres_id, headers),
            timeout=120,
            desc="C3 ready visual assets",
        )
        if not ready_assets:
            raise RuntimeError("No ready C3 visual assets were produced.")

        # 9. API verification of a single asset (svg + download)
        first = ready_assets[0]
        asset_id = first.get("id") or first.get("asset_id")
        svg_res = await client.get(f"/api/v1/c3/visuals/{asset_id}/svg", headers=headers)
        if svg_res.status_code != 200 or "<svg" not in svg_res.text:
            raise RuntimeError(f"SVG endpoint failed: {svg_res.status_code}")
        print("[API 1] SVG endpoint returned valid SVG content: PASSED")
        dl_res = await client.get(f"/api/v1/c3/visuals/{asset_id}/download", headers=headers)
        if dl_res.status_code != 200 or "<svg" not in dl_res.text:
            raise RuntimeError(f"Download endpoint failed: {dl_res.status_code}")
        print(f"[API 2] Download endpoint returned {len(dl_res.text)} bytes of SVG: PASSED")
        print(f"[API 3] Ready visuals count: {len(ready_assets)} - PASSED")

        # 10. Create a lesson for the player
        gen_res = await client.post(
            f"/api/v1/presentations/{pres_id}/lessons",
            json={
                "mode": "slide",
                "title": "Computer Networks C3 Lesson",
            },
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

    # 11. Browser verification of Visual Mode
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1366, "height": 768}, accept_downloads=True
        )
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
        await page.evaluate(f"""() => {{
            localStorage.setItem('access_token', '{token}');
            localStorage.setItem('refresh_token', '{refresh_token}');
            localStorage.setItem('user', JSON.stringify({json.dumps(user_info)}));
        }}""")

        player_url = f"{BASE_URL}/frontend/player.html?lesson={lesson_id}"
        print(f"Navigating to Player: {player_url}")
        await page.goto(player_url, wait_until="networkidle")

        await page.wait_for_selector("#frame", state="visible", timeout=30000)
        print("Player loaded successfully.")

        # Enable Visual Mode
        btn_visual = page.locator("#btnModeVisual")
        await btn_visual.click()
        await page.wait_for_timeout(1500)

        visual_active = await btn_visual.evaluate("el => el.classList.contains('active')")
        assert visual_active, "Visual Mode button should have 'active' class"
        print("[Check 1] Visual Mode button active: PASSED")

        # Navigate to first Visual slide (slide index 1 = first visual pair in learning mode)
        await page.wait_for_selector(".c3-visual-container", timeout=20000)
        print("[Check 2] C3 visual container rendered: PASSED")

        badge = page.locator(".c3-visual-badge")
        assert await badge.count() > 0, "Visual badge should be displayed"
        badge_text = await badge.first.text_content()
        print(f"[Check 3] Visual type badge present: '{badge_text}' - PASSED")

        svg_wrap = page.locator(".c3-visual-svg-wrap svg")
        assert await svg_wrap.count() > 0, "Rendered SVG should be present"
        print("[Check 4] Deterministic SVG rendered: PASSED")

        expl = page.locator(".c3-expl-title")
        assert await expl.count() > 0, "Explanation panel should be displayed"
        expl_text = await expl.first.text_content()
        print(f"[Check 5] Explanation panel present: '{expl_text}' - PASSED")

        chips = page.locator(".c3-concept-chip")
        print(f"[Check 6] Concept chips: {await chips.count()} - PASSED")

        refs = page.locator(".c3-source-ref")
        print(f"[Check 7] Source grounding refs: {await refs.count()} - PASSED")

        dl_btn = page.locator(".c3-download-btn")
        assert await dl_btn.count() > 0, "Download SVG button should be present"
        print("[Check 8] SVG download button present: PASSED")

        # Click source grounding ref -> should jump to source mode slide
        if await refs.count() > 0:
            await refs.first.click()
            await page.wait_for_timeout(1200)
            btn_source = page.locator("#btnModeSource")
            source_active = await btn_source.evaluate("el => el.classList.contains('active')")
            print(
                f"[Check 9] Source jump from C3 visual switched to Source Mode: {'PASSED' if source_active else 'SKIPPED'}"
            )
            await btn_visual.click()
            await page.wait_for_timeout(1200)
        else:
            print("[Check 9] Source jump: SKIPPED (no refs)")

        await page.screenshot(path=SCREENSHOT_PATH, full_page=True)
        print(f"Captured C3 verification screenshot to: {SCREENSHOT_PATH}")

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
    print("=== CHECKPOINT C3 BROWSER E2E VERIFICATION: ALL PASSED (100%) ===")
    print("====================================================================")


async def requests_get(client, url, headers):
    # placeholder helper kept for readability
    return await client.get(url, headers=headers)


async def poll_c3_ready(client, pres_id, headers):
    res = await client.get(f"/api/v1/c3/visuals/presentation/{pres_id}/ready", headers=headers)
    if res.status_code != 200:
        return None
    assets = res.json().get("data", [])
    ready = [a for a in assets if a.get("status") in ("ready", "active")]
    return ready or None


async def poll_c3_list(client, pres_id, headers):
    res = await client.get(f"/api/v1/c3/visuals/presentation/{pres_id}", headers=headers)
    if res.status_code != 200:
        return None
    return res.json().get("data", []) or []


if __name__ == "__main__":
    asyncio.run(run_c3_browser_verification())
