"""API Router for Phase 4K.3 + 4K.4 Interactive Video Runtime Synchronization.
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel

from app.core.dependencies import get_current_user
from app.core.logging import get_logger
from app.models.user import User
from app.services.educational_memory_service import educational_memory_service
from app.services.learning_context_service import learning_context_service

logger = get_logger(__name__)

video_runtime_router = APIRouter(
    prefix="/videos/runtime", tags=["Interactive Educational Video Runtime Engine"]
)

_VIDEO_RUNTIME_STATES: dict[str, Any] = {}
_VIDEO_BOOKMARKS: dict[str, list[dict[str, Any]]] = {}
_VIDEO_ASSESSMENTS: dict[str, list[dict[str, Any]]] = {}


class SyncVideoRuntimeRequest(BaseModel):
    session_id: str
    video_id: str
    scene_index: int
    current_timestamp_ms: float
    component_id: str | None = None


class BookmarkRequest(BaseModel):
    session_id: str
    video_id: str
    time_ms: float
    title: str = "Saved Bookmark"


class AssessmentSubmitRequest(BaseModel):
    session_id: str
    video_id: str
    scene_index: int
    selected_option: str


@video_runtime_router.post(
    "/sync",
    status_code=status.HTTP_200_OK,
    summary="Synchronize live interactive video playback step with Learning Context & Memory",
)
async def sync_video_runtime(
    req: SyncVideoRuntimeRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    now = time.time()
    _VIDEO_RUNTIME_STATES[req.session_id] = {
        "video_id": req.video_id,
        "scene_index": req.scene_index,
        "current_timestamp_ms": req.current_timestamp_ms,
        "component_id": req.component_id,
        "user_id": str(user.id),
        "last_sync_timestamp": now,
    }

    # Publish event to LearningContext (best-effort; session may not exist)
    try:
        learning_context_service.publish_event(
            session_id=req.session_id,
            event_type="video_scene_viewed",
            step_name=f"Video Scene {req.scene_index + 1}",
            component_id=req.component_id,
            details={"video_id": req.video_id, "timestamp_ms": req.current_timestamp_ms},
        )
    except Exception as exc:
        logger.debug("video_runtime_publish_event_failed", session_id=req.session_id, error=str(exc))

    # Log milestone in EducationalMemory and persist to DB (best-effort)
    try:
        educational_memory_service.add_milestone(
            user_id=str(user.id),
            title=f"Watched Video Scene {req.scene_index + 1}",
            category="video_viewed",
            details={"video_id": req.video_id},
        )
        from app.database.session import async_session_factory
        async with async_session_factory() as _session:
            await educational_memory_service.save_to_db(_session, str(user.id))
            await _session.commit()
    except Exception as exc:
        logger.debug("video_runtime_add_milestone_failed", user_id=str(user.id), error=str(exc))

    return {"success": True, "data": _VIDEO_RUNTIME_STATES[req.session_id]}


@video_runtime_router.get(
    "/state/{session_id}",
    summary="Retrieve current active video runtime state by session ID",
)
async def get_video_runtime_state(
    session_id: str,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    state = _VIDEO_RUNTIME_STATES.get(session_id)
    if not state or state.get("user_id") != str(user.id):
        return {"success": True, "data": None}
    return {"success": True, "data": state}


@video_runtime_router.post(
    "/bookmark",
    status_code=status.HTTP_201_CREATED,
    summary="Save a video timestamp bookmark for active session",
)
async def create_video_bookmark(
    req: BookmarkRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    bm = {
        "bookmark_id": f"bm_{int(time.time() * 1000)}",
        "video_id": req.video_id,
        "time_ms": req.time_ms,
        "title": req.title,
        "user_id": str(user.id),
        "created_at": time.time(),
    }
    if req.session_id not in _VIDEO_BOOKMARKS:
        _VIDEO_BOOKMARKS[req.session_id] = []
    _VIDEO_BOOKMARKS[req.session_id].append(bm)
    return {"success": True, "data": bm}


@video_runtime_router.post(
    "/assessment",
    status_code=status.HTTP_200_OK,
    summary="Record interactive in-video assessment checkpoint response",
)
async def submit_video_assessment(
    req: AssessmentSubmitRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    attempt = {
        "session_id": req.session_id,
        "video_id": req.video_id,
        "scene_index": req.scene_index,
        "selected_option": req.selected_option,
        "is_correct": "Decode" in req.selected_option,
        "user_id": str(user.id),
        "submitted_at": time.time(),
    }
    if req.session_id not in _VIDEO_ASSESSMENTS:
        _VIDEO_ASSESSMENTS[req.session_id] = []
    _VIDEO_ASSESSMENTS[req.session_id].append(attempt)

    return {"success": True, "data": attempt}


@video_runtime_router.get(
    "/tutor-context/{session_id}",
    summary="Retrieve AI Tutor context snapshot for active video scene",
)
async def get_video_tutor_context(
    session_id: str,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    state = _VIDEO_RUNTIME_STATES.get(session_id)
    if not state or state.get("user_id") != str(user.id):
        return {"success": True, "data": None}
    return {
        "success": True,
        "data": {
            "session_id": session_id,
            "active_video_id": state["video_id"],
            "scene_index": state["scene_index"],
            "component_id": state.get("component_id", "comp_fetch"),
            "prompt_suggestion": f"Explain step {state['scene_index'] + 1} of this video lesson",
        },
    }
