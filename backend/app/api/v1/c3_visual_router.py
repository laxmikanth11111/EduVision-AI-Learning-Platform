"""C3 API Router — endpoints for topic-level visual intelligence.

Provides endpoints for visual generation, retrieval, download,
and management scoped to user ownership.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from pydantic import BaseModel

from app.core.dependencies import get_current_user
from app.core.exceptions import NotFoundError
from app.database.unit_of_work import UnitOfWork, get_unit_of_work
from app.models.user import User
from app.repositories.topic_visual_asset_repository import TopicVisualAssetRepository
from app.schemas.c3_visual_intelligence import (
    VisualGenerationRequest,
)

c3_visual_router = APIRouter(prefix="/c3/visuals", tags=["C3 Visual Intelligence"])


class C3VisualAssetResponse(BaseModel):
    id: str
    public_id: str
    visual_type: str
    title: str
    status: str
    asset_format: str
    asset_url: str | None = None
    topic_id: str
    topic_title: str
    subtopic_id: str | None = None
    subtopic_title: str | None = None
    provenance: str
    confidence: float
    version: int
    explanation: dict[str, Any] | None = None
    source_references: list[dict[str, Any]] = []
    concept_ids: list[str] = []
    created_at: str | None = None


async def _assert_ownership(
    asset_id: uuid.UUID,
    user: User,
    repo: TopicVisualAssetRepository,
) -> Any:
    """Raise 404 if asset doesn't exist or isn't owned by user."""
    asset = await repo.get_by_id_and_user(asset_id, user.id)
    if not asset:
        raise NotFoundError(
            message="Visual asset not found",
            details={"asset_id": str(asset_id)},
        )
    return asset


async def _resolve_presentation(
    presentation_id: str,
    user: User,
    uow: UnitOfWork,
) -> uuid.UUID:
    """Resolve a presentation public_id to its DB id, verifying ownership."""
    from app.repositories.presentation_repository import PresentationRepository

    pres_repo = PresentationRepository(uow.session)
    presentation = await pres_repo.get_by_public_id(presentation_id)
    if not presentation or str(presentation.owner_id) != str(user.id):
        raise NotFoundError(
            message="Presentation not found",
            details={"presentation_id": presentation_id},
        )
    return presentation.id


async def _validate_topic_hint(
    uow: UnitOfWork,
    presentation_db_id: uuid.UUID,
    topic_id: str | None,
    subtopic_id: str | None,
) -> None:
    """Validate the topic/subtopic title hint against the C2 outline, if one exists.

    The contract: ``topic_id``/``subtopic_id`` are outline titles (used purely as
    resume hints). If an outline exists and an explicit hint is supplied for a
    title that is not present, reject it — otherwise a client could silently
    reference a topic that never generated a visual.
    """
    if not topic_id:
        return

    from app.repositories.topic_outline_repository import TopicOutlineRepository

    repo = TopicOutlineRepository(uow.session)
    outline = await repo.get_by_presentation_id(presentation_db_id)
    if outline is None:
        return  # no outline yet — nothing to validate against

    topics = outline.topics or []
    titles = [
        str(t.get("title", "")) if isinstance(t, dict) else str(getattr(t, "title", ""))
        for t in topics
    ]
    if topic_id not in titles:
        raise HTTPException(
            status_code=422,
            detail=(
                f"topic_id '{topic_id}' is not a topic title in this presentation's "
                "outline; expected one of the outline titles (contract: topic_id is "
                "a title, not a UUID)"
            ),
            headers={"X-C3-Contract": "topic_id-is-outline-title"},
        )

    if subtopic_id:
        subtitles = []
        for t in topics:
            sub = t.get("subtopics") if isinstance(t, dict) else getattr(t, "subtopics", [])
            if not isinstance(sub, list):
                continue
            for s in sub:
                if isinstance(s, dict):
                    subtitles.append(str(s.get("title", "")))
                else:
                    subtitles.append(str(getattr(s, "title", "")))
        if subtopic_id not in subtitles:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"subtopic_id '{subtopic_id}' is not a subtopic title in this "
                    "presentation's outline"
                ),
            )


@c3_visual_router.get(
    "/presentation/{presentation_id}",
    summary="List all C3 visuals for a presentation",
)
async def list_presentation_visuals(
    presentation_id: str,
    user: User = Depends(get_current_user),
    status_filter: str | None = Query(default=None, alias="status"),
    topic_id: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> dict[str, Any]:
    repo = TopicVisualAssetRepository(uow.session)
    pres_uuid = await _resolve_presentation(presentation_id, user, uow)

    assets, total = await repo.list_by_presentation(
        pres_uuid,
        status=status_filter,
        topic_id=topic_id,
        page=page,
        page_size=page_size,
    )

    return {
        "success": True,
        "data": [_serialize_asset(a) for a in assets],
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
        },
    }


@c3_visual_router.get(
    "/presentation/{presentation_id}/topic/{topic_id}",
    summary="Get visuals for a specific topic",
)
async def get_topic_visuals(
    presentation_id: str,
    topic_id: str,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> dict[str, Any]:
    repo = TopicVisualAssetRepository(uow.session)
    pres_uuid = await _resolve_presentation(presentation_id, user, uow)

    assets = await repo.list_by_topic(pres_uuid, topic_id)

    return {
        "success": True,
        "data": [_serialize_asset(a) for a in assets],
    }


@c3_visual_router.get(
    "/{asset_id}",
    summary="Get a single C3 visual asset",
)
async def get_visual_asset(
    asset_id: uuid.UUID,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> dict[str, Any]:
    repo = TopicVisualAssetRepository(uow.session)
    asset = await _assert_ownership(asset_id, user, repo)
    return {"success": True, "data": _serialize_asset(asset)}


@c3_visual_router.get(
    "/{asset_id}/svg",
    summary="Get the SVG content of a visual asset",
)
async def get_visual_svg(
    asset_id: uuid.UUID,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> Response:
    repo = TopicVisualAssetRepository(uow.session)
    asset = await _assert_ownership(asset_id, user, repo)

    if not asset.asset_content:
        raise NotFoundError(
            message="Visual content not available",
            details={"asset_id": str(asset_id)},
        )

    return Response(
        content=asset.asset_content,
        media_type="image/svg+xml",
        headers={
            "Content-Disposition": f'inline; filename="{asset.title}.svg"',
            "Cache-Control": "public, max-age=3600",
        },
    )


@c3_visual_router.get(
    "/{asset_id}/download",
    summary="Download a visual asset",
)
async def download_visual(
    asset_id: uuid.UUID,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> Response:
    repo = TopicVisualAssetRepository(uow.session)
    asset = await _assert_ownership(asset_id, user, repo)

    if asset.status != "ready" or not asset.asset_content:
        raise NotFoundError(
            message="Visual asset is not ready for download",
            details={"asset_id": str(asset_id), "status": asset.status},
        )

    safe_title = "".join(c if c.isalnum() or c in " -_" else "" for c in asset.title)
    safe_title = safe_title.strip().replace(" ", "_")[:50]

    return Response(
        content=asset.asset_content,
        media_type="image/svg+xml",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_title}.svg"',
        },
    )


@c3_visual_router.post(
    "/generate",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger async visual generation for a presentation",
)
async def trigger_visual_generation(
    req: VisualGenerationRequest,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> dict[str, Any]:
    # Verify presentation ownership
    from app.repositories.presentation_repository import PresentationRepository

    pres_repo = PresentationRepository(uow.session)
    presentation = await pres_repo.get_by_public_id(req.presentation_id)
    if not presentation or str(presentation.owner_id) != str(user.id):
        raise NotFoundError(
            message="Presentation not found",
            details={"presentation_id": req.presentation_id},
        )

    await _validate_topic_hint(uow, presentation.id, req.topic_id, req.subtopic_id)

    # Dispatch Celery task
    from app.workers.c3_visual_tasks import c3_generate_visuals_task
    from app.workers.tasks import safe_dispatch

    safe_dispatch(
        c3_generate_visuals_task,
        req.presentation_id,
        str(user.id),
        force_regenerate=req.force_regenerate,
    )

    return {
        "success": True,
        "message": "Visual generation dispatched",
        "presentation_id": req.presentation_id,
    }


@c3_visual_router.get(
    "/presentation/{presentation_id}/ready",
    summary="Get all ready visuals for player consumption",
)
async def get_ready_visuals(
    presentation_id: str,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> dict[str, Any]:
    repo = TopicVisualAssetRepository(uow.session)
    pres_uuid = await _resolve_presentation(presentation_id, user, uow)

    assets = await repo.get_ready_assets_for_presentation(pres_uuid)

    return {
        "success": True,
        "data": [_serialize_asset_for_player(a) for a in assets],
    }


@c3_visual_router.delete(
    "/{asset_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft-delete a visual asset",
)
async def delete_visual_asset(
    asset_id: uuid.UUID,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> None:
    repo = TopicVisualAssetRepository(uow.session)
    await _assert_ownership(asset_id, user, repo)
    await repo.delete(asset_id, hard=False)


# ── Serialization Helpers ──────────────────────────────────────────────────


def _serialize_asset(asset: Any) -> dict[str, Any]:
    return {
        "id": str(asset.id),
        "public_id": asset.public_id,
        "visual_type": asset.visual_type,
        "title": asset.title,
        "status": asset.status,
        "asset_format": asset.asset_format,
        "asset_url": asset.asset_url,
        "topic_id": asset.topic_id,
        "topic_title": asset.topic_title,
        "subtopic_id": asset.subtopic_id,
        "subtopic_title": asset.subtopic_title,
        "provenance": asset.provenance,
        "confidence": asset.confidence,
        "version": asset.version,
        "explanation": asset.explanation,
        "source_references": asset.source_references or [],
        "concept_ids": asset.concept_ids or [],
        "created_at": asset.created_at.isoformat() if asset.created_at else None,
    }


def _serialize_asset_for_player(a: Any) -> dict[str, Any]:
    concept_ids = a.concept_ids or []
    topic_prefix = f"{a.topic_id or ''}:"
    concepts = [
        cid[len(topic_prefix) :] if cid.startswith(topic_prefix) else cid for cid in concept_ids
    ]
    return {
        "id": str(a.id),
        "public_id": a.public_id,
        "asset_id": str(a.id),
        "visual_type": a.visual_type,
        "title": a.title,
        "purpose": a.purpose or "",
        "learning_objective": a.learning_objective or "",
        "status": a.status,
        "asset_format": a.asset_format,
        "topic_id": a.topic_id,
        "topic_title": a.topic_title,
        "subtopic_id": a.subtopic_id,
        "subtopic_title": a.subtopic_title,
        "provenance": a.provenance,
        "confidence": a.confidence,
        "explanation": a.explanation or {},
        "specification": a.specification or {},
        "source_references": a.source_references or [],
        "concept_ids": concept_ids,
        "concepts": concepts,
        "svg_content": a.asset_content,
    }
