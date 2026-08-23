from __future__ import annotations

import io
from abc import ABC, abstractmethod
from typing import Any


class StorageBackend(ABC):
    @abstractmethod
    async def initialize(self) -> None:
        ...

    @abstractmethod
    async def upload_fileobj(
        self,
        file_obj: io.BytesIO,
        key: str,
        content_type: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> str:
        ...

    @abstractmethod
    async def download_fileobj(self, key: str) -> bytes:
        ...

    @abstractmethod
    async def delete_object(self, key: str) -> None:
        ...

    @abstractmethod
    async def object_exists(self, key: str) -> bool:
        ...

    @abstractmethod
    async def list_objects(self, prefix: str = "") -> list[dict[str, Any]]:
        ...

    @abstractmethod
    async def generate_presigned_url(
        self,
        key: str,
        expiration: int = 3600,
        method: str = "get_object",
    ) -> str:
        ...

    @abstractmethod
    async def list_buckets(self) -> list[dict[str, str]]:
        ...

    @abstractmethod
    async def close(self) -> None:
        ...
