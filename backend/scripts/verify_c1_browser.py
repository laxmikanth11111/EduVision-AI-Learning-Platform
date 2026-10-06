"""End-to-end browser verification for Checkpoint C1 using Playwright."""
import asyncio
import json
import os
import uuid

import httpx
from playwright.async_api import ConsoleMessage, Response, async_playwright

BASE_URL = "http://127.0.0.1:8000"
PPTX_PATH = os.path.join(os.path.dirname(__file__), "..", "tests", "fixtures", "computer_networks_sample.pptx")

async def run_c1_browser_verification() -> None:
    print("=== Starting Checkpoint C1 E2E Browser Verification ===")

    # 1. Register / Sign in real user
    email = f"c1_student_{uuid.uuid4().hex[:6]}@example.com"
    password = "StudentPassword123!"

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        # Register user
        reg_res = await client.post("/api/v1/auth/register", json={
            "email": email,
            "password": password,
            "name": "C1 Verification Student",
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
        user_info = login_data.get("user") or login_data.get("data", {}).get("user") or {"email": email, "name": "C1 Verification Student"}
        headers = {"Authorization": f"Bearer {token}"}

        # 2. Create presentation
        pres_res = await client.post("/api/v1/presentations", json={
            "title": "Computer Networks & Architecture",
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
        for _ in range(20):
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

        # 6. Create lesson for the presentation
        gen_res = await client.post(f"/api/v1/presentations/{pres_id}/lessons", json={
            "mode": "slide",
            "title": "Computer Networks & Architecture Lesson",
        }, headers=headers)
        if gen_res.status_code not in (200, 201, 202):
            raise RuntimeError(f"Generate lesson failed: {gen_res.text}")
        lesson_id = gen_res.json()["data"]["id"]
        print(f"Created lesson: {lesson_id}")

    # 7. Real Browser Automation via Playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1366, "height": 768})
        page = await context.new_page()

        console_errors: list[str] = []
        network_errors: list[str] = []

        def _on_console(msg: ConsoleMessage) -> None:
            if msg.type == "error":
                console_errors.append(msg.text)

        def _on_response(res: Response) -> None:
            if res.status >= 400:
                network_errors.append(f"{res.status} {res.url}")

        page.on("console", _on_console)
        page.on("response", _on_response)

        # Inject auth tokens into localStorage before loading page
        await page.goto(f"{BASE_URL}/frontend/signin.html")
        await page.evaluate(f"""() => {{
            localStorage.setItem('access_token', '{token}');
            localStorage.setItem('refresh_token', '{refresh_token}');
            localStorage.setItem('user', JSON.stringify({json.dumps(user_info)}));
        }}""")

        player_url = f"{BASE_URL}/frontend/player.html?lesson={lesson_id}"
        print(f"Navigating to Player: {player_url}")
        await page.goto(player_url, wait_until="networkidle")
        await page.wait_for_selector("#viewport .source-title, #viewport .slide-title", timeout=10000)

        # Check Mode Bar & Default Mode
        is_source_mode = await page.evaluate("() => playerMode === 'source'")
        print(f"Player default mode: {is_source_mode} (expected True)")
        assert is_source_mode, "Default mode must be 'source' when source units are present"

        # Check Slide 1 Content
        s1_title = await page.text_content("#viewport .source-title")
        print(f"Slide 1 Title: {s1_title}")
        assert "Computer Networks & Architecture" in s1_title

        provenance = await page.text_content(".source-provenance-banner")
        print(f"Provenance banner: {provenance.strip()}")
        assert "From Your Uploaded Material" in provenance

        # Navigate to Slide 2 (Hierarchical Bullets)
        print("Navigating to Slide 2...")
        await page.click("#nextBtn")
        await asyncio.sleep(0.5)
        s2_title = await page.text_content("#viewport .source-title")
        print(f"Slide 2 Title: {s2_title}")
        assert "Network Types & Classifications" in s2_title

        # Check Bullets
        bullets = await page.query_selector_all(".source-bullet-item")
        print(f"Slide 2 bullet count: {len(bullets)}")
        assert len(bullets) >= 4, "Hierarchical bullets must be rendered"
        bullet_texts = [await b.text_content() for b in bullets]
        print(f"Slide 2 bullet texts: {bullet_texts}")
        assert any("Local Area Network" in t for t in bullet_texts)
        assert any("Metropolitan Area Network" in t for t in bullet_texts)
        assert any("Wide Area Network" in t for t in bullet_texts)

        # Navigate to Slide 3 (Table & Notes)
        print("Navigating to Slide 3...")
        await page.click("#nextBtn")
        await asyncio.sleep(0.5)
        s3_title = await page.text_content("#viewport .source-title")
        print(f"Slide 3 Title: {s3_title}")
        assert "OSI vs TCP/IP Protocol Architecture" in s3_title

        # Check Table
        table = await page.query_selector(".source-table")
        assert table is not None, "Structured table must be rendered on Slide 3"
        table_text = await page.text_content(".source-table")
        print("Slide 3 Table headers & contents detected:")
        assert "Layer Tier" in table_text
        assert "OSI 7-Layer Reference" in table_text
        assert "TCP/IP 4-Layer Suite" in table_text

        # Check Notes
        notes = await page.query_selector(".source-notes-card")
        assert notes is not None, "Speaker notes card must be rendered"
        notes_text = await page.text_content(".source-notes-card")
        assert "Instructor Note" in notes_text or "conceptual model" in notes_text
        print("Slide 3 Speaker notes verified.")

        # Navigate to Slide 4 (Transmission Media Table)
        print("Navigating to Slide 4...")
        await page.click("#nextBtn")
        await asyncio.sleep(0.5)
        s4_title = await page.text_content("#viewport .source-title")
        print(f"Slide 4 Title: {s4_title}")
        assert "Physical Transmission Media Comparison" in s4_title
        table4_text = await page.text_content(".source-table")
        assert "Cat6a Twisted Pair" in table4_text
        assert "Single-mode Fiber" in table4_text

        # Test Mode Switching: Switch to AI Learning Mode
        print("Switching to AI Learning Mode...")
        await page.click("#btnModeLearning")
        await asyncio.sleep(0.5)
        is_learning_mode = await page.evaluate("() => playerMode === 'learning'")
        assert is_learning_mode, "Player must switch to learning mode"
        learning_badge = await page.text_content(".learning-provenance-badge")
        print(f"AI Learning Mode badge: {learning_badge.strip()}")
        assert "AI Explanation" in learning_badge or "EduVision Visual" in learning_badge

        # Switch back to Source Mode
        print("Switching back to Source Mode...")
        await page.click("#btnModeSource")
        await asyncio.sleep(0.5)
        is_source_again = await page.evaluate("() => playerMode === 'source'")
        assert is_source_again, "Player must switch back to source mode"

        # Test Page Refresh and Session Resume
        print("Testing page reload and resume...")
        await page.reload(wait_until="networkidle")
        await asyncio.sleep(1)
        resumed_counter = await page.text_content("#counter")
        print(f"Resumed counter display: {resumed_counter}")

        # Screenshot capture for artifact verification
        os.makedirs(os.path.join(os.path.dirname(__file__), "..", "docs", "screenshots"), exist_ok=True)
        screenshot_path = os.path.join(os.path.dirname(__file__), "..", "docs", "screenshots", "c1_source_mode_verified.png")
        await page.screenshot(path=screenshot_path)
        print(f"Saved verification screenshot to: {screenshot_path}")

        await browser.close()

        # Verify 0 console errors and 0 network errors
        filtered_console = [e for e in console_errors if not any(ign in e for ign in ["favicon", "livereload"])]
        filtered_network = [n for n in network_errors if not any(ign in n for ign in ["favicon", "livereload"])]

        print(f"Console errors: {len(filtered_console)} -> {filtered_console}")
        print(f"Network errors: {len(filtered_network)} -> {filtered_network}")

        assert len(filtered_console) == 0, f"Must have 0 console errors, got: {filtered_console}"
        assert len(filtered_network) == 0, f"Must have 0 network errors, got: {filtered_network}"

        print("\n=== Checkpoint C1 E2E Browser Verification: PASSED 100% ===")

if __name__ == "__main__":
    asyncio.run(run_c1_browser_verification())
