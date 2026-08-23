"""Integration tests for presentation topics — auth removed."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.database.unit_of_work import UnitOfWork
from app.main import app
from app.services.content_extraction_service import ContentExtractionService

pytestmark = pytest.mark.integration

SOURCE_CONTENT = b"Introduction\n\nMain body paragraph.\n\nConcluding remarks."

OUTLINE_JSON = (
    '{"title": "Unit Overview", "topics": ['
    '{"title": "Intro", "slide_ranges": [1, 1]}]}'
)


@pytest.fixture
def mock_storage() -> MagicMock:
    storage = MagicMock()
    storage.upload_fileobj = AsyncMock(return_value="sources/mock-key")
    storage.download_fileobj = AsyncMock(return_value=SOURCE_CONTENT)
    return storage


@pytest.fixture(autouse=True)
def override_storage_backend(mock_storage: MagicMock):
    with patch(
        "app.services.presentation_service.get_storage_backend",
        AsyncMock(return_value=mock_storage),
    ), patch(
        "app.services.content_extraction_service.get_storage_backend",
        AsyncMock(return_value=mock_storage),
    ):
        yield


@pytest.fixture(autouse=True)
def override_ai_service():
    class FakeAI:
        async def generate(self, request):
            return MagicMock(
                text=OUTLINE_JSON,
                provider="fake",
                model="fake-model",
                request_id="ai_req_1",
                correlation_id="corr_1",
            )

    with patch(
        "app.services.topic_outline_service.AIContentService",
        lambda uow=None: FakeAI(),
    ):
        yield


async def _create_presentation(client: AsyncClient, title: str) -> str:
    response = await client.post(
        "/api/v1/presentations",
        json={"title": title},
    )
    assert response.status_code == 201
    return response.json()["data"]["id"]


async def _create_extracted_presentation(client: AsyncClient, title: str) -> str:
    presentation_id = await _create_presentation(client, title)
    upload_response = await client.post(
        f"/api/v1/presentations/{presentation_id}/source",
        files={"source": ("notes.txt", SOURCE_CONTENT, "text/plain")},
    )
    assert upload_response.status_code == 200
    async with UnitOfWork() as uow:
        await ContentExtractionService(uow).extract_presentation(presentation_id)
    return presentation_id


class TestPresentationTopicsApi:
    async def test_get_topics_returns_none_before_generation(
        self, client: AsyncClient
    ) -> None:
        presentation_id = await _create_extracted_presentation(client, "Topics Empty")

        response = await client.get(
            f"/api/v1/presentations/{presentation_id}/topics",
        )
        assert response.status_code == 200
        body = response.json()["data"]
        assert body["status"] == "none"
        assert body["topics"] == []
        assert body["title"] is None

    async def test_regenerate_generates_and_persists_outline(
        self, client: AsyncClient
    ) -> None:
        presentation_id = await _create_extracted_presentation(client, "Topics Gen")

        response = await client.post(
            f"/api/v1/presentations/{presentation_id}/topics/regenerate",
        )
        assert response.status_code == 200
        body = response.json()["data"]
        assert body["status"] == "succeeded"
        assert body["title"] == "Unit Overview"
        assert len(body["topics"]) == 1
        assert body["topics"][0]["title"] == "Intro"
        assert body["topics"][0]["slide_ranges"] == [1, 1]
        assert body["provider"] == "fake"

        fetch_response = await client.get(
            f"/api/v1/presentations/{presentation_id}/topics",
        )
        assert fetch_response.status_code == 200
        fetch_body = fetch_response.json()["data"]
        assert fetch_body["status"] == "succeeded"
        assert len(fetch_body["topics"]) == 1
