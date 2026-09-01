"""WS5 — public `/uploads` mount determination tests.

`/uploads` intentionally serves only server-generated, playable media
(TTS audio and rendered videos). Private objects live in the storage layer
(``storage-data`` locally, the private S3 bucket in production) and must never
be reachable through the public mount.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from httpx import AsyncClient
from starlette.routing import Mount
from starlette.staticfiles import StaticFiles


def _uploads_mount(app) -> Mount:
    mounts = [r for r in app.routes if isinstance(r, Mount) and r.path == "/uploads"]
    assert len(mounts) == 1, "exactly one /uploads mount must exist"
    return mounts[0]


def _uploads_static(app) -> StaticFiles:
    mount = _uploads_mount(app)
    assert isinstance(mount.app, StaticFiles)
    return mount.app


def test_uploads_mount_points_at_generated_media_dir() -> None:
    from app.core.config import settings
    from app.main import app

    static = _uploads_static(app)
    assert str(Path(static.directory).resolve()) == str(settings.upload_path.resolve())


@pytest.mark.asyncio
async def test_uploads_serves_generated_media(client: AsyncClient) -> None:
    from app.core.config import settings
    from app.main import app

    static = _uploads_static(app)
    render_dir = static.directory / "videos"
    render_dir.mkdir(parents=True, exist_ok=True)

    filename = f"render-{uuid.uuid4().hex}.mp4"
    file_path = render_dir / filename
    file_path.write_bytes(b"\x00\x00\x00\x18ftypmp42")

    try:
        resp = await client.get(f"/uploads/videos/{filename}")
        assert resp.status_code == 200
        assert resp.content == b"\x00\x00\x00\x18ftypmp42"
        assert (resp.headers.get("content-type") or "").startswith("video/mp4")
    finally:
        file_path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_uploads_does_not_serve_storage_objects(client: AsyncClient) -> None:
    from app.main import app

    static = _uploads_static(app)
    private_path = static.directory.parent / "storage-data" / "eduvision"
    private_path.mkdir(parents=True, exist_ok=True)
    secret = private_path / "private-notes.pdf"
    secret.write_bytes(b"%PDF-1.4 private")

    try:
        resp = await client.get(f"/uploads/eduvision/{secret.name}")
        assert resp.status_code == 404

        resp2 = await client.get(f"/uploads/../storage-data/eduvision/{secret.name}")
        assert resp2.status_code == 404
    finally:
        secret.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_uploads_requires_explicit_directory(client: AsyncClient) -> None:
    resp = await client.get("/uploads/")
    assert resp.status_code in (404, 403)
