"""Annotation layer API endpoint tests (teaching continuity)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.api.v1.annotations as annotations_module
from app.database.unit_of_work import get_unit_of_work

pytestmark = pytest.mark.asyncio

_LESSON_ID = "lssn_annotations"
_FAKE_LESSON = MagicMock(id=uuid.uuid4(), public_id=_LESSON_ID)

_STROKE = {
    "type": "stroke",
    "tool": "pen",
    "color": "#F2A623",
    "size": 4,
    "points": [{"x": 1.0, "y": 2.0}, {"x": 3.0, "y": 4.0}],
}


@pytest.fixture
def override_uow() -> Any:
    async def _uow_override() -> AsyncGenerator[MagicMock]:
        yield MagicMock()

    from app.main import app

    app.dependency_overrides[get_unit_of_work] = _uow_override
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def mock_services() -> tuple[MagicMock, MagicMock]:
    lesson_service = MagicMock()
    lesson_service._assert_lesson_ownership = AsyncMock(return_value=_FAKE_LESSON)

    annotation_service = MagicMock()
    annotation_service.list_for_lesson = AsyncMock(return_value=[])
    annotation_service.replace = AsyncMock(
        return_value={
            "public_id": "pann_abc",
            "player_mode": "learning",
            "slide_index": 0,
            "item_count": 1,
        }
    )

    with (
        patch.object(annotations_module, "LessonPlayerService", return_value=lesson_service),
        patch.object(
            annotations_module, "PresentationAnnotationService", return_value=annotation_service
        ),
    ):
        yield lesson_service, annotation_service


class TestListAnnotations:
    async def test_returns_layers_scoped_to_lesson(
        self, client, mock_services, override_uow
    ) -> None:
        lesson_service, annotation_service = mock_services
        annotation_service.list_for_lesson = AsyncMock(
            return_value=[
                {"player_mode": "learning", "slide_index": 0, "items": [_STROKE]}
            ]
        )
        response = await client.get(f"/api/v1/lessons/{_LESSON_ID}/annotations")
        assert response.status_code == 200, response.text
        layers = response.json()["data"]["layers"]
        assert layers[0]["player_mode"] == "learning"
        assert layers[0]["slide_index"] == 0
        assert len(layers[0]["items"]) == 1

    async def test_ownership_404(self, client, mock_services, override_uow) -> None:
        lesson_service, _ = mock_services
        lesson_service._assert_lesson_ownership = AsyncMock(side_effect=PermissionError)
        response = await client.get(f"/api/v1/lessons/{_LESSON_ID}/annotations")
        assert response.status_code == 404

    async def test_missing_lesson_404(self, client, mock_services, override_uow) -> None:
        lesson_service, _ = mock_services
        lesson_service._assert_lesson_ownership = AsyncMock(
            side_effect=ValueError("Lesson not found")
        )
        response = await client.get(f"/api/v1/lessons/{_LESSON_ID}/annotations")
        assert response.status_code == 404


class TestSaveAnnotationLayer:
    async def test_put_upserts_layer(self, client, mock_services, override_uow) -> None:
        _, annotation_service = mock_services
        annotation_service.replace = AsyncMock(
            return_value={
                "public_id": "pann_abc",
                "player_mode": "learning",
                "slide_index": 3,
                "item_count": 1,
            }
        )
        response = await client.put(
            f"/api/v1/lessons/{_LESSON_ID}/annotations/learning/3",
            json={"items": [_STROKE]},
        )
        assert response.status_code == 200, response.text
        assert response.json()["message"] == "Annotation layer saved"
        saved = response.json()["data"]
        assert saved["player_mode"] == "learning"
        assert saved["slide_index"] == 3
        assert saved["item_count"] == 1
        assert annotation_service.replace.await_args.kwargs["player_mode"] == "learning"
        assert annotation_service.replace.await_args.kwargs["slide_index"] == 3

    async def test_invalid_layer_mode_is_422(self, client, mock_services, override_uow) -> None:
        response = await client.put(
            f"/api/v1/lessons/{_LESSON_ID}/annotations/critical-html/0",
            json={"items": [_STROKE]},
        )
        assert response.status_code == 422

    async def test_negative_slide_is_422(self, client, mock_services, override_uow) -> None:
        response = await client.put(
            f"/api/v1/lessons/{_LESSON_ID}/annotations/learning/-1",
            json={"items": [_STROKE]},
        )
        assert response.status_code == 422

    async def test_malformed_items_is_422(self, client, mock_services, override_uow) -> None:
        response = await client.put(
            f"/api/v1/lessons/{_LESSON_ID}/annotations/learning/0",
            json={"items": [{"type": "html", "html": "<script>"}]},
        )
        assert response.status_code == 422

    async def test_empty_items_still_saves_delete_signal(
        self, client, mock_services, override_uow
    ) -> None:
        _, annotation_service = mock_services
        annotation_service.replace = AsyncMock(
            return_value={
                "public_id": "",
                "player_mode": "learning",
                "slide_index": 0,
                "item_count": 0,
            }
        )
        response = await client.put(
            f"/api/v1/lessons/{_LESSON_ID}/annotations/learning/0",
            json={"items": []},
        )
        assert response.status_code == 200
        assert response.json()["data"]["item_count"] == 0

    async def test_unauthorized_owner_404(self, client, mock_services, override_uow) -> None:
        lesson_service, _ = mock_services
        lesson_service._assert_lesson_ownership = AsyncMock(side_effect=PermissionError)
        response = await client.put(
            f"/api/v1/lessons/{_LESSON_ID}/annotations/learning/0",
            json={"items": [_STROKE]},
        )
        assert response.status_code == 404
