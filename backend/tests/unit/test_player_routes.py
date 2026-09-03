from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.api.v1.player as player_module
from app.database.unit_of_work import get_unit_of_work

pytestmark = pytest.mark.asyncio


def _state(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "lesson": {
            "id": "lssn_lesson",
            "presentation_id": "pres_xyz",
            "mode": "slide",
            "status": "ready",
            "title": "My Lesson",
            "language": "en",
            "difficulty": "beginner",
            "latest_version": 1,
        },
        "version": {
            "id": "lssnver_abc",
            "lesson_id": "lssn_lesson",
            "version": 1,
            "status": "succeeded",
            "title": "My Lesson",
            "summary": None,
            "language": "en",
            "difficulty": "beginner",
            "model": "fake",
            "completed_at": datetime.now(UTC),
        },
        "topics": [
            {"index": 0, "title": "Intro", "position": 0},
            {"index": 1, "title": "Body", "position": 3},
        ],
        "session": None,
    }
    data.update(overrides)
    return data


@pytest.fixture
def override_uow() -> Any:
    async def _uow_override() -> AsyncGenerator[MagicMock]:
        yield MagicMock()

    from app.main import app
    app.dependency_overrides[get_unit_of_work] = _uow_override
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def mock_service() -> MagicMock:
    service = MagicMock()
    service.get_state = AsyncMock(return_value=_state())
    service.start = AsyncMock(return_value=_state(session={
        "session_id": "sess_123",
        "lesson_id": "lssn_lesson",
        "topic_index": 0,
        "total_topics": 2,
        "status": "active",
    }))
    service.get_checkpoint = AsyncMock(return_value={
        "has_checkpoint": True,
        "quiz": {
            "id": "q_abc",
            "title": "Checkpoint",
            "description": None,
            "mode": "practice",
            "status": "ready",
            "question_count": 3,
            "passing_score": 70.0,
            "max_attempts_per_user": 3,
        },
        "completed": False,
        "latest_attempt": None,
        "available_attempts": 3,
    })
    service.get_mastery_and_next_action = AsyncMock(return_value={
        "average_mastery": 45.0,
        "mastered_count": 1,
        "developing_count": 2,
        "weak_count": 1,
        "concept_mastery": {"loops": 60.0, "list": 30.0},
        "summary": "Two concepts need review",
        "next_action": {
            "action_type": "review_concept",
            "concept_id": "list",
            "concept_name": "List",
            "title": "Review List",
            "description": "Review list operations",
            "reason": "Scored in the weak band",
            "activity_type": "video_lesson",
            "priority": "high",
        },
    })
    with patch.object(player_module, "LessonPlayerService", return_value=service):
        yield service


class TestGetPlayerStateEndpoint:
    async def test_get_state(self, client, mock_service, override_uow) -> None:
        response = await client.get("/api/v1/lessons/lssn_lesson/player")
        assert response.status_code == 200
        body = response.json()["data"]
        assert body["lesson"]["id"] == "lssn_lesson"
        assert body["version"]["version"] == 1
        assert body["topics"][0]["title"] == "Intro"
        mock_service.get_state.assert_awaited_once()


class TestStartPlayerEndpoint:
    async def test_start_creates_and_starts(
        self, client, mock_service, override_uow
    ) -> None:
        response = await client.post(
            "/api/v1/lessons/lssn_lesson/player/start",
            json={"device_id": "dev-1"},
        )
        assert response.status_code == 200
        assert response.json()["message"] == "Session started"
        assert response.json()["data"]["lesson"]["id"] == "lssn_lesson"
        mock_service.start.assert_awaited_once()

    async def test_start_passes_client_metadata(
        self, client, mock_service, override_uow
    ) -> None:
        await client.post(
            "/api/v1/lessons/lssn_lesson/player/start",
            json={"client_metadata": {"source": "homepage"}},
        )
        assert mock_service.start.await_args.kwargs["client_metadata"] == {
            "source": "homepage"
        }


class TestCheckpointEndpoint:
    async def test_get_checkpoint(
        self, client, mock_service, override_uow
    ) -> None:
        response = await client.get(
            "/api/v1/lessons/lssn_lesson/player/checkpoint"
        )
        assert response.status_code == 200
        body = response.json()["data"]
        assert body["has_checkpoint"] is True
        assert body["quiz"]["id"] == "q_abc"
        mock_service.get_checkpoint.assert_awaited_once()


class TestMasteryEndpoint:
    async def test_get_mastery_and_next_action(
        self, client, mock_service, override_uow
    ) -> None:
        response = await client.get(
            "/api/v1/lessons/lssn_lesson/player/mastery"
        )
        assert response.status_code == 200
        body = response.json()["data"]
        assert body["next_action"]["concept_name"] == "List"
        assert body["average_mastery"] == 45.0
        mock_service.get_mastery_and_next_action.assert_awaited_once()
