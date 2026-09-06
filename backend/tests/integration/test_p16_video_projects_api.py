"""P16 integration tests for the async learner-owned video runtime API.

Covers create → (background render) → ready poll, explicit re-render, 404 for
unknown projects, 409 for the per-user concurrency cap, and request validation.
The app test env pins ``VIDEO_RENDER_BACKEND=mock`` + ``VIDEO_RENDER_EXECUTOR=inline``
(see conftest), so renders complete deterministically without FFmpeg/OpenCV.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import delete

from app.models.video_project import VideoProjectRecord, VideoRenderStatus
from app.services.video_project_builder import build_visual_learning_model, compose_project
from tests.conftest import TEST_USER_ID, TestSessionLocal

pytestmark = pytest.mark.asyncio


async def _wait_for(client: AsyncClient, public_id: str, status: str, timeout: float = 5.0) -> dict[str, Any]:
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        resp = await client.get(f"/api/v1/video-projects/{public_id}")
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        if data["status"] == status:
            return data
        assert asyncio.get_running_loop().time() < deadline, f"timeout waiting for {status}: {data}"
        await asyncio.sleep(0.01)


async def _seed_active_projects(count: int) -> list[str]:
    """Insert queued/rendering rows directly so the cap is deterministic."""
    from app.services.video_project_service import VideoProjectService

    public_ids: list[str] = []
    async with TestSessionLocal() as session:
        service = VideoProjectService(session)
        for idx in range(count):
            model = await build_visual_learning_model(
                topic=f"Seeded Cap {idx}", description=None, components=[]
            )
            project = compose_project(topic=f"Seeded Cap {idx}", model=model)
            record = await service.create(
                user_id=TEST_USER_ID,
                video_id=project.video_id,
                topic=f"Seeded Cap {idx}",
                project_data=project.model_dump(mode="json"),
                dispatch_render=False,
            )
            record.status = VideoRenderStatus.RENDERING
            public_ids.append(record.public_id)
        await session.commit()
    return public_ids


async def test_create_list_get_ready_flow(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/video-projects",
        json={"topic": "P16 Async Rendering"},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    public_id = data["public_id"]
    assert public_id.startswith("vproj_")
    assert data["video_id"].startswith("video_")
    assert data["status"] == VideoRenderStatus.QUEUED
    assert data["progress_percentage"] == 0.0
    assert data["playable_url"] is None

    ready = await _wait_for(client, public_id, VideoRenderStatus.READY)
    assert ready["progress_percentage"] == 100.0
    assert ready["playable_url"], "ready project must have a playable URL"
    assert ready["playable_url"].endswith(f"{data['video_id']}.mp4")
    assert ready["topic"] == "P16 Async Rendering"
    assert ready["error"] is None

    listed = await client.get("/api/v1/video-projects")
    assert listed.status_code == 200
    payload = listed.json()
    assert payload["success"] is True
    public_ids = [p["public_id"] for p in payload["data"]]
    assert public_id in public_ids
    assert payload["meta"]["count"] >= 1


async def test_unknown_project_404(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/video-projects/vproj_doesnotexist")
    assert resp.status_code == 404


async def test_explicit_render_on_ready_project(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/video-projects",
        json={"topic": "Re-render me"},
    )
    assert resp.status_code == 201
    public_id = resp.json()["data"]["public_id"]
    await _wait_for(client, public_id, VideoRenderStatus.READY)

    re_render = await client.post(
        f"/api/v1/video-projects/{public_id}/render",
        json={"force": True},
    )
    assert re_render.status_code == 200, re_render.text
    assert re_render.json()["data"]["status"] == VideoRenderStatus.QUEUED

    await _wait_for(client, public_id, VideoRenderStatus.READY)


async def test_concurrency_cap_returns_409(client: AsyncClient) -> None:
    await _seed_active_projects(2)

    resp = await client.post(
        "/api/v1/video-projects",
        json={"topic": "Over the cap"},
    )
    assert resp.status_code == 409, resp.text
    body = resp.json()
    assert body["success"] is False
    assert "Too many active video renders" in body.get("error", {}).get("message", "")

    # Remove the seeded active rows so later tests are unaffected.
    async with TestSessionLocal() as session:
        await session.execute(delete(VideoProjectRecord))
        await session.commit()


async def test_validation_topic_too_long(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/video-projects",
        json={"topic": "x" * 301},
    )
    assert resp.status_code == 422


async def test_validation_too_many_components(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/video-projects",
        json={"topic": "Components", "components": [{"name": f"c{i}"} for i in range(51)]},
    )
    assert resp.status_code == 422


async def test_celery_render_task_end_to_end(client: AsyncClient) -> None:
    """The worker task renders an owned project to READY without an executor."""
    from unittest.mock import MagicMock

    from app.services.video_project_service import VideoProjectService
    from app.workers.video_tasks import video_render_task

    async with TestSessionLocal() as session:
        model = await build_visual_learning_model(
            topic="Worker round-trip", description=None, components=[]
        )
        project = compose_project(topic="Worker round-trip", model=model)
        service = VideoProjectService(session)
        record = await service.create(
            user_id=TEST_USER_ID,
            video_id=project.video_id,
            topic="Worker round-trip",
            project_data=project.model_dump(mode="json"),
            dispatch_render=False,
        )
        public_id = record.public_id
        video_id = record.video_id

    result = video_render_task.run.__func__(MagicMock(), str(TEST_USER_ID), public_id)
    assert result == public_id

    resp = await client.get(f"/api/v1/video-projects/{public_id}")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == VideoRenderStatus.READY
    assert data["progress_percentage"] == 100.0
    assert data["playable_url"] == f"/uploads/videos/{video_id}.mp4"


async def test_project_endpoints_require_auth(client: AsyncClient) -> None:
    from app.core.dependencies import get_current_user
    from app.main import app as _app

    saved = _app.dependency_overrides.pop(get_current_user, None)
    try:
        resp = await client.post("/api/v1/video-projects", json={"topic": "No auth"})
        assert resp.status_code == 401
        resp = await client.get("/api/v1/video-projects")
        assert resp.status_code == 401
        resp = await client.get("/api/v1/video-projects/vproj_x")
        assert resp.status_code == 401
    finally:
        if saved is not None:
            _app.dependency_overrides[get_current_user] = saved


async def test_legacy_create_returns_blueprint_contract(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/videos/create",
        json={"topic": "Legacy contract"},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    assert data["video_id"].startswith("video_")
    assert data["topic"] == "Legacy contract"
    assert data["validation"]["is_valid"] is True
    assert data["rendering_status"] == VideoRenderStatus.QUEUED
    assert data["playable_url"] is None
    assert data["project_public_id"].startswith("vproj_")

    vid_id = data["video_id"]
    get_resp = await client.get(f"/api/v1/videos/{vid_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["data"]["video_id"] == vid_id

    missing = await client.get("/api/v1/videos/video_missing_0000")
    assert missing.status_code == 404
