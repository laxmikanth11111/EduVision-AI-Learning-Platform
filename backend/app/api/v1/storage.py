"""Storage API router — authenticated, scoped object downloads.

Exposes an authenticated streaming endpoint so local (filesystem) storage can
hand out real download URLs instead of absolute ``file://`` paths. Access is
scoped to the current user's own export namespace.
"""

from __future__ import annotations

import mimetypes

from fastapi import APIRouter, Depends, Response

from app.core.dependencies import get_current_user
from app.core.exceptions import NotFoundError, StorageError
from app.models.user import User
from app.storage.base import StorageBackend
from app.storage.factory import get_storage_backend

storage_router = APIRouter(prefix="/storage", tags=["Storage"])


@storage_router.get(
    "/content/{key:path}",
    summary="Download a scoped storage object",
    response_class=Response,
)
async def get_storage_content(
    key: str,
    user: User = Depends(get_current_user),
    storage: StorageBackend = Depends(get_storage_backend),
) -> Response:
    """Stream an object owned by the current user.

    Only keys under the caller's own export namespace
    (``exports/user_<user-id-hex>/...``) are served; anything else is masked as
    a 404 so storage keys cannot be probed across users.
    """
    expected_prefix = f"exports/user_{user.id.hex}/"
    if not key.startswith(expected_prefix):
        raise NotFoundError("Object not found")

    try:
        data = await storage.download_fileobj(key)
    except StorageError as exc:
        raise NotFoundError("Object not found") from exc

    media_type = mimetypes.guess_type(key)[0] or "application/octet-stream"
    return Response(content=data, media_type=media_type)
