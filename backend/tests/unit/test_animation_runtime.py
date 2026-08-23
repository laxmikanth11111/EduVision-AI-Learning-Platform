"""Unit Tests for Phase 4J.3 + 4J.4 Interactive Animation Runtime Synchronization.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.learning_context_service import learning_context_service


@pytest.mark.asyncio
async def test_animation_runtime_sync_api_endpoints(
    client: AsyncClient,
    db_session: AsyncSession,
):
    ctx = learning_context_service.create_session(topic="Computer Architecture")

    # 1. Sync Animation Runtime Step Endpoint
    sync_res = await client.post(
        "/api/v1/animations/runtime/sync",
        json={
            "session_id": ctx.session_id,
            "blueprint_id": "bp_101",
            "scene_index": 2,
            "event_id": "evt_glow_1",
            "component_id": "comp_cpu",
        },
    )
    assert sync_res.status_code == 200
    sync_data = sync_res.json()["data"]
    assert sync_data["blueprint_id"] == "bp_101"
    assert sync_data["scene_index"] == 2

    # 2. Get Runtime State Endpoint
    state_res = await client.get(f"/api/v1/animations/runtime/state/{ctx.session_id}")
    assert state_res.status_code == 200
    state_data = state_res.json()["data"]
    assert state_data["component_id"] == "comp_cpu"
