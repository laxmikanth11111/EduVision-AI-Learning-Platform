"""API Router for Phase 4J.3 + 4J.4 Interactive Animation Runtime Synchronization.
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel

from app.core.dependencies import get_current_user
from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.models.user import User
from app.services.educational_memory_service import educational_memory_service
from app.services.learning_context_service import learning_context_service
from app.utils.bounded_cache import BoundedCache

logger = get_logger(__name__)

animation_runtime_router = APIRouter(
    prefix="/animations/runtime", tags=["Interactive Animation Runtime Engine"]
)

# Bounded in-process state: evicts the least-recently-written session once it
# exceeds the cap so long-running servers never accumulate state without limit.
_RUNTIME_STATES: BoundedCache[str, dict[str, Any]] = BoundedCache(max_size=4096)


def _assert_session_owned(
    session_id: str,
    existing: dict[str, Any] | None,
    user_id: str,
) -> None:
    """404-equalized ownership check for an animation runtime-session slot.

    If no state exists yet the caller may create it (first-write preserved);
    if it exists it must belong to ``user_id``. A foreign session surfaces as
    a uniform ``NotFoundError`` so no ownership/existence detail is leaked.
    """
    if existing is None:
        return
    if existing.get("user_id") != user_id:
        raise NotFoundError(
            message="Runtime session not found",
            details={"session_id": session_id},
        )


class SyncRuntimeRequest(BaseModel):
    session_id: str
    blueprint_id: str
    scene_index: int
    event_id: str | None = None
    component_id: str | None = None


@animation_runtime_router.post(
    "/sync",
    status_code=status.HTTP_200_OK,
    summary="Synchronize live interactive animation playback step with Learning Context & Memory",
)
async def sync_animation_runtime(
    req: SyncRuntimeRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    now = time.time()
    _assert_session_owned(
        req.session_id,
        _RUNTIME_STATES.get(req.session_id),
        str(user.id),
    )
    _RUNTIME_STATES.set(req.session_id, {
        "blueprint_id": req.blueprint_id,
        "scene_index": req.scene_index,
        "event_id": req.event_id,
        "component_id": req.component_id,
        "user_id": str(user.id),
        "last_sync_timestamp": now,
    })

    # Log into LearningContext Timeline (best-effort; session may not exist)
    try:
        learning_context_service.publish_event(
            session_id=req.session_id,
            event_type="animation_step_viewed",
            step_name=f"Animation Scene {req.scene_index + 1}",
            component_id=req.component_id,
            details={"blueprint_id": req.blueprint_id, "scene_index": req.scene_index},
        )
    except Exception as exc:
        logger.debug("animation_runtime_publish_event_failed", session_id=req.session_id, error=str(exc))

    # Log milestone into EducationalMemory and persist to DB (best-effort)
    try:
        educational_memory_service.add_milestone(
            user_id=str(user.id),
            title=f"Viewed Animation Scene {req.scene_index + 1}",
            category="animation_viewed",
            details={"blueprint_id": req.blueprint_id},
        )
        from app.database.session import async_session_factory
        async with async_session_factory() as _session:
            await educational_memory_service.save_to_db(_session, str(user.id))
            await _session.commit()
    except Exception as exc:
        logger.debug("animation_runtime_add_milestone_failed", user_id=str(user.id), error=str(exc))

    return {"success": True, "data": _RUNTIME_STATES.get(req.session_id)}


@animation_runtime_router.get(
    "/state/{session_id}",
    summary="Retrieve current active animation runtime state by session ID",
)
async def get_animation_runtime_state(
    session_id: str,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    state = _RUNTIME_STATES.get(session_id)
    if not state or state.get("user_id") != str(user.id):
        return {"success": True, "data": None}
    return {"success": True, "data": state}
