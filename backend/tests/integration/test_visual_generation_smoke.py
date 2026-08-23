"""Smoke tests for all 4 visual generation systems.

Tests real generation flow for each system with a real topic description,
verifying the Topic model (title + description) is properly wired through
to canvas, animation, video, and simulation outputs.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

TOPIC_TITLE = "Bubble Sort Algorithm"
TOPIC_DESCRIPTION = (
    "Bubble sort is a simple comparison-based sorting algorithm. "
    "It repeatedly steps through the list, compares adjacent elements, "
    "and swaps them if they are in the wrong order. The pass through "
    "the list is repeated until the list is sorted."
)


@pytest.mark.asyncio
async def test_canvas_generation_from_topic_description(client: AsyncClient):
    """Visual Canvas: generate a knowledge graph canvas from a topic description."""
    res = await client.post(
        "/api/v1/visual/canvases",
        json={"content": TOPIC_DESCRIPTION, "title": TOPIC_TITLE},
    )
    assert res.status_code == 201
    data = res.json()["data"]
    assert "canvas_id" in data
    assert data["public_id"]
    assert data["title"] == TOPIC_TITLE
    assert data["category"]
    assert data["pattern_type"]


@pytest.mark.asyncio
async def test_animation_blueprint_from_topic_description(client: AsyncClient):
    """Animation Planner: generate an animation blueprint from a topic description."""
    res = await client.post(
        "/api/v1/animations/plan",
        json={"topic": TOPIC_TITLE, "description": TOPIC_DESCRIPTION},
    )
    assert res.status_code == 201
    data = res.json()["data"]
    assert data["blueprint_id"].startswith("anim_")
    assert data["topic"] == TOPIC_TITLE
    assert len(data["timeline"]["scenes"]) >= 2
    assert data["timeline"]["total_duration_ms"] > 0
    assert data["validation"]["is_valid"] is True
    assert data["validation"]["coverage_score"] == 100.0


@pytest.mark.asyncio
async def test_animation_blueprint_fallback_without_description(client: AsyncClient):
    """Animation Planner: still works with explicit components (no description)."""
    res = await client.post(
        "/api/v1/animations/plan",
        json={
            "topic": "CPU Pipeline",
            "components": [
                {"component_id": "c1", "name": "Fetch", "short_description": "Fetch stage"},
                {"component_id": "c2", "name": "Decode", "short_description": "Decode stage"},
            ],
        },
    )
    assert res.status_code == 201
    data = res.json()["data"]
    assert data["blueprint_id"].startswith("anim_")
    assert len(data["timeline"]["scenes"]) >= 3


@pytest.mark.asyncio
async def test_animation_runtime_state_tracking(client: AsyncClient):
    """Animation Runtime: sync position and retrieve runtime state."""
    plan_res = await client.post(
        "/api/v1/animations/plan",
        json={"topic": "Test Topic", "description": "A test topic for runtime state."},
    )
    blueprint_id = plan_res.json()["data"]["blueprint_id"]

    sync_res = await client.post(
        "/api/v1/animations/runtime/sync",
        json={
            "session_id": "test_anim_session",
            "blueprint_id": blueprint_id,
            "scene_index": 1,
        },
    )
    assert sync_res.status_code == 200
    assert sync_res.json()["success"] is True

    state_res = await client.get("/api/v1/animations/runtime/state/test_anim_session")
    assert state_res.status_code == 200
    state_data = state_res.json()["data"]
    assert state_data["scene_index"] == 1
    assert state_data["last_sync_timestamp"] > 0


@pytest.mark.asyncio
async def test_video_project_from_topic_description(client: AsyncClient):
    """Video Composition: generate a complete video project from a topic description."""
    res = await client.post(
        "/api/v1/videos/create",
        json={
            "topic": TOPIC_TITLE,
            "description": TOPIC_DESCRIPTION,
            "target_audience": "general_learner",
            "difficulty_level": "Beginner",
        },
    )
    assert res.status_code == 201
    data = res.json()["data"]
    assert data["video_id"].startswith("video_")
    assert data["topic"] == TOPIC_TITLE
    assert data["timeline"]["scene_count"] >= 2
    assert data["timeline"]["total_duration_ms"] > 0
    assert data["validation"]["is_valid"] is True


@pytest.mark.asyncio
async def test_video_storyboard_from_topic_description(client: AsyncClient):
    """Video Storyboard: generate a storyboard from a topic description."""
    res = await client.post(
        "/api/v1/videos/storyboard",
        json={"topic": TOPIC_TITLE, "description": TOPIC_DESCRIPTION},
    )
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["topic"] == TOPIC_TITLE
    assert len(data["scenes"]) >= 2


@pytest.mark.asyncio
async def test_video_script_from_topic_description(client: AsyncClient):
    """Video Script: generate a teaching script from a topic description."""
    res = await client.post(
        "/api/v1/videos/script",
        json={"topic": TOPIC_TITLE, "description": TOPIC_DESCRIPTION},
    )
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["topic"] == TOPIC_TITLE
    assert len(data["sections"]) >= 1


@pytest.mark.asyncio
async def test_video_runtime_sync(client: AsyncClient):
    """Video Runtime: sync playback position."""
    create_res = await client.post(
        "/api/v1/videos/create",
        json={"topic": "Test Video", "description": "A test topic for video runtime."},
    )
    video_id = create_res.json()["data"]["video_id"]

    sync_res = await client.post(
        "/api/v1/videos/runtime/sync",
        json={
            "session_id": "test_vid_session",
            "video_id": video_id,
            "scene_index": 0,
            "current_timestamp_ms": 5000.0,
        },
    )
    assert sync_res.status_code == 200
    assert sync_res.json()["success"] is True

    state_res = await client.get("/api/v1/videos/runtime/state/test_vid_session")
    assert state_res.status_code == 200
    state_data = state_res.json()["data"]
    assert state_data["video_id"] == video_id
    assert state_data["current_timestamp_ms"] == 5000.0


@pytest.mark.asyncio
async def test_video_bookmark(client: AsyncClient):
    """Video Runtime: create a timestamp bookmark."""
    create_res = await client.post(
        "/api/v1/videos/create",
        json={"topic": "Bookmark Test", "description": "Testing bookmark creation."},
    )
    video_id = create_res.json()["data"]["video_id"]

    bookmark_res = await client.post(
        "/api/v1/videos/runtime/bookmark",
        json={
            "session_id": "test_bookmark_session",
            "video_id": video_id,
            "time_ms": 12000.0,
            "title": "Key Concept",
        },
    )
    assert bookmark_res.status_code == 201


@pytest.mark.asyncio
async def test_simulation_bubble_sort_full_lifecycle(client: AsyncClient):
    """Simulation: full lifecycle with pre-registered bubble sort definition."""
    start_res = await client.post(
        "/api/v1/simulations/sessions/start",
        json={"simulation_id": "sim_bubble_sort"},
    )
    assert start_res.status_code == 201
    session_data = start_res.json()["data"]
    state = session_data["state"]
    definition = session_data["definition"]

    assert definition["simulation_id"] == "sim_bubble_sort"
    assert definition["topic"] == "Bubble Sort Algorithm"
    assert len(definition["steps"]) >= 2
    assert state["current_step_index"] == 0
    assert state["playback_state"] == "paused"

    session_id = state["session_id"]

    # Step forward
    step_res = await client.post(
        f"/api/v1/simulations/sessions/{session_id}/step",
        json={"action": "next"},
    )
    assert step_res.status_code == 200
    assert step_res.json()["data"]["state"]["current_step_index"] == 1

    # Step backward
    step_back_res = await client.post(
        f"/api/v1/simulations/sessions/{session_id}/step",
        json={"action": "prev"},
    )
    assert step_back_res.status_code == 200
    assert step_back_res.json()["data"]["state"]["current_step_index"] == 0

    # Play/pause
    play_res = await client.post(
        f"/api/v1/simulations/sessions/{session_id}/playback",
        json={"playback_state": "playing", "speed": 2.0},
    )
    assert play_res.status_code == 200
    assert play_res.json()["data"]["state"]["playback_state"] == "playing"
    assert play_res.json()["data"]["state"]["playback_speed"] == 2.0

    pause_res = await client.post(
        f"/api/v1/simulations/sessions/{session_id}/playback",
        json={"playback_state": "paused"},
    )
    assert pause_res.status_code == 200
    assert pause_res.json()["data"]["state"]["playback_state"] == "paused"


@pytest.mark.asyncio
async def test_simulation_cpu_cycle(client: AsyncClient):
    """Simulation: CPU fetch-execute cycle session."""
    start_res = await client.post(
        "/api/v1/simulations/sessions/start",
        json={"simulation_id": "sim_cpu_fetch_execute"},
    )
    assert start_res.status_code == 201
    state = start_res.json()["data"]["state"]
    definition = start_res.json()["data"]["definition"]

    assert definition["simulation_id"] == "sim_cpu_fetch_execute"
    assert definition["category"] == "System Architecture"
    assert len(definition["steps"]) >= 3
    assert len(definition["parameters"]) >= 1

    session_id = state["session_id"]

    # Walk through all steps
    for _ in range(len(definition["steps"]) - 1):
        step_res = await client.post(
            f"/api/v1/simulations/sessions/{session_id}/step",
            json={"action": "next"},
        )
        assert step_res.status_code == 200

    final_state = step_res.json()["data"]["state"]
    assert final_state["playback_state"] == "completed"
    assert final_state["current_step_index"] == len(definition["steps"]) - 1


@pytest.mark.asyncio
async def test_simulation_list_definitions(client: AsyncClient):
    """Simulation: list available definitions."""
    res = await client.get("/api/v1/simulations/definitions")
    assert res.status_code == 200
    defs = res.json()["data"]
    assert len(defs) >= 2
    ids = [d["simulation_id"] for d in defs]
    assert "sim_bubble_sort" in ids
    assert "sim_cpu_fetch_execute" in ids
