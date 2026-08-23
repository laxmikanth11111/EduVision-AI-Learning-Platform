"""Integration tests for presentation extraction — auth removed."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.database.unit_of_work import UnitOfWork
from app.main import app
from app.services.content_extraction_service import ContentExtractionService

pytestmark = pytest.mark.integration

SOURCE_CONTENT = b"Introduction\n\nMain body paragraph.\n\nConcluding remarks."


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


async def _create_presentation(client: AsyncClient, title: str) -> str:
    response = await client.post(
        "/api/v1/presentations",
        json={"title": title},
    )
    assert response.status_code == 201
    return response.json()["data"]["id"]


class TestPresentationExtraction:
    async def test_full_extraction_flow(self, client: AsyncClient) -> None:
        presentation_id = await _create_presentation(client, "Extraction Test")

        upload_response = await client.post(
            f"/api/v1/presentations/{presentation_id}/source",
            files={"source": ("notes.txt", SOURCE_CONTENT, "text/plain")},
        )
        assert upload_response.status_code == 200

        async with UnitOfWork() as uow:
            await ContentExtractionService(uow).extract_presentation(presentation_id)

        status_response = await client.get(
            f"/api/v1/presentations/{presentation_id}/processing-status",
        )
        assert status_response.status_code == 200
        status_body = status_response.json()["data"]
        assert status_body["extraction_status"] == "ready"
        assert status_body["units_count"] == 1

        content_response = await client.get(
            f"/api/v1/presentations/{presentation_id}/content",
        )
        assert content_response.status_code == 200
        content_body = content_response.json()["data"]
        assert content_body["extraction_status"] == "ready"
        units = content_body["units"]
        assert len(units) == 1
        assert units[0]["unit_type"] == "document"
        assert len(units[0]["blocks"]) == 3

        detail_response = await client.get(
            f"/api/v1/presentations/{presentation_id}",
        )
        assert detail_response.status_code == 200
        assert detail_response.json()["data"]["extraction_status"] == "ready"

    async def test_processing_status_without_source(self, client: AsyncClient) -> None:
        presentation_id = await _create_presentation(client, "No Source")

        response = await client.get(
            f"/api/v1/presentations/{presentation_id}/processing-status",
        )
        assert response.status_code == 200
        body = response.json()["data"]
        assert body["extraction_status"] == "none"
        assert body["units_count"] == 0
