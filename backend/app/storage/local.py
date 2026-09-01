from __future__ import annotations

import io
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

from app.core.config import settings
from app.core.exceptions import StorageError
from app.core.logging import get_logger
from app.storage.base import StorageBackend

logger = get_logger(__name__)


class LocalStorageBackend(StorageBackend):
    def __init__(self) -> None:
        self._base_path: Path = Path(settings.LOCAL_STORAGE_PATH)
        self._initialized = False

    async def initialize(self) -> None:
        if self._initialized:
            return
        self._base_path.mkdir(parents=True, exist_ok=True)
        (self._base_path / settings.S3_BUCKET_NAME).mkdir(parents=True, exist_ok=True)
        (self._base_path / settings.S3_PUBLIC_BUCKET_NAME).mkdir(parents=True, exist_ok=True)
        self._initialized = True
        logger.info("local_storage_initialized", path=str(self._base_path))

    def _resolve_path(self, key: str, bucket: str | None = None) -> Path:
        bucket_name = bucket or settings.S3_BUCKET_NAME
        full_path = (self._base_path / bucket_name / key).resolve()
        if not full_path.is_relative_to(self._base_path.resolve()):
            raise StorageError(message="Invalid storage key: path traversal detected")
        full_path.parent.mkdir(parents=True, exist_ok=True)
        return full_path

    async def upload_fileobj(
        self,
        file_obj: io.BytesIO,
        key: str,
        content_type: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> str:
        file_path = self._resolve_path(key)
        file_path.write_bytes(file_obj.getvalue())
        logger.info("local_upload_completed", path=str(file_path))
        return key

    async def download_fileobj(self, key: str) -> bytes:
        file_path = self._resolve_path(key)
        if not file_path.exists():
            raise StorageError(message=f"File not found: {key}")
        return file_path.read_bytes()

    async def delete_object(self, key: str) -> None:
        file_path = self._resolve_path(key)
        if file_path.exists():
            file_path.unlink()
            logger.info("local_delete_completed", path=str(file_path))

    async def object_exists(self, key: str) -> bool:
        file_path = self._resolve_path(key)
        return file_path.exists()

    async def list_objects(self, prefix: str = "") -> list[dict[str, Any]]:
        bucket_path = self._base_path / settings.S3_BUCKET_NAME
        search_path = bucket_path / prefix if prefix else bucket_path
        if not search_path.exists():
            return []
        results: list[dict[str, Any]] = []
        for file_path in search_path.rglob("*"):
            if file_path.is_file():
                rel_path = file_path.relative_to(bucket_path)
                stat = file_path.stat()
                results.append(
                    {
                        "key": str(rel_path.as_posix()),
                        "size": stat.st_size,
                        "last_modified": datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat(),
                        "etag": str(uuid.uuid4()),
                    }
                )
        return results

    async def generate_presigned_url(
        self,
        key: str,
        expiration: int = 3600,
        method: str = "get_object",
    ) -> str:
        """Return an app-relative, authenticated download URL for the object.

        Local storage must never expose absolute filesystem paths (file:// URIs).
        Objects are streamed through an authenticated API endpoint instead; the
        ``expiration``/``method`` parameters mirror the S3 adapter's signature.
        """
        path = self._resolve_path(key)
        if not path.exists():
            raise StorageError(message=f"File not found: {key}")
        return f"/api/v1/storage/content/{quote(key, safe='/')}"

    async def list_buckets(self) -> list[dict[str, str]]:
        if not self._base_path.exists():
            return []
        return [
            {"name": d.name, "creation_date": "local"}
            for d in self._base_path.iterdir()
            if d.is_dir()
        ]

    async def close(self) -> None:
        self._initialized = False
        logger.info("local_storage_closed")
