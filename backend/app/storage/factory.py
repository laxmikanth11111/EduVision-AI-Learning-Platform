from __future__ import annotations

from app.core.config import settings
from app.core.exceptions import ConfigurationError
from app.storage.base import StorageBackend

_storage_instance: StorageBackend | None = None


async def create_storage_backend(provider: str | None = None) -> StorageBackend:
    provider = provider or settings.STORAGE_PROVIDER

    if provider == "s3":
        from app.storage.s3_adapter import S3StorageBackend

        backend: StorageBackend = S3StorageBackend()
    elif provider == "local":
        from app.storage.local import LocalStorageBackend

        backend = LocalStorageBackend()
    else:
        raise ConfigurationError(
            message=f"Unknown storage provider: {provider}",
            details={"provider": provider, "supported": ["s3", "local"]},
        )

    await backend.initialize()
    return backend


async def get_storage_backend() -> StorageBackend:
    global _storage_instance
    if _storage_instance is None:
        _storage_instance = await create_storage_backend()
    return _storage_instance


async def close_storage_backend() -> None:
    global _storage_instance
    if _storage_instance is not None:
        await _storage_instance.close()
        _storage_instance = None
