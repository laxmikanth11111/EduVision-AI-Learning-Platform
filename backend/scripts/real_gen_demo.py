"""Real generation demo — runs all 4 visual systems against 'What is a Qubit?'."""

import asyncio
import json
import os

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///real_gen_demo.db"
os.environ["APP_ENV"] = "test"
os.environ["RATE_LIMIT_ENABLED"] = "0"

import app.models  # noqa: E402, F401
from app.database.base import Base  # noqa: E402
from app.database.session import engine  # noqa: E402

TOPIC = "What is a Qubit?"
DESC = (
    "A qubit is the basic unit of quantum information in quantum computing. "
    "Unlike a classical bit which is either 0 or 1, a qubit can exist in a "
    "superposition of both states simultaneously. Qubits can be physically "
    "realized using trapped ions, superconducting circuits, or photonic systems. "
    "When measured, a qubit collapses to either 0 or 1 with probabilities "
    "determined by its quantum state. Entanglement allows qubits to be "
    "correlated in ways impossible for classical bits."
)


async def demo():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    from fastapi.testclient import TestClient

    from app.main import app
    from app.services.visual_intelligence_service import VisualIntelligenceService

    c = TestClient(app, raise_server_exceptions=False)
    intel = VisualIntelligenceService()
    model = await intel.generate_visual_learning_model(DESC, title=TOPIC)

    # ================================================================
    # 1. VISUAL CANVAS
    # ================================================================
    print("=" * 80)
    print("1. VISUAL CANVAS — Knowledge Graph from Topic Description")
    print("=" * 80)
    print(f"Topic: {model.topic}")
    print(f"Classification: {model.classification.primary_category.value} "
          f"(confidence: {model.classification.confidence_score})")
    print(f"Visualization: {model.visualization_decision.visualization_type.value}")
    print(f"  Reason: {model.visualization_decision.reason}")
    print()
    print(f"COMPONENTS ({len(model.components)}):")
    for i, comp in enumerate(model.components):
        print(f"  [{i + 1}] {comp.name} ({comp.category})")
        print(f"      {comp.short_description}")
    print()
    print(f"RELATIONSHIPS ({len(model.relationships)}):")
    for rel in model.relationships:
        print(f"  {rel.source_id} --[{rel.relationship_type.value}]--> {rel.target_id}")
    print()
    print(f"VISUAL NODES ({len(model.visual_nodes)}):")
    for vn in model.visual_nodes:
        attrs = {k: v for k, v in vn.model_dump().items()
                 if k not in ("node_id", "label", "node_type") and v is not None}
        print(f"  {vn.node_id}: {vn.label} (type={vn.node_type}) {json.dumps(attrs)}")
    print()
    print(f"VISUAL EDGES ({len(model.visual_edges)}):")
    for ve in model.visual_edges:
        print(f"  {ve.source} --> {ve.target} ({ve.edge_type})")
    print()
    print(f"Layout: {model.suggested_layout.layout_type}")
    print(f"  Reason: {model.suggested_layout.reason}")

    # ================================================================
    # 2. ANIMATION BLUEPRINT
    # ================================================================
    print()
    print("=" * 80)
    print("2. ANIMATION BLUEPRINT — Scene Timeline from Topic Description")
    print("=" * 80)
    r = c.post("/api/v1/animations/plan",
               json={"topic": TOPIC, "description": DESC})
    assert r.status_code == 201, f"Animation plan failed: {r.text}"
    bp = r.json()["data"]
    tl = bp["timeline"]

    dur_sec = round(tl["total_duration_ms"] / 1000, 1)
    print(f"Blueprint ID: {bp['blueprint_id']}")
    print(f"Topic: {bp['topic']}")
    print(f"Total Duration: {tl['total_duration_ms']}ms = {dur_sec}s")
    print(f"Estimated Minutes: {tl['estimated_minutes']}")
    print(f"Total Events: {tl['total_events']}")
    print(f"Scenes: {len(tl['scenes'])}")
    print(f"Validation: valid={bp['validation']['is_valid']}, "
          f"coverage={bp['validation']['coverage_score']}%")
    print(f"Classification: {bp['classification']['recommended_style']}")
    print()
    for scene in tl["scenes"]:
        print(f"  Scene {scene['scene_index']}: {scene['title']}")
        print(f"    Duration: {scene['duration_ms']}ms | "
              f"Transition: {scene['transition']}")
        print(f"    Objective: {scene['learning_objective']}")
        for evt in scene["events"]:
            cue = evt.get("narration_cue", {})
            text = cue.get("text_emphasis", "") if cue else ""
            print(f"      [{evt['event_type']}] @{evt['timestamp_ms']}ms "
                  f"target={evt['target_id']} "
                  f"narration=\"{text}\"")
    print()

    # ================================================================
    # 3. VIDEO PROJECT
    # ================================================================
    print("=" * 80)
    print("3. VIDEO PROJECT — Full Composition from Topic Description")
    print("=" * 80)
    r = c.post("/api/v1/videos/create", json={
        "topic": TOPIC, "description": DESC,
        "target_audience": "general_learner",
        "difficulty_level": "Intermediate",
    })
    assert r.status_code == 201, f"Video create failed: {r.text}"
    proj = r.json()["data"]
    vtl = proj["timeline"]
    print(f"Video ID: {proj['video_id']}")
    print(f"Topic: {proj['topic']}")
    print(f"Rendering: {proj.get('rendering_status', 'N/A')}")
    print(f"Timeline: {vtl['scene_count']} scenes, "
          f"{vtl['total_duration_ms']}ms ({round(vtl['total_duration_ms']/1000, 1)}s)")
    print(f"Validation: valid={proj['validation']['is_valid']}")
    print()
    for sc in vtl["scenes"]:
        narr = sc.get("narration_text", "")
        print(f"  Scene {sc['scene_index']}: {sc['title']}")
        print(f"    Duration: {sc['duration_ms']}ms | Type: {sc.get('scene_type', 'N/A')}")
        if narr:
            print(f"    Narration: {narr[:150]}")
    print()

    # Storyboard
    print("--- STORYBOARD ---")
    r2 = c.post("/api/v1/videos/storyboard",
                json={"topic": TOPIC, "description": DESC})
    sb = r2.json()["data"]
    for sc in sb.get("scenes", []):
        print(f"  Scene {sc['scene_index']}: {sc['title']}")
        print(f"    Visual: {sc.get('visual_description', 'N/A')[:120]}")
        print(f"    Duration: {sc['duration_ms']}ms")
    print()

    # Script
    print("--- SCRIPT ---")
    r3 = c.post("/api/v1/videos/script",
                json={"topic": TOPIC, "description": DESC})
    scr = r3.json()["data"]
    for sec in scr.get("sections", []):
        print(f"  [{sec.get('section_type', 'N/A')}] {sec.get('section_title', 'N/A')}")
        print(f"    {sec.get('text', 'N/A')[:160]}")

    # ================================================================
    # 4. SIMULATION
    # ================================================================
    print()
    print("=" * 80)
    print("4. SIMULATION — Interactive Runtime (Bubble Sort)")
    print("=" * 80)
    r = c.post("/api/v1/simulations/sessions/start",
               json={"simulation_id": "sim_bubble_sort"})
    assert r.status_code == 201, f"Sim start failed: {r.text}"
    sess = r.json()["data"]
    defn = sess["definition"]
    state = sess["state"]
    sid = state["session_id"]
    print(f"Session: {sid}")
    print(f"Simulation: {defn['simulation_id']}")
    print(f"Topic: {defn['topic']}")
    print(f"Category: {defn['category']}")
    print(f"Description: {defn['description']}")
    print()
    print("CONTROLS — what the user can adjust:")
    for p in defn["parameters"]:
        print(f"  {p['parameter_id']} ({p['data_type']}): "
              f"default={p['default_value']}, range=[{p['min_value']}, {p['max_value']}]")
    print()
    print("STEPS — the interactive walkthrough:")
    for step in defn["steps"]:
        print(f"  Step {step['step_number']}: {step['title']}")
        print(f"    {step['description'][:120]}")
        if step.get("active_components"):
            print(f"    Active: {step['active_components']}")
    print()
    print("CHECKPOINTS:")
    for cp in defn["checkpoints"]:
        print(f"  {cp['checkpoint_id']}: {cp['title']}")
        print(f"    {cp['explanation'][:120]}")
    print()
    print("LEARNING OBJECTIVES:")
    for obj in defn["learning_objectives"]:
        print(f"  - {obj}")
    print()
    print(f"Initial State: step={state['current_step_index']}, "
          f"playback={state['playback_state']}, speed={state['playback_speed']}")
    print(f"Parameters: {json.dumps(state['parameters'])}")
    print()
    print("LIFECYCLE:")
    # step forward through all
    for _ in range(len(defn["steps"]) - 1):
        r = c.post(f"/api/v1/simulations/sessions/{sid}/step",
                   json={"action": "next"})
        s = r.json()["data"]["state"]
        step_title = defn["steps"][s["current_step_index"]]["title"]
        print(f"  next -> step {s['current_step_index']}: {step_title} "
              f"(state={s['playback_state']})")
    final = s
    print(f"  FINAL: playback={final['playback_state']}, "
          f"step={final['current_step_index']}")
    print()

    # Step back
    r = c.post(f"/api/v1/simulations/sessions/{sid}/step",
               json={"action": "prev"})
    s = r.json()["data"]["state"]
    print(f"  prev -> step {s['current_step_index']}: "
          f"{defn['steps'][s['current_step_index']]['title']}")

    # Play
    r = c.post(f"/api/v1/simulations/sessions/{sid}/playback",
               json={"playback_state": "playing", "speed": 2.0})
    s = r.json()["data"]["state"]
    print(f"  PLAY -> playback={s['playback_state']}, speed={s['playback_speed']}")

    # Pause
    r = c.post(f"/api/v1/simulations/sessions/{sid}/playback",
               json={"playback_state": "paused"})
    s = r.json()["data"]["state"]
    print(f"  PAUSE -> playback={s['playback_state']}")

    print()
    print("=" * 80)
    print("DONE — All 4 systems generated real output from topic description")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(demo())
