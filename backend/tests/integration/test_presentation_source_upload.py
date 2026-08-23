"""Integration tests for presentation source upload — auth removed."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

pytestmark = pytest.mark.integration


@pytest.fixture
def mock_storage() -> MagicMock:
    storage = MagicMock()
    storage.upload_fileobj = AsyncMock(return_value="sources/mock-key")
    return storage


@pytest.fixture(autouse=True)
def override_storage_backend(mock_storage: MagicMock):
    with patch(
        "app.services.presentation_service.get_storage_backend",
        AsyncMock(return_value=mock_storage),
    ):
        yield


async def _create_presentation(client: AsyncClient) -> str:
    response = await client.post(
        "/api/v1/presentations",
        json={"title": "Upload Test Presentation"},
    )
    assert response.status_code == 201
    return response.json()["data"]["id"]


class TestPresentationSourceUpload:
    async def test_upload_source_succeeds(self, client: AsyncClient, mock_storage: MagicMock) -> None:
        presentation_id = await _create_presentation(client)

        response = await client.post(
            f"/api/v1/presentations/{presentation_id}/source",
            files={"source": ("slides.pdf", b"%PDF-1.4 content", "application/pdf")},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"]["id"] == presentation_id
        assert body["data"]["file_name"] == "slides.pdf"
        assert body["data"]["mime_type"] == "application/pdf"
        assert body["data"]["file_size"] == len(b"%PDF-1.4 content")
        assert body["data"]["file_key"].startswith(f"sources/{presentation_id}/")
        assert body["data"]["source_status"] == "uploaded"
        mock_storage.upload_fileobj.assert_awaited_once()

    async def test_missing_file_returns_422(self, client: AsyncClient) -> None:
        presentation_id = await _create_presentation(client)

        response = await client.post(
            f"/api/v1/presentations/{presentation_id}/source",
        )

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    async def test_empty_file_returns_409(self, client: AsyncClient) -> None:
        presentation_id = await _create_presentation(client)

        response = await client.post(
            f"/api/v1/presentations/{presentation_id}/source",
            files={"source": ("slides.pdf", b"", "application/pdf")},
        )

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "CONFLICT"

    async def test_unsupported_extension_returns_422(self, client: AsyncClient) -> None:
        presentation_id = await _create_presentation(client)

        response = await client.post(
            f"/api/v1/presentations/{presentation_id}/source",
            files={"source": ("slides.png", b"binary-data", "image/png")},
        )

        assert response.status_code == 422
        body = response.json()
        assert body["error"]["code"] == "VALIDATION_ERROR"
        assert "Unsupported source file extension" in body["error"]["message"]

    async def test_oversized_file_returns_422(self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "app.services.presentation_service.settings.UPLOAD_MAX_FILE_SIZE",
            10,
        )
        presentation_id = await _create_presentation(client)

        response = await client.post(
            f"/api/v1/presentations/{presentation_id}/source",
            files={"source": ("slides.pdf", b"0123456789A", "application/pdf")},
        )

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    async def test_invalid_content_type_still_allows_upload(self, client: AsyncClient, mock_storage: MagicMock) -> None:
        presentation_id = await _create_presentation(client)

        response = await client.post(
            f"/api/v1/presentations/{presentation_id}/source",
            files={"source": ("slides.pdf", b"pdf-data", "application/invalid")},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["data"]["mime_type"] == "application/invalid"

    async def test_nonexistent_presentation_returns_404(self, client: AsyncClient) -> None:
        fake_id = str(uuid.uuid4())
        response = await client.post(
            f"/api/v1/presentations/{fake_id}/source",
            files={"source": ("slides.pdf", b"pdf-data", "application/pdf")},
        )

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"
