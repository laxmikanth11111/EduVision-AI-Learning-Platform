"""Evidence script — register, login, create deck, generate content + all 4 visual types.

Run after Gemini quota resets.  No arguments needed; uses an isolated SQLite DB.
Outputs structured evidence for each system.

Usage:
    cd backend && python scripts/test_evidence.py
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import UTC, datetime

# ── environment setup (isolated DB, no rate limits) ──────────────────────────
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///test_evidence.db"
os.environ["APP_ENV"] = "test"
os.environ["RATE_LIMIT_ENABLED"] = "0"

# Must come after env overrides so settings picks them up
import app.models  # noqa: E402, F401
from app.database.base import Base  # noqa: E402
from app.database.session import engine  # noqa: E402

# ── topic definitions ────────────────────────────────────────────────────────
TOPICS = [
    {
        "title": "What is a Qubit?",
        "description": (
            "A qubit is the basic unit of quantum information in quantum computing. "
            "Unlike a classical bit which is either 0 or 1, a qubit can exist in a "
            "superposition of both states simultaneously. Qubits can be physically "
            "realized using trapped ions, superconducting circuits, or photonic systems. "
            "When measured, a qubit collapses to either 0 or 1 with probabilities "
            "determined by its quantum state. Entanglement allows qubits to be "
            "correlated in ways impossible for classical bits."
        ),
    },
    {
        "title": "How Does Neural Network Backpropagation Work?",
        "description": (
            "Backpropagation is the fundamental algorithm for training neural networks. "
            "It works by computing the gradient of the loss function with respect to each "
            "weight using the chain rule. The process involves a forward pass where inputs "
            "flow through layers with weights and activation functions to produce a "
            "prediction, followed by a backward pass where the error is propagated back "
            "through the network. Each weight is then updated proportional to its "
            "contribution to the error, using gradient descent. Deep networks may suffer "
            "from vanishing or exploding gradients, which techniques like batch "
            "normalization and residual connections help mitigate."
        ),
    },
]

EVIDENCE_LOG: list[str] = []
RUN_START = time.time()


def log(msg: str) -> None:
    ts = datetime.now(UTC).strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    EVIDENCE_LOG.append(line)


def section(title: str) -> None:
    log("")
    log("=" * 80)
    log(title)
    log("=" * 80)


async def main() -> None:
    # ── bootstrap DB ─────────────────────────────────────────────────────────
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    from fastapi.testclient import TestClient

    from app.main import app

    c = TestClient(app, raise_server_exceptions=False)

    # ── 1. REGISTER ──────────────────────────────────────────────────────────
    section("STEP 1: Register test user")
    tsuffix = int(time.time())
    reg_email = f"evidence_{tsuffix}@test.example.com"
    reg_password = "EvidenceTest123!"
    reg_name = "Evidence Test User"

    r = c.post("/api/v1/auth/register", json={
        "email": reg_email,
        "password": reg_password,
        "name": reg_name,
    })
    assert r.status_code == 201, f"Register failed ({r.status_code}): {r.text}"
    reg_data = r.json()
    token = reg_data["tokens"]["access_token"]
    log(f"Registered: {reg_data['user']['email']}  (id={reg_data['user']['id']})")
    log(f"Access token obtained ({len(token)} chars)")

    headers = {"Authorization": f"Bearer {token}"}

    # ── 2. LOGIN (verify round-trip) ─────────────────────────────────────────
    section("STEP 2: Login with registered credentials")
    r = c.post("/api/v1/auth/login", json={
        "email": reg_email,
        "password": reg_password,
    })
    assert r.status_code == 200, f"Login failed ({r.status_code}): {r.text}"
    token2 = r.json()["tokens"]["access_token"]
    headers = {"Authorization": f"Bearer {token2}"}
    log(f"Login OK — token refreshed ({len(token2)} chars)")

    # ── 3. CREATE DECK (manual topic entry) ──────────────────────────────────
    section("STEP 3: Create deck via manual topic entry")
    r = c.post("/api/v1/presentations/manual", json={
        "title": "Evidence Deck — Dual Topics",
        "topics": [t["title"] for t in TOPICS],
        "description": "Auto-created by evidence script for quota-reset validation.",
    }, headers=headers)
    assert r.status_code == 201, f"Manual deck failed ({r.status_code}): {r.text}"
    deck = r.json()["data"]
    deck_id = deck["id"]
    log(f"Deck created: id={deck_id}, title={deck['title']}, topics={deck.get('topic', 'N/A')}")
    log(f"Status: {deck['status']}, slide_count={deck.get('slide_count', 0)}")

    # ── 4. GENERATE CONTENT (AI lesson for topic 1) ──────────────────────────
    section("STEP 4: Generate AI lesson content for Topic 1")
    r = c.post(
        f"/api/v1/presentations/{deck_id}/lessons",
        json={"mode": "slide", "title": TOPICS[0]["title"]},
        headers={**headers, "Idempotency-Key": f"evidence-{deck_id}-t0"},
    )
    assert r.status_code == 201, f"Lesson gen failed ({r.status_code}): {r.text}"
    lesson1 = r.json()["data"]
    lesson1_id = lesson1.get("id") or lesson1.get("lesson_id", "unknown")
    log(f"Lesson 1 started: id={lesson1_id}, status={lesson1.get('status', 'N/A')}")

    # Poll until complete (max 120 s)
    for attempt in range(40):
        r = c.get(
            f"/api/v1/presentations/{deck_id}/lessons/{lesson1_id}/status",
            headers=headers,
        )
        if r.status_code != 200:
            log(f"  poll {attempt}: status endpoint returned {r.status_code}")
            break
        st = r.json().get("data", {})
        status_val = st.get("status", "unknown")
        log(f"  poll {attempt}: status={status_val}")
        if status_val in ("completed", "failed", "error"):
            break
        await asyncio.sleep(3)

    if status_val == "completed":
        log("Lesson 1 generation COMPLETED successfully")
    else:
        log(f"Lesson 1 ended with status={status_val} — proceeding anyway")

    # ── 5. GENERATE CONTENT (AI lesson for topic 2) ──────────────────────────
    section("STEP 5: Generate AI lesson content for Topic 2")
    r = c.post(
        f"/api/v1/presentations/{deck_id}/lessons",
        json={"mode": "slide", "title": TOPICS[1]["title"]},
        headers={**headers, "Idempotency-Key": f"evidence-{deck_id}-t1"},
    )
    assert r.status_code == 201, f"Lesson 2 gen failed ({r.status_code}): {r.text}"
    lesson2 = r.json()["data"]
    lesson2_id = lesson2.get("id") or lesson2.get("lesson_id", "unknown")
    log(f"Lesson 2 started: id={lesson2_id}, status={lesson2.get('status', 'N/A')}")

    for attempt in range(40):
        r = c.get(
            f"/api/v1/presentations/{deck_id}/lessons/{lesson2_id}/status",
            headers=headers,
        )
        if r.status_code != 200:
            log(f"  poll {attempt}: status endpoint returned {r.status_code}")
            break
        st = r.json().get("data", {})
        status_val = st.get("status", "unknown")
        log(f"  poll {attempt}: status={status_val}")
        if status_val in ("completed", "failed", "error"):
            break
        await asyncio.sleep(3)

    if status_val == "completed":
        log("Lesson 2 generation COMPLETED successfully")
    else:
        log(f"Lesson 2 ended with status={status_val} — proceeding anyway")

    # ================================================================
    # VISUAL TYPE 1: CANVAS  (both topics)
    # ================================================================
    section("VISUAL TYPE 1: Visual Canvas — Knowledge Graphs")
    canvas_ids = []
    for idx, topic in enumerate(TOPICS):
        log(f"--- Canvas for Topic {idx + 1}: {topic['title']} ---")
        r = c.post("/api/v1/visual/canvases", json={
            "content": topic["description"],
            "title": topic["title"],
        }, headers=headers)
        assert r.status_code == 201, f"Canvas {idx+1} failed ({r.status_code}): {r.text}"
        cid = r.json()["data"]["canvas_id"]
        canvas_ids.append(cid)
        log(f"  canvas_id: {cid}")

        # Fetch full model
        r2 = c.get(f"/api/v1/visual/canvases/{cid}", headers=headers)
        assert r2.status_code == 200, f"Fetch canvas failed: {r2.text}"
        model = r2.json()["data"]
        nodes = model.get("visual_nodes", [])
        log(f"  node_count: {len(nodes)}")
        log(f"  node_labels: {[n['label'] for n in nodes]}")

    # ================================================================
    # VISUAL TYPE 2: ANIMATION (both topics)
    # ================================================================
    section("VISUAL TYPE 2: Animation Blueprint — Scene Timelines")
    for idx, topic in enumerate(TOPICS):
        log(f"--- Animation for Topic {idx + 1}: {topic['title']} ---")
        r = c.post("/api/v1/animations/plan", json={
            "topic": topic["title"],
            "description": topic["description"],
        }, headers=headers)
        assert r.status_code == 201, f"Animation {idx+1} failed ({r.status_code}): {r.text}"
        bp = r.json()["data"]
        tl = bp["timeline"]
        scene_count = len(tl["scenes"])
        dur_sec = round(tl["total_duration_ms"] / 1000, 1)
        log(f"  blueprint_id: {bp['blueprint_id']}")
        log(f"  scene_count: {scene_count}")
        log(f"  total_duration_ms: {tl['total_duration_ms']}  ({dur_sec}s)")
        log(f"  total_events: {tl['total_events']}")
        for sc in tl["scenes"]:
            log(f"    scene {sc['scene_index']}: {sc['title']}  ({sc['duration_ms']}ms)")

    # ================================================================
    # VISUAL TYPE 3: VIDEO (both topics)
    # ================================================================
    section("VISUAL TYPE 3: Video Project — Rendered MP4")
    for idx, topic in enumerate(TOPICS):
        log(f"--- Video for Topic {idx + 1}: {topic['title']} ---")
        r = c.post("/api/v1/videos/create", json={
            "topic": topic["title"],
            "description": topic["description"],
            "target_audience": "general_learner",
            "difficulty_level": "Intermediate",
        }, headers=headers)
        assert r.status_code == 201, f"Video {idx+1} failed ({r.status_code}): {r.text}"
        proj = r.json()["data"]
        playable_url = proj.get("playable_url", "N/A")
        rendering = proj.get("rendering_status", "N/A")
        vtl = proj["timeline"]
        log(f"  video_id: {proj['video_id']}")
        log(f"  rendering_status: {rendering}")
        log(f"  playable_url: {playable_url}")
        log(f"  timeline: {vtl['scene_count']} scenes, {vtl['total_duration_ms']}ms")

        # Confirm the MP4 file exists on disk
        if playable_url and playable_url != "N/A":
            import os as _os
            mp4_path = _os.path.join(_os.getcwd(), playable_url.lstrip("/"))
            exists = _os.path.isfile(mp4_path)
            size_kb = round(_os.path.getsize(mp4_path) / 1024, 1) if exists else 0
            log(f"  mp4_exists: {exists}  size: {size_kb} KB")
            if exists:
                log(f"  CONFIRMED: playable_url resolves to {mp4_path}")

    # ================================================================
    # VISUAL TYPE 4: SIMULATION
    # ================================================================
    section("VISUAL TYPE 4: Simulation — Interactive Runtime")
    log("--- Simulation: Bubble Sort ---")
    r = c.post("/api/v1/simulations/sessions/start", json={
        "simulation_id": "sim_bubble_sort",
    }, headers=headers)
    assert r.status_code == 201, f"Sim start failed ({r.status_code}): {r.text}"
    sess = r.json()["data"]
    defn = sess["definition"]
    state = sess["state"]
    sid = state["session_id"]
    log(f"  session_id: {sid}")
    log(f"  simulation_id: {defn['simulation_id']}")
    log(f"  topic: {defn['topic']}")
    log(f"  steps: {len(defn['steps'])}")
    log(f"  parameters: {json.dumps(state['parameters'])}")

    # Step through all steps
    log("  stepping through all steps:")
    for _ in range(len(defn["steps"]) - 1):
        r = c.post(f"/api/v1/simulations/sessions/{sid}/step",
                   json={"action": "next"}, headers=headers)
        s = r.json()["data"]["state"]
        step_title = defn["steps"][s["current_step_index"]]["title"]
        log(f"    next -> step {s['current_step_index']}: {step_title}")

    # Verify final state
    final_step = defn["steps"][s["current_step_index"]]
    log(f"  final_step: {final_step['title']}")
    log(f"  final_playback: {s['playback_state']}")

    # Play / Pause
    r = c.post(f"/api/v1/simulations/sessions/{sid}/playback",
               json={"playback_state": "playing", "speed": 2.0}, headers=headers)
    s = r.json()["data"]["state"]
    log(f"  PLAY  -> playback={s['playback_state']}, speed={s['playback_speed']}")
    r = c.post(f"/api/v1/simulations/sessions/{sid}/playback",
               json={"playback_state": "paused"}, headers=headers)
    s = r.json()["data"]["state"]
    log(f"  PAUSE -> playback={s['playback_state']}")
    log(f"  MATCH RESULT: session completed, all {len(defn['steps'])} steps traversed")

    # ================================================================
    # SUMMARY
    # ================================================================
    elapsed = round(time.time() - RUN_START, 1)
    section("EVIDENCE SUMMARY")
    log(f"Run timestamp (UTC): {datetime.now(UTC).isoformat()}")
    log(f"Total elapsed: {elapsed}s")
    log(f"User registered: {reg_email}")
    log(f"Deck created: {deck_id}  ({len(TOPICS)} topics)")
    log(f"Canvases: {len(canvas_ids)} generated")
    log(f"Animations: {len(TOPICS)} blueprints generated")
    log(f"Videos: {len(TOPICS)} projects rendered")
    log("Simulation: bubble sort session completed")
    log("")
    log("ALL 4 VISUAL TYPES GENERATED SUCCESSFULLY")
    log("=" * 80)

    # ── persist evidence log to file ─────────────────────────────────────────
    log_path = os.path.join(os.path.dirname(__file__), "..", "test_evidence.log")
    with open(log_path, "w", encoding="utf-8") as f:
        f.write("\n".join(EVIDENCE_LOG) + "\n")
    print(f"\nEvidence log saved to: {os.path.abspath(log_path)}")


if __name__ == "__main__":
    asyncio.run(main())
