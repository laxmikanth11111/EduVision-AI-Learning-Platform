"""End-to-end click-through test for the manual topic entry flow.

Tests: register → login → create presentation → upload source →
       poll processing → manual topics → generate lesson → poll → player
"""
import sys
import time

import httpx

BASE = "http://localhost:8000/api/v1"
EMAIL = "clicktest_e2e@example.com"
PASSWORD = "TestPass1234!"


def log(msg: str) -> None:
    print(f"[CLICK] {msg}", flush=True)


def main():
    log("=" * 60)
    log("E2E CLICK-THROUGH TEST")
    log("=" * 60)

    with httpx.Client(timeout=30.0) as client:
        # ── 1. Register ──
        log("\n--- Step 1: Register ---")
        r = client.post(f"{BASE}/auth/register", json={
            "email": EMAIL, "password": PASSWORD, "name": "Click Test User",
        })
        log(f"Register: {r.status_code}")
        if r.status_code == 201:
            log(f"  user_id={r.json()['user']['id']}")
        elif r.status_code == 409:
            log("  (already exists, continuing)")
        else:
            log(f"  FAIL: {r.text[:200]}")
            return 1

        # ── 2. Login ──
        log("\n--- Step 2: Login ---")
        r = client.post(f"{BASE}/auth/login", json={"email": EMAIL, "password": PASSWORD})
        r.raise_for_status()
        token = r.json()["tokens"]["access_token"]
        log(f"  token={token[:40]}...")
        h = {"Authorization": f"Bearer {token}"}

        # ── 3. Create presentation ──
        log("\n--- Step 3: Create Presentation ---")
        r = client.post(f"{BASE}/presentations", headers=h, json={
            "title": "Computer Architecture",
            "description": "Test presentation for click-through",
        })
        r.raise_for_status()
        data = r.json()
        pres_id = data["data"]["id"]
        log(f"  presentation_id={pres_id}")

        # ── 4. Upload source file ──
        log("\n--- Step 4: Upload Source File ---")
        content = (
            b"# Computer Architecture Overview\n\n"
            b"## CPU and Registers\n\n"
            b"The CPU contains several key components including the ALU, control unit, "
            b"and registers. Registers are small, fast storage locations within the CPU "
            b"that hold data temporarily during processing. Common registers include the "
            b"program counter, stack pointer, and general purpose registers.\n\n"
            b"## Memory Hierarchy\n\n"
            b"Computer memory is organized in a hierarchy from fast but small (registers, cache) "
            b"to large but slower (RAM, disk). Cache memory sits between registers and main memory "
            b"to bridge the speed gap. L1 cache is fastest, L2 is larger but slower, L3 is shared.\n\n"
            b"## Input/Output Systems\n\n"
            b"I/O systems handle communication between the computer and external devices. "
            b"Common I/O interfaces include USB, HDMI, and Ethernet ports. DMA allows direct "
            b"memory access without CPU intervention for high-speed transfers."
        )
        files = {"source": ("topics.txt", content, "text/plain")}
        r = client.post(f"{BASE}/presentations/{pres_id}/source", headers=h, files=files)
        log(f"  Upload: {r.status_code} {r.text[:200]}")
        if r.status_code not in (200, 201):
            return 1

        # ── 5. Poll processing ──
        log("\n--- Step 5: Poll Processing ---")
        for i in range(60):
            r = client.get(f"{BASE}/presentations/{pres_id}", headers=h)
            if r.status_code == 200:
                status = r.json()["data"].get("status", "unknown")
                log(f"  [{i}] status={status}")
                if status in ("ready", "completed", "processed"):
                    break
                if status in ("failed", "error"):
                    log(f"  FAILED: {r.json()}")
                    return 1
            time.sleep(2)

        # ── 6. Check AI topics ──
        log("\n--- Step 6: Check Topics ---")
        r = client.get(f"{BASE}/presentations/{pres_id}/topics", headers=h)
        log(f"  Topics: {r.status_code}")
        if r.status_code == 200:
            topics = r.json()
            if isinstance(topics, dict) and "data" in topics:
                topics = topics["data"]
            log(f"  Found {len(topics) if isinstance(topics, list) else 'N/A'} topics")

        # ── 7. Manual topic lesson generation ──
        log("\n--- Step 7: Generate Lesson (Manual Topics) ---")
        r = client.post(f"{BASE}/presentations/{pres_id}/lessons", headers=h, json={
            "mode": "slide",
            "title": "Computer Architecture Basics",
            "difficulty": "intermediate",
            "topics": ["CPU and Registers", "Memory Hierarchy", "I/O Systems"],
        })
        log(f"  Generate: {r.status_code}")
        if r.status_code not in (200, 201):
            log(f"  FAIL: {r.text[:300]}")
            return 1
        lesson_data = r.json()["data"]
        lesson_id = lesson_data["id"]
        log(f"  lesson_id={lesson_id}")

        # ── 8. Poll lesson status ──
        log("\n--- Step 8: Poll Lesson Status ---")
        for i in range(40):
            r = client.get(f"{BASE}/presentations/{pres_id}/lessons", headers=h)
            if r.status_code == 200:
                lessons_resp = r.json()
                lessons = lessons_resp.get("data", lessons_resp) if isinstance(lessons_resp, dict) else lessons_resp
                if isinstance(lessons, list):
                    for lesson in lessons:
                        ls = lesson.get("status", "unknown")
                        log(f"  [{i}] lesson status={ls}")
                        if ls == "ready":
                            lesson_id = lesson["id"]
                            log(f"  READY! lesson_id={lesson_id}")
                            break
                    else:
                        time.sleep(3)
                        continue
                    break
                else:
                    log(f"  Unexpected response: {str(lessons_resp)[:200]}")
                    break
            time.sleep(3)

        # ── 9. Start player ──
        log("\n--- Step 9: Start Player ---")
        if lesson_id:
            r = client.post(f"{BASE}/lessons/{lesson_id}/player/start", headers=h)
            log(f"  Player: {r.status_code}")
            if r.status_code == 200:
                player = r.json()
                log(f"  session_id={player.get('data', {}).get('session_id', 'N/A')}")
                log("  PLAYER WORKS!")
            else:
                log(f"  FAIL: {r.text[:300]}")
        else:
            log("  No lesson_id, skipping player")

        log("\n" + "=" * 60)
        log("ALL STEPS COMPLETED")
        log("=" * 60)
        return 0


if __name__ == "__main__":
    sys.exit(main())
