"""Unit Tests for Phase 4K.3 + 4K.4 Interactive Video Runtime Synchronization.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.learning_context_service import learning_context_service


@pytest.mark.asyncio
async def test_video_runtime_sync_and_state_endpoints(
    client: AsyncClient,
    db_session: AsyncSession,
):
    ctx = learning_context_service.create_session(topic="Computer Architecture")

    # 1. Sync Video Runtime Step
    sync_res = await client.post(
        "/api/v1/videos/runtime/sync",
        json={
            "session_id": ctx.session_id,
            "video_id": "video_101",
            "scene_index": 1,
            "current_timestamp_ms": 7500.0,
            "component_id": "comp_fetch",
        },
    )
    assert sync_res.status_code == 200
    sync_data = sync_res.json()["data"]
    assert sync_data["video_id"] == "video_101"
    assert sync_data["scene_index"] == 1

    # 2. Get Video Runtime State
    state_res = await client.get(f"/api/v1/videos/runtime/state/{ctx.session_id}")
    assert state_res.status_code == 200
    state_data = state_res.json()["data"]
    assert state_data["component_id"] == "comp_fetch"

    # 3. Create Video Bookmark
    bm_res = await client.post(
        "/api/v1/videos/runtime/bookmark",
        json={
            "session_id": ctx.session_id,
            "video_id": "video_101",
            "time_ms": 7500.0,
            "title": "Important Pipeline Stage",
        },
    )
    assert bm_res.status_code == 201
    assert bm_res.json()["data"]["title"] == "Important Pipeline Stage"

    # 4. Submit Assessment Checkpoint
    assess_res = await client.post(
        "/api/v1/videos/runtime/assessment",
        json={
            "session_id": ctx.session_id,
            "video_id": "video_101",
            "scene_index": 1,
            "selected_option": "Instruction Decode Unit",
        },
    )
    assert assess_res.status_code == 200
    assert assess_res.json()["data"]["is_correct"] is True

    # 5. Get AI Tutor Video Context
    tutor_res = await client.get(f"/api/v1/videos/runtime/tutor-context/{ctx.session_id}")
    assert tutor_res.status_code == 200
    assert tutor_res.json()["data"]["active_video_id"] == "video_101"
