"""C4 Animation API Router — endpoints for advanced animation intelligence.

Mirrors the C3 visual router under the ``/c4/animations`` prefix, providing
CRUD, player consumption, and generation dispatch for deterministic educational
animation packages. The legacy ``/animations`` router (4J blueprint engine) is
left untouched and continues to serve in-memory sessions only.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import BaseModel

from app.core.dependencies import get_current_user
from app.core.exceptions import NotFoundError
from app.database.unit_of_work import UnitOfWork, get_unit_of_work
from app.models.user import User
from app.repositories.topic_animation_asset_repository import (
    TopicAnimationAssetRepository,
)
from app.schemas.c4_animation_intelligence import AnimationGenerationRequest

c4_animation_router = APIRouter(prefix="/c4/animations", tags=["C4 Advanced Animations"])


class C4AnimationAssetResponse(BaseModel):
    id: str
    public_id: str
    animation_type: str
    title: str
    status: str
    asset_format: str
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


# ── Helpers ────────────────────────────────────────────────────────────────


async def _assert_animation_ownership(
    asset_id: uuid.UUID,
    user: User,
    repo: TopicAnimationAssetRepository,
) -> Any:
    asset = await repo.get_by_id_and_user(asset_id, user.id)
    if not asset:
        raise NotFoundError(
            message="Animation asset not found",
            details={"asset_id": str(asset_id)},
        )
    return asset


async def _resolve_presentation(
    presentation_id: str,
    user: User,
    uow: UnitOfWork,
) -> uuid.UUID:
    from app.repositories.presentation_repository import PresentationRepository

    pres_repo = PresentationRepository(uow.session)
    presentation = await pres_repo.get_by_public_id(presentation_id)
    if not presentation or str(presentation.owner_id) != str(user.id):
        raise NotFoundError(
            message="Presentation not found",
            details={"presentation_id": presentation_id},
        )
    return presentation.id


# ── Endpoints ──────────────────────────────────────────────────────────────


@c4_animation_router.get(
    "/presentation/{presentation_id}",
    summary="List all animation assets for a presentation",
)
async def list_presentation_animations(
    presentation_id: str,
    user: User = Depends(get_current_user),
    status_filter: str | None = Query(default=None, alias="status"),
    topic_id: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> dict[str, Any]:
    repo = TopicAnimationAssetRepository(uow.session)
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
        "pagination": {"page": page, "page_size": page_size, "total": total},
    }


@c4_animation_router.get(
    "/presentation/{presentation_id}/topic/{topic_id}",
    summary="List animation assets for a specific topic",
)
async def get_topic_animations(
    presentation_id: str,
    topic_id: str,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> dict[str, Any]:
    repo = TopicAnimationAssetRepository(uow.session)
    pres_uuid = await _resolve_presentation(presentation_id, user, uow)
    assets = await repo.list_by_topic(pres_uuid, topic_id)
    return {
        "success": True,
        "data": [_serialize_asset(a) for a in assets],
    }


@c4_animation_router.get(
    "/{asset_id}",
    summary="Get a single animation asset",
)
async def get_animation_asset(
    asset_id: uuid.UUID,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> dict[str, Any]:
    repo = TopicAnimationAssetRepository(uow.session)
    asset = await _assert_animation_ownership(asset_id, user, repo)
    return {"success": True, "data": _serialize_asset(asset)}


@c4_animation_router.get(
    "/{asset_id}/html",
    summary="Get the self-contained animation package HTML",
)
async def get_animation_html(
    asset_id: uuid.UUID,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> Response:
    repo = TopicAnimationAssetRepository(uow.session)
    asset = await _assert_animation_ownership(asset_id, user, repo)
    if not asset.package_content:
        raise NotFoundError(
            message="Animation package content not available",
            details={"asset_id": str(asset_id)},
        )
    return Response(
        content=asset.package_content,
        media_type="text/html; charset=utf-8",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@c4_animation_router.get(
    "/{asset_id}/download",
    summary="Download an animation package for offline self-study",
)
async def download_animation(
    asset_id: uuid.UUID,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> Response:
    repo = TopicAnimationAssetRepository(uow.session)
    asset = await _assert_animation_ownership(asset_id, user, repo)

    if asset.status != "ready" or not asset.package_content:
        raise NotFoundError(
            message="Animation asset is not ready for download",
            details={"asset_id": str(asset_id), "status": asset.status},
        )

    safe_title = "".join(c if c.isalnum() or c in " -_" else "" for c in asset.title)
    safe_title = safe_title.strip().replace(" ", "_")[:50]

    return Response(
        content=asset.package_content,
        media_type="text/html; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_title}.html"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@c4_animation_router.get(
    "/presentation/{presentation_id}/ready",
    summary="Get all ready animation assets for player consumption",
)
async def get_ready_animations(
    presentation_id: str,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> dict[str, Any]:
    repo = TopicAnimationAssetRepository(uow.session)
    pres_uuid = await _resolve_presentation(presentation_id, user, uow)
    assets = await repo.get_ready_assets_for_presentation(pres_uuid)
    return {
        "success": True,
        "data": [_serialize_asset_for_player(a) for a in assets],
    }


@c4_animation_router.post(
    "/generate",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger async animation generation for a presentation",
)
async def trigger_animation_generation(
    req: AnimationGenerationRequest,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> dict[str, Any]:
    from app.repositories.presentation_repository import PresentationRepository

    pres_repo = PresentationRepository(uow.session)
    presentation = await pres_repo.get_by_public_id(req.presentation_id)
    if not presentation or str(presentation.owner_id) != str(user.id):
        raise NotFoundError(
            message="Presentation not found",
            details={"presentation_id": req.presentation_id},
        )
    from app.workers.c4_animation_tasks import c4_generate_animations_task
    from app.workers.tasks import safe_dispatch

    safe_dispatch(
        c4_generate_animations_task,
        req.presentation_id,
        str(user.id),
        force_regenerate=req.force_regenerate,
    )
    return {
        "success": True,
        "message": "Animation generation dispatched",
        "presentation_id": req.presentation_id,
    }


@c4_animation_router.delete(
    "/{asset_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft-delete an animation asset",
)
async def delete_animation_asset(
    asset_id: uuid.UUID,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> None:
    repo = TopicAnimationAssetRepository(uow.session)
    await _assert_animation_ownership(asset_id, user, repo)
    await repo.delete(asset_id, hard=False)


# ── Serialization Helpers ──────────────────────────────────────────────────


def _serialize_asset(asset: Any) -> dict[str, Any]:
    return {
        "id": str(asset.id),
        "public_id": asset.public_id,
        "animation_type": asset.animation_type,
        "title": asset.title,
        "status": asset.status,
        "asset_format": asset.asset_format,
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
    spec = a.specification or {}
    return {
        "id": str(a.id),
        "asset_id": str(a.id),
        "animation_type": a.animation_type,
        "title": a.title,
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
        "package_content": a.package_content or "",
        "pedagogical_rationale": spec.get("pedagogical_rationale") or "",
    }
