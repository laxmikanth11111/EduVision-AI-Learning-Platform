"""WS4 — storage path-security tests.

Local storage must never expose absolute filesystem paths (``file://`` URIs).
Download URLs must be app-relative and streamed through an authenticated,
ownership-scoped endpoint.
"""

from __future__ import annotations

import io

import httpx
import pytest
import pytest_asyncio
from httpx import AsyncClient

from tests.conftest import TEST_USER_ID


@pytest_asyncio.fixture
async def local_storage():
    from app.storage.local import LocalStorageBackend

    backend = LocalStorageBackend()
    await backend.initialize()
    yield backend
    await backend.close()


class TestLocalPresignedUrl:
    async def test_returns_app_relative_url_not_file_uri(
        self, local_storage
    ) -> None:
        key = f"exports/user_{TEST_USER_ID.hex}/job123/report.pdf"
        await local_storage.upload_fileobj(io.BytesIO(b"%PDF-1.4 test"), key)

        url = await local_storage.generate_presigned_url(key)

        assert url == f"/api/v1/storage/content/{key}"
        assert "file://" not in url
        assert str(local_storage._base_path) not in url

    async def test_missing_key_raises_storage_error(self, local_storage) -> None:
        from app.core.exceptions import StorageError

        with pytest.raises(StorageError):
            await local_storage.generate_presigned_url(
                "exports/user_deadbeef/job1/missing.pdf"
            )

    async def test_url_encodes_reserved_characters(self, local_storage) -> None:
        key = "exports/user_abc/job1/lesson notes 101.pptx"
        await local_storage.upload_fileobj(io.BytesIO(b"PK\x03\x04" + b"\x00" * 8), key)

        url = await local_storage.generate_presigned_url(key)

        assert url.startswith("/api/v1/storage/content/exports/user_abc/job1/")
        assert " " not in url


class TestStorageContentEndpoint:
    OWN_KEY = f"exports/user_{TEST_USER_ID.hex}/job1/report.pdf"

    async def test_streams_own_object(self, client: AsyncClient) -> None:
        resp = await client.get(f"/api/v1/storage/content/{self.OWN_KEY}")

        assert resp.status_code == 200
        assert resp.content == b"test-data"  # conftest mock_storage payload
        assert "application/pdf" in resp.headers["content-type"]

    async def test_denies_other_users_namespace(self, client: AsyncClient) -> None:
        other_key = "exports/user_ffffffffffffffffffffffffffffffff/job1/report.pdf"
        resp = await client.get(f"/api/v1/storage/content/{other_key}")

        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "NOT_FOUND"

    async def test_denies_non_export_keys(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/storage/content/sources/pres1/slides.pdf")

        assert resp.status_code == 404

    async def test_denies_traversal_key(self, client: AsyncClient) -> None:
        resp = await client.get(
            f"/api/v1/storage/content/exports/user_{TEST_USER_ID.hex}/../../secret"
        )

        assert resp.status_code == 404

    async def test_requires_authentication(self) -> None:
        from app.core.dependencies import get_current_user
        from app.main import app

        app.dependency_overrides.pop(get_current_user, None)
        try:
            transport = httpx.ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as anon:
                resp = await anon.get(f"/api/v1/storage/content/{self.OWN_KEY}")
                assert resp.status_code == 401
        finally:
            from tests.conftest import _FakeUser as _Fake

            async def _fake_user_jwtless():
                return _Fake()

            app.dependency_overrides[get_current_user] = _fake_user_jwtless

    async def test_masks_storage_error_as_404(self, client: AsyncClient) -> None:
        from app.core.exceptions import StorageError
        from app.main import app
        from app.storage.factory import get_storage_backend

        class _FailingBackend:
            async def download_fileobj(self, key: str) -> bytes:
                raise StorageError("boom")

        async def _failing_storage():
            return _FailingBackend()

        app.dependency_overrides[get_storage_backend] = _failing_storage
        try:
            resp = await client.get(f"/api/v1/storage/content/{self.OWN_KEY}")
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.pop(get_storage_backend, None)
