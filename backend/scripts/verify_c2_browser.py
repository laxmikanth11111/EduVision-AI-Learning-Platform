"""End-to-end browser verification for Checkpoint C2 using Playwright.
Verifies Topic / Subtopic Learning Intelligence, Deep Content Structuring,
Learning Objectives, Subtopics, Concepts, and Source Grounding Jump Navigation.
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
PPTX_PATH = os.path.join(os.path.dirname(__file__), "..", "tests", "fixtures", "computer_networks_sample.pptx")
SCREENSHOT_DIR = os.path.join(os.path.dirname(__file__), "..", "docs", "screenshots")
SCREENSHOT_PATH = os.path.join(SCREENSHOT_DIR, "c2_topic_hierarchy_verified.png")


async def run_c2_browser_verification():
    print("=== Starting Checkpoint C2 E2E Browser Verification ===")
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)

    # 1. Register / Sign in real user
    email = f"c2_student_{uuid.uuid4().hex[:6]}@example.com"
    password = "StudentPassword123!"

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        # Register user
        reg_res = await client.post("/api/v1/auth/register", json={
            "email": email,
            "password": password,
            "name": "C2 Verification Student",
        })
        print(f"Register status: {reg_res.status_code}")

        # Login
        login_res = await client.post("/api/v1/auth/login", json={
            "email": email,
            "password": password,
        })
        if login_res.status_code != 200:
            raise RuntimeError(f"Login failed: {login_res.text}")

        login_data = login_res.json()
        tokens = login_data.get("tokens") or login_data.get("data", {}).get("tokens")
        if not tokens or "access_token" not in tokens:
            raise RuntimeError(f"Could not find tokens in login response: {login_data}")
        token = tokens["access_token"]
        refresh_token = tokens.get("refresh_token", "")
        user_info = login_data.get("user") or login_data.get("data", {}).get("user") or {"email": email, "name": "C2 Verification Student"}
        headers = {"Authorization": f"Bearer {token}"}

        # 2. Create presentation
        pres_res = await client.post("/api/v1/presentations", json={
            "title": "Computer Networks: Foundations & Architectures",
        }, headers=headers)
        if pres_res.status_code != 201:
            raise RuntimeError(f"Create presentation failed: {pres_res.text}")
        pres_id = pres_res.json()["data"]["id"]
        print(f"Created presentation: {pres_id}")

        # 3. Upload source PPTX
        with open(PPTX_PATH, "rb") as f:
            file_bytes = f.read()

        upload_res = await client.post(
            f"/api/v1/presentations/{pres_id}/source",
            files={"source": ("computer_networks_sample.pptx", file_bytes, "application/vnd.openxmlformats-officedocument.presentationml.presentation")},
            headers=headers,
        )
        if upload_res.status_code != 200:
            raise RuntimeError(f"Source upload failed: {upload_res.text}")
        print("Uploaded PPTX source file successfully.")

        # 4. Poll extraction status until ready
        for _ in range(25):
            st_res = await client.get(f"/api/v1/presentations/{pres_id}/processing-status", headers=headers)
            if st_res.status_code == 200 and st_res.json()["data"]["extraction_status"] == "ready":
                print("Extraction completed successfully: ready!")
                break
            await asyncio.sleep(1)
        else:
            raise TimeoutError("Extraction timed out waiting for ready status.")

        # 5. Check Content API
        content_res = await client.get(f"/api/v1/presentations/{pres_id}/content", headers=headers)
        if content_res.status_code != 200:
            raise RuntimeError(f"Content API failed: {content_res.text}")
        units = content_res.json()["data"]["units"]
        print(f"Verified Content API: returned {len(units)} units.")

        # 6. Generate Topics / Structure via Topic API
        regen_res = await client.post(f"/api/v1/presentations/{pres_id}/topics/regenerate", headers=headers)
        if regen_res.status_code != 200:
            raise RuntimeError(f"Topics regenerate failed: {regen_res.text}")
        topic_data = regen_res.json().get("data", {})
        print(f"Topics regenerate returned: status={topic_data.get('status')}, topics={len(topic_data.get('topics', []))}")

        topics_res = await client.get(f"/api/v1/presentations/{pres_id}/topics", headers=headers)
        if topics_res.status_code != 200:
            raise RuntimeError(f"Topics API failed: {topics_res.text}")
        topic_data = topics_res.json().get("data", {})
        print(f"Topics API returned: status={topic_data.get('status')}, topics={len(topic_data.get('topics', []))}")

        # 7. Create lesson for the presentation
        gen_res = await client.post(f"/api/v1/presentations/{pres_id}/lessons", json={
            "mode": "slide",
            "title": "Computer Networks Deep Learning",
        }, headers=headers)
        if gen_res.status_code not in (200, 201, 202):
            raise RuntimeError(f"Generate lesson failed: {gen_res.text}")
        lesson_id = gen_res.json()["data"]["id"]
        print(f"Created lesson: {lesson_id}")

        # 8. Poll lesson status until ready
        for _ in range(30):
            l_status_res = await client.get(f"/api/v1/lessons/{lesson_id}", headers=headers)
            if l_status_res.status_code == 200 and l_status_res.json()["data"]["status"] == "ready":
                print(f"Lesson {lesson_id} is ready!")
                break
            await asyncio.sleep(1)
        else:
            print("Lesson generation did not report ready in 30s; proceeding with player test anyway.")

    # 9. Real Browser Automation via Playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1366, "height": 768})
        page = await context.new_page()

        console_errors = []
        network_errors = []

        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda err: console_errors.append(str(err)))
        page.on("response", lambda resp: network_errors.append(f"{resp.status} {resp.url}") if resp.status >= 400 and "/api/v1/auth" not in resp.url else None)

        # Seed localStorage with auth tokens
        await page.goto(f"{BASE_URL}/frontend/signin.html")
        await page.evaluate(f"""() => {{
            localStorage.setItem('access_token', '{token}');
            localStorage.setItem('refresh_token', '{refresh_token}');
            localStorage.setItem('user', JSON.stringify({json.dumps(user_info)}));
        }}""")

        # Navigate to Player
        player_url = f"{BASE_URL}/frontend/player.html?lesson={lesson_id}"
        print(f"Navigating to Player: {player_url}")
        await page.goto(player_url, wait_until="networkidle")

        # Wait for frame to be visible
        await page.wait_for_selector("#frame", state="visible", timeout=15000)
        print("Player loaded successfully.")

        # Switch to AI Learning Mode
        btn_learning = page.locator("#btnModeLearning")
        await btn_learning.click()
        await page.wait_for_timeout(1000)

        # Verify AI Learning Mode is active
        learning_active = await btn_learning.evaluate("el => el.classList.contains('active')")
        assert learning_active, "AI Learning Mode button should have 'active' class"
        print("[Check 1] AI Learning Mode active: PASSED")

        # Navigate to Topic 2 (Network Types) to view subtopics & concepts
        # First thumbnail is Topic 1 Concept, second is Topic 1 Visual, third is Topic 2 Concept
        thumb_2 = page.locator("#thumb-2")
        if await thumb_2.count() > 0:
            await thumb_2.click()
            await page.wait_for_timeout(1000)

        # Check for C2 Section / Learning Provenance
        learning_badge = page.locator(".learning-provenance-badge")
        assert await learning_badge.count() > 0, "Learning provenance badge should be displayed"
        badge_text = await learning_badge.first.text_content()
        print(f"[Check 2] Provenance badge present: '{badge_text}' - PASSED")

        # Check for C2 Educational Hierarchy card
        hier_container = page.locator(".c2-hierarchy-container")
        assert await hier_container.count() > 0, "C2 hierarchy container should be displayed"
        print("[Check 3] C2 Hierarchy container rendered: PASSED")

        # Check for Subtopics or Concepts chips
        concept_chips = page.locator(".c2-concept-chip")
        subtopic_blocks = page.locator(".c2-subtopic-block")
        num_chips = await concept_chips.count()
        num_subtopics = await subtopic_blocks.count()
        print(f"[Check 4] Hierarchy details: {num_subtopics} subtopics, {num_chips} concept chips rendered - PASSED")
        assert num_chips > 0 or num_subtopics > 0, "Should have rendered subtopics or concept chips"

        # Check for Source Grounding Jump Buttons
        jump_btns = page.locator(".c2-jump-btn")
        num_jumps = await jump_btns.count()
        print(f"[Check 5] Source grounding jump buttons: {num_jumps} found - PASSED")
        assert num_jumps > 0, "Source grounding jump buttons should be rendered"

        # Test Jumping back to Source Slide: click first jump button
        jump_btn_text = await jump_btns.first.text_content()
        safe_btn_label = (jump_btn_text or "").strip().encode("ascii", "replace").decode("ascii")
        print(f"Clicking source grounding button: '{safe_btn_label}'")
        await jump_btns.first.click()
        await page.wait_for_timeout(1200)

        # Verify mode switched back to Source Mode
        btn_source = page.locator("#btnModeSource")
        source_active = await btn_source.evaluate("el => el.classList.contains('active')")
        assert source_active, "Clicking source jump button should switch player mode to 'source'"
        print("[Check 6] Source jump button switched to Source Mode: PASSED")

        # Verify source provenance banner is visible in source mode
        prov_banner = page.locator(".source-provenance-banner")
        assert await prov_banner.count() > 0, "Source slide provenance banner should be visible"
        banner_text = await prov_banner.text_content()
        print(f"[Check 7] Source provenance banner verified: '{banner_text.strip()}' - PASSED")

        # Switch back to AI Learning Mode and capture screenshot
        await btn_learning.click()
        await page.wait_for_timeout(800)
        if await thumb_2.count() > 0:
            await thumb_2.click()
            await page.wait_for_timeout(800)

        await page.screenshot(path=SCREENSHOT_PATH, full_page=True)
        print(f"Captured C2 verification screenshot to: {SCREENSHOT_PATH}")

        # Check console & network errors
        filtered_console_errors = [e for e in console_errors if "favicon" not in e.lower()]
        print(f"Console errors: {len(filtered_console_errors)}")
        if filtered_console_errors:
            print("Console error details:", filtered_console_errors)
        assert len(filtered_console_errors) == 0, f"Expected 0 console errors, got: {filtered_console_errors}"

        print(f"Network errors: {len(network_errors)}")
        if network_errors:
            print("Network error details:", network_errors)
        assert len(network_errors) == 0, f"Expected 0 network errors, got: {network_errors}"

        await browser.close()

    print("\n==================================================================")
    print("=== CHECKPOINT C2 BROWSER E2E VERIFICATION: ALL PASSED (100%) ===")
    print("==================================================================")

if __name__ == "__main__":
    asyncio.run(run_c2_browser_verification())
