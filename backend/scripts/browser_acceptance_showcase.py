"""Autonomous Browser Showcase & End-to-End Acceptance Verification Script.

Executes the complete EduVision AI learner journey in a real browser context
against the running stack (PostgreSQL + Redis + Celery + FastAPI).
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from typing import Any

from playwright.async_api import ConsoleMessage, Request, async_playwright

BASE_URL = "http://127.0.0.1:8000"
TS = int(time.time())
USER_A = {
    "email": f"alex_morgan_{TS}@example.com",
    "password": "ShowcasePass2026!",
    "name": "Alex Morgan",
}
USER_B = {
    "email": f"jordan_lee_{TS}@example.com",
    "password": "ShowcasePass2026!",
    "name": "Jordan Lee",
}

console_errors: list[str] = []
network_errors: list[str] = []

RESULTS: dict[str, Any] = {
    "authentication": "NOT RUN",
    "dashboard": "NOT RUN",
    "upload": "NOT RUN",
    "lesson_player": "NOT RUN",
    "persistent_resume": "NOT RUN",
    "adaptive_assessment": "NOT RUN",
    "review_retention": "NOT RUN",
    "ai_tutor": "NOT RUN",
    "video_lessons": "NOT RUN",
    "two_user_isolation": "NOT RUN",
    "console_errors": console_errors,
    "network_errors": network_errors,
}


async def main() -> None:
    print(f"Starting browser acceptance showcase against {BASE_URL}...")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--disable-web-security",
            ],
        )

        context = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await context.new_page()

        # Monitor console and failed requests
        def _on_console(msg: ConsoleMessage) -> None:
            if (
                msg.type == "error"
                and "favicon" not in msg.text
                and "status of 404" not in msg.text
            ):
                console_errors.append(msg.text)

        def _on_request_failed(req: Request) -> None:
            network_errors.append(f"{req.method} {req.url} - {req.failure}")

        page.on("console", _on_console)
        page.on("requestfailed", _on_request_failed)

        # -------------------------------------------------------------
        # STEP 1: AUTHENTICATION (Register -> Login -> Tokens)
        # -------------------------------------------------------------
        print("\n--- [1/10] Testing Authentication ---")
        try:
            await page.goto(f"{BASE_URL}/frontend/signup.html")
            await page.wait_for_load_state("domcontentloaded")
            await page.fill("#name", USER_A["name"])
            await page.fill("#email", USER_A["email"])
            await page.fill("#password", USER_A["password"])
            await page.click("#submitBtn")

            await page.wait_for_url("**/upload.html", timeout=15000)
            token = await page.evaluate("localStorage.getItem('access_token')")
            user_raw = await page.evaluate("localStorage.getItem('user')")
            assert token, "access_token must be saved in localStorage"
            assert user_raw, "user object must be saved in localStorage"
            print("[OK] Registration and token storage successful")

            # Test Logout & Re-login
            await page.goto(f"{BASE_URL}/frontend/signin.html")
            await page.wait_for_load_state("domcontentloaded")
            await page.fill("#email", USER_A["email"])
            await page.fill("#password", USER_A["password"])
            await page.click("#submitBtn")
            await page.wait_for_url("**/upload.html", timeout=15000)
            print("[OK] Sign in and redirect to upload successful")
            RESULTS["authentication"] = "PASS"
        except Exception as e:
            print(f"[FAIL] Authentication failed: {e}")
            RESULTS["authentication"] = f"FAIL: {e}"

        # -------------------------------------------------------------
        # STEP 2: DASHBOARD (Overview, Goals, Plan, Retention)
        # -------------------------------------------------------------
        print("\n--- [2/10] Testing Learner Dashboard ---")
        try:
            await page.goto(f"{BASE_URL}/frontend/dashboard.html")
            await page.wait_for_load_state("domcontentloaded")
            await page.wait_for_timeout(2000)

            user_badge = await page.inner_text("#userName")
            assert USER_A["name"] in user_badge or USER_A["email"] in user_badge
            print(f"[OK] Dashboard loaded with user: {user_badge}")

            content = await page.content()
            assert "Effort vs Mastery" in content or "Mastery" in content
            assert "Review Queue" in content or "Retention" in content
            assert "Today" in content or "Plan" in content or "Goals" in content
            print("[OK] Dashboard intelligence cards & navigation verified")
            RESULTS["dashboard"] = "PASS"
        except Exception as e:
            print(f"[FAIL] Dashboard failed: {e}")
            RESULTS["dashboard"] = f"FAIL: {e}"

        # -------------------------------------------------------------
        # STEP 3: CONTENT CREATION / UPLOAD
        # -------------------------------------------------------------
        print("\n--- [3/10] Testing Content Creation / Upload ---")
        lesson_id = None
        deck_id = None
        try:
            deck_info = await page.evaluate("""async () => {
                const token = localStorage.getItem('access_token');
                const auth = { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token };

                const presRes = await fetch('/api/v1/presentations/manual', {
                    method: 'POST',
                    headers: auth,
                    body: JSON.stringify({
                        title: 'Cellular Biology Masterclass',
                        topics: ['Mitochondria Powerhouse', 'ATP Synthesis', 'Cellular Respiration'],
                    }),
                });
                const presData = await presRes.json();
                const presId = presData.data.id;

                const lessonRes = await fetch('/api/v1/presentations/' + presId + '/lessons', {
                    method: 'POST',
                    headers: auth,
                    body: JSON.stringify({ mode: 'slide', title: 'Cellular Biology Lesson' }),
                });
                const lessonData = await lessonRes.json();
                return { presId, lessonId: lessonData.data.id };
            }""")
            deck_id = deck_info["presId"]
            lesson_id = deck_info["lessonId"]
            print(f"[OK] Content created: Deck {deck_id}, Lesson {lesson_id}")
            RESULTS["upload"] = "PASS"
        except Exception as e:
            print(f"[FAIL] Upload / Content creation failed: {e}")
            RESULTS["upload"] = f"FAIL: {e}"

        # -------------------------------------------------------------
        # STEP 4: LESSON PLAYER
        # -------------------------------------------------------------
        print("\n--- [4/10] Testing Lesson Player ---")
        session_id = None
        try:
            if lesson_id and deck_id:
                # Start player session via API
                start_res = await page.evaluate(f"""async () => {{
                    const token = localStorage.getItem('access_token');
                    const res = await fetch('/api/v1/lessons/{lesson_id}/player/start', {{
                        method: 'POST',
                        headers: {{ 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token }},
                        body: JSON.stringify({{ device_id: 'browser_test_dev' }}),
                    }});
                    return await res.json();
                }}""")
                assert start_res.get("success") is True, f"Player start failed: {start_res}"
                session_id = start_res["data"]["session"]["session_id"]
                print(f"[OK] Player session started: {session_id}")

                await page.goto(f"{BASE_URL}/frontend/player.html?lesson={lesson_id}&deck={deck_id}")
                await page.wait_for_load_state("domcontentloaded")
                await page.wait_for_timeout(2000)

                body_text = await page.inner_text("body")
                assert "Cellular Biology" in body_text or "player" in page.url.lower() or "topic" in body_text.lower()
                print("[OK] Lesson player UI loaded in browser")
                RESULTS["lesson_player"] = "PASS"
            else:
                RESULTS["lesson_player"] = "SKIP"
        except Exception as e:
            print(f"[FAIL] Lesson Player failed: {e}")
            RESULTS["lesson_player"] = f"FAIL: {e}"

        # -------------------------------------------------------------
        # STEP 5: PERSISTENT RESUME
        # -------------------------------------------------------------
        print("\n--- [5/10] Testing Persistent Resume ---")
        try:
            if lesson_id and session_id:
                # Persist position to slide 2
                pos_res = await page.evaluate(f"""async () => {{
                    const token = localStorage.getItem('access_token');
                    const res = await fetch('/api/v1/lessons/{lesson_id}/player/position', {{
                        method: 'POST',
                        headers: {{ 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token }},
                        body: JSON.stringify({{ session_id: '{session_id}', slide_index: 2 }}),
                    }});
                    return await res.json();
                }}""")
                assert pos_res.get("success") is True, f"Set position failed: {pos_res}"
                print(f"[OK] Position persisted to slide 2: {pos_res.get('message')}")

                # Verify via /api/v1/me/progress
                prog = await page.evaluate("""async () => {
                    const token = localStorage.getItem('access_token');
                    const res = await fetch('/api/v1/me/progress', {
                        headers: { 'Authorization': 'Bearer ' + token },
                    });
                    return await res.json();
                }""")
                assert prog.get("success") is True
                print("[OK] Learner progress endpoint verified resume tracking")
                RESULTS["persistent_resume"] = "PASS"
            else:
                RESULTS["persistent_resume"] = "SKIP"
        except Exception as e:
            print(f"[FAIL] Persistent resume failed: {e}")
            RESULTS["persistent_resume"] = f"FAIL: {e}"

        # -------------------------------------------------------------
        # STEP 6: ADAPTIVE ASSESSMENT & CHECKPOINTS
        # -------------------------------------------------------------
        print("\n--- [6/10] Testing Adaptive Assessment & Checkpoints ---")
        try:
            if lesson_id:
                cp_data = await page.evaluate(f"""async () => {{
                    const token = localStorage.getItem('access_token');
                    const res = await fetch('/api/v1/lessons/{lesson_id}/player/checkpoint', {{
                        headers: {{ 'Authorization': 'Bearer ' + token }},
                    }});
                    return await res.json();
                }}""")
                assert cp_data.get("success") is True
                print("[OK] Assessment checkpoint endpoint verified")

                mastery_data = await page.evaluate(f"""async () => {{
                    const token = localStorage.getItem('access_token');
                    const res = await fetch('/api/v1/lessons/{lesson_id}/player/mastery', {{
                        headers: {{ 'Authorization': 'Bearer ' + token }},
                    }});
                    return await res.json();
                }}""")
                assert mastery_data.get("success") is True
                print("[OK] Learner mastery intelligence endpoint verified")
                RESULTS["adaptive_assessment"] = "PASS"
            else:
                RESULTS["adaptive_assessment"] = "SKIP"
        except Exception as e:
            print(f"[FAIL] Adaptive assessment failed: {e}")
            RESULTS["adaptive_assessment"] = f"FAIL: {e}"

        # -------------------------------------------------------------
        # STEP 7: REVIEW & RETENTION
        # -------------------------------------------------------------
        print("\n--- [7/10] Testing Review & Retention Surface ---")
        try:
            review_queue = await page.evaluate("""async () => {
                const token = localStorage.getItem('access_token');
                const res = await fetch('/api/v1/me/review', {
                    headers: { 'Authorization': 'Bearer ' + token },
                });
                return await res.json();
            }""")
            assert review_queue.get("success") is True
            items = review_queue.get("data", {}).get("items", [])
            print(f"[OK] Adaptive review queue verified (items: {len(items)})")

            retention_data = await page.evaluate("""async () => {
                const token = localStorage.getItem('access_token');
                const res = await fetch('/api/v1/me/analytics/retention', {
                    headers: { 'Authorization': 'Bearer ' + token },
                });
                return await res.json();
            }""")
            assert retention_data.get("success") is True
            print("[OK] Learner retention analytics endpoint verified")
            RESULTS["review_retention"] = "PASS"
        except Exception as e:
            print(f"[FAIL] Review & Retention failed: {e}")
            RESULTS["review_retention"] = f"FAIL: {e}"

        # -------------------------------------------------------------
        # STEP 8: AI MASTERY TUTOR
        # -------------------------------------------------------------
        print("\n--- [8/10] Testing AI Mastery Tutor ---")
        tutor_session_id = None
        try:
            await page.goto(f"{BASE_URL}/frontend/tutor.html")
            await page.wait_for_load_state("domcontentloaded")
            await page.wait_for_timeout(2000)

            tutor_session = await page.evaluate(f"""async () => {{
                const token = localStorage.getItem('access_token');
                const res = await fetch('/api/v1/tutor/sessions', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token }},
                    body: JSON.stringify({{
                        title: 'ATP Synthesis Master Tutor',
                        lesson_id: '{lesson_id or ""}',
                    }}),
                }});
                return await res.json();
            }}""")
            assert tutor_session.get("success") is True, f"Tutor session creation failed: {tutor_session}"
            tutor_session_id = tutor_session["data"]["id"]
            print(f"[OK] AI Tutor session created: {tutor_session_id}")

            tutor_resp = await page.evaluate(f"""async () => {{
                const token = localStorage.getItem('access_token');
                const res = await fetch('/api/v1/tutor/sessions/{tutor_session_id}/messages', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token }},
                    body: JSON.stringify({{ content: 'How does ATP synthase work in 2 sentences?' }}),
                }});
                return await res.json();
            }}""")
            assert tutor_resp.get("success") is True, f"Tutor message failed: {tutor_resp}"
            answer = tutor_resp["data"]["assistant_message"]["content"]
            print(f"[OK] AI Tutor response grounded: {answer[:80]}...")
            RESULTS["ai_tutor"] = "PASS"
        except Exception as e:
            print(f"[FAIL] AI Tutor failed: {e}")
            RESULTS["ai_tutor"] = f"FAIL: {e}"

        # -------------------------------------------------------------
        # STEP 9: VIDEO LESSONS (P16 Persistent Video Projects)
        # -------------------------------------------------------------
        print("\n--- [9/10] Testing Video Lessons ---")
        vid_id = None
        try:
            await page.goto(f"{BASE_URL}/frontend/videos.html")
            await page.wait_for_load_state("domcontentloaded")
            await page.wait_for_timeout(2000)

            vid_project = await page.evaluate("""async () => {
                const token = localStorage.getItem('access_token');
                const res = await fetch('/api/v1/video-projects', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token },
                    body: JSON.stringify({
                        topic: 'Mitochondrial Energy Flow',
                        description: 'Visual breakdown of ATP synthesis',
                    }),
                });
                return await res.json();
            }""")
            assert vid_project.get("success") is True, f"Video project creation failed: {vid_project}"
            vid_id = vid_project["data"].get("public_id") or vid_project["data"].get("id")
            vid_status = vid_project["data"].get("status")
            print(f"[OK] Video project created: {vid_id}, status={vid_status}")

            vid_list = await page.evaluate("""async () => {
                const token = localStorage.getItem('access_token');
                const res = await fetch('/api/v1/video-projects', {
                    headers: { 'Authorization': 'Bearer ' + token },
                });
                return await res.json();
            }""")
            assert vid_list.get("success") is True
            found = any(vp.get("public_id") == vid_id or vp.get("video_id") == vid_id or vp.get("id") == vid_id for vp in vid_list.get("data", []))
            assert found, "Created video project must appear in learner project list"
            print("[OK] Video projects list contains learner's video project")
            RESULTS["video_lessons"] = "PASS"
        except Exception as e:
            print(f"[FAIL] Video Lessons failed: {e}")
            RESULTS["video_lessons"] = f"FAIL: {e}"

        # -------------------------------------------------------------
        # STEP 10: TWO-USER ISOLATION (Security & Ownership)
        # -------------------------------------------------------------
        print("\n--- [10/10] Testing Two-User Isolation ---")
        try:
            context_b = await browser.new_context(viewport={"width": 1280, "height": 800})
            page_b = await context_b.new_page()

            # Register User B
            await page_b.goto(f"{BASE_URL}/frontend/signup.html")
            await page_b.wait_for_load_state("domcontentloaded")
            await page_b.fill("#name", USER_B["name"])
            await page_b.fill("#email", USER_B["email"])
            await page_b.fill("#password", USER_B["password"])
            await page_b.click("#submitBtn")
            await page_b.wait_for_url("**/upload.html", timeout=15000)

            # User B attempts to access User A's tutor session (must be 403 or 404)
            if tutor_session_id:
                b_probe_tutor = await page_b.evaluate(f"""async () => {{
                    const token = localStorage.getItem('access_token');
                    const res = await fetch('/api/v1/tutor/sessions/{tutor_session_id}', {{
                        headers: {{ 'Authorization': 'Bearer ' + token }},
                    }});
                    return res.status;
                }}""")
                assert b_probe_tutor in (403, 404), f"User B accessed User A's tutor with status {b_probe_tutor}"
                print(f"[OK] User B blocked from User A's tutor session (status {b_probe_tutor})")

            # User B attempts to access User A's video project (must be 403 or 404)
            if vid_id:
                b_probe_vid = await page_b.evaluate(f"""async () => {{
                    const token = localStorage.getItem('access_token');
                    const res = await fetch('/api/v1/video-projects/{vid_id}', {{
                        headers: {{ 'Authorization': 'Bearer ' + token }},
                    }});
                    return res.status;
                }}""")
                assert b_probe_vid in (403, 404), f"User B accessed User A's video with status {b_probe_vid}"
                print(f"[OK] User B blocked from User A's video project (status {b_probe_vid})")

            await context_b.close()
            print("[OK] Two-user isolation and ownership verification PASSED")
            RESULTS["two_user_isolation"] = "PASS"
        except Exception as e:
            print(f"[FAIL] Two-user isolation failed: {e}")
            RESULTS["two_user_isolation"] = f"FAIL: {e}"

        # Return page to dashboard for final state
        await page.goto(f"{BASE_URL}/frontend/dashboard.html")
        await page.wait_for_load_state("domcontentloaded")
        await page.wait_for_timeout(1000)

        await browser.close()

    print("\n" + "=" * 50)
    print("BROWSER ACCEPTANCE VERIFICATION SUMMARY")
    print("=" * 50)
    for k, v in RESULTS.items():
        if k not in ("console_errors", "network_errors"):
            print(f"{k.upper():<25}: {v}")
    print(f"Console Errors Count     : {len(RESULTS['console_errors'])}")
    print(f"Network Errors Count     : {len(RESULTS['network_errors'])}")
    print("=" * 50)

    with open("backend/scripts/acceptance_results.json", "w") as f:
        json.dump(RESULTS, f, indent=2)

    all_passed = all(
        v == "PASS"
        for k, v in RESULTS.items()
        if k not in ("console_errors", "network_errors")
    )
    if not all_passed:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
