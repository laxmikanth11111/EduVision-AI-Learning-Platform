"""API Router for Visual Knowledge Graph Canvases (Phase 4I.3).
"""

from __future__ import annotations

import contextlib
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel

from app.core.dependencies import get_current_user
from app.core.exceptions import NotFoundError
from app.database.unit_of_work import UnitOfWork, get_unit_of_work
from app.models.user import User
from app.services.visual_intelligence_service import VisualIntelligenceService
from app.services.visual_persistence_service import VisualPersistenceService

visual_router = APIRouter(prefix="/visual/canvases", tags=["Visual Canvases"])


class CreateVisualCanvasRequest(BaseModel):
    content: str
    title: str | None = None
    presentation_id: uuid.UUID | None = None
    lesson_id: str | None = None
    slide_id: str | None = None
    content_unit_id: uuid.UUID | None = None


class UpdateVisualCanvasRequest(BaseModel):
    title: str | None = None
    category: str | None = None
    is_published: bool | None = None


async def _assert_canvas_owner(
    canvas_id: uuid.UUID,
    user: User,
    persistence_service: VisualPersistenceService,
) -> None:
    """Raise 404 if the canvas does not exist or does not belong to *user*.

    Ownership is strict: a canvas is only accessible to its owning user. A
    canvas with no owner (``user_id IS NULL``) is not owned by anyone and must
    never be reachable through this personal, owner-scoped API.
    """
    canvas = await persistence_service.canvas_repo.get_or_raise(canvas_id)
    if canvas.user_id is None or str(canvas.user_id) != str(user.id):
        raise NotFoundError(
            message="Canvas not found",
            details={"canvas_id": str(canvas_id)},
        )


@visual_router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Generate and persist a new Visual Knowledge Graph Canvas",
)
async def create_visual_canvas(
    req: CreateVisualCanvasRequest,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> dict[str, Any]:
    intel_service = VisualIntelligenceService()
    model = await intel_service.generate_visual_learning_model(req.content, title=req.title)

    persistence_service = VisualPersistenceService(uow.session)
    lesson_uuid = None
    if req.lesson_id:
        with contextlib.suppress(ValueError, TypeError):
            lesson_uuid = uuid.UUID(req.lesson_id)
    canvas = await persistence_service.save_visual_model(
        model,
        user_id=user.id,
        presentation_id=req.presentation_id,
        slide_id=req.slide_id,
        content_unit_id=req.content_unit_id,
        lesson_id=lesson_uuid,
    )
    # Commit before returning: the client immediately requests
    # /nodes, /edges and /components for the returned canvas_id and would
    # otherwise race this request's teardown commit and get 404 (same
    # transaction-ordering pattern as the auth register fix).
    await uow.commit()

    return {
        "success": True,
        "data": {
            "canvas_id": str(canvas.id),
            "public_id": canvas.public_id,
            "title": canvas.title,
            "category": canvas.category,
            "pattern_type": canvas.pattern_type,
            "created_at": canvas.created_at.isoformat(),
        },
    }


@visual_router.get(
    "",
    summary="List Visual Canvases, optionally scoped to a lesson",
)
async def list_visual_canvases(
    user: User = Depends(get_current_user),
    lesson_id: str | None = Query(
        default=None,
        description="Public lesson (or presentation) id to scope canvases to",
    ),
    category: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> dict[str, Any]:
    persistence_service = VisualPersistenceService(uow.session)

    canvases, total = await persistence_service.canvas_repo.list_user_canvases(
        user.id,
        category=category,
        page=page,
        page_size=page_size,
    )

    return {
        "success": True,
        "data": [
            {
                "canvas_id": str(canvas.id),
                "public_id": canvas.public_id,
                "title": canvas.title,
                "category": canvas.category,
                "pattern_type": canvas.pattern_type,
                "created_at": canvas.created_at.isoformat(),
            }
            for canvas in canvases
        ],
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
        },
    }


@visual_router.get(
    "/{canvas_id}",
    summary="Fetch full Visual Learning Model graph by Canvas ID",
)
async def get_visual_canvas(
    canvas_id: uuid.UUID,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> dict[str, Any]:
    persistence_service = VisualPersistenceService(uow.session)
    await _assert_canvas_owner(canvas_id, user, persistence_service)
    model = await persistence_service.load_visual_model(canvas_id)
    return {"success": True, "data": model.model_dump()}


@visual_router.put(
    "/{canvas_id}",
    summary="Update Visual Canvas metadata",
)
async def update_visual_canvas(
    canvas_id: uuid.UUID,
    req: UpdateVisualCanvasRequest,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> dict[str, Any]:
    persistence_service = VisualPersistenceService(uow.session)
    await _assert_canvas_owner(canvas_id, user, persistence_service)
    canvas = await persistence_service.canvas_repo.get_or_raise(canvas_id)

    update_kwargs: dict[str, Any] = {}
    if req.title is not None:
        update_kwargs["title"] = req.title
    if req.category is not None:
        update_kwargs["category"] = req.category
    if req.is_published is not None:
        update_kwargs["is_published"] = req.is_published

    if update_kwargs:
        canvas = await persistence_service.canvas_repo.update(canvas_id, **update_kwargs)

    return {
        "success": True,
        "data": {
            "canvas_id": str(canvas.id),
            "public_id": canvas.public_id,
            "title": canvas.title,
            "category": canvas.category,
            "is_published": canvas.is_published,
        },
    }


@visual_router.delete(
    "/{canvas_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a Visual Canvas",
)
async def delete_visual_canvas(
    canvas_id: uuid.UUID,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> None:
    persistence_service = VisualPersistenceService(uow.session)
    await _assert_canvas_owner(canvas_id, user, persistence_service)
    await persistence_service.canvas_repo.delete(canvas_id, hard=False)


@visual_router.get(
    "/{canvas_id}/nodes",
    summary="List visual nodes for a canvas",
)
async def get_canvas_nodes(
    canvas_id: uuid.UUID,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> dict[str, Any]:
    persistence_service = VisualPersistenceService(uow.session)
    await _assert_canvas_owner(canvas_id, user, persistence_service)
    nodes = await persistence_service.node_repo.get_nodes_by_canvas(canvas_id)
    return {
        "success": True,
        "data": [
            {
                "node_id": str(n.id),
                "public_id": n.public_id,
                "component_key": n.component_key,
                "label": n.label,
                "category": n.category,
                "position": n.position,
                "dimensions": n.dimensions,
                "style": n.style,
            }
            for n in nodes
        ],
    }


@visual_router.get(
    "/{canvas_id}/edges",
    summary="List visual edges for a canvas",
)
async def get_canvas_edges(
    canvas_id: uuid.UUID,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> dict[str, Any]:
    persistence_service = VisualPersistenceService(uow.session)
    await _assert_canvas_owner(canvas_id, user, persistence_service)
    edges = await persistence_service.edge_repo.get_edges_by_canvas(canvas_id)
    return {
        "success": True,
        "data": [
            {
                "edge_id": str(e.id),
                "edge_key": e.edge_key,
                "source_node_id": str(e.source_node_id),
                "target_node_id": str(e.target_node_id),
                "label": e.label,
                "relationship_type": e.relationship_type,
                "is_bidirectional": e.is_bidirectional,
            }
            for e in edges
        ],
    }


@visual_router.get(
    "/{canvas_id}/components",
    summary="List component metadata for a canvas",
)
async def get_canvas_components(
    canvas_id: uuid.UUID,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> dict[str, Any]:
    persistence_service = VisualPersistenceService(uow.session)
    await _assert_canvas_owner(canvas_id, user, persistence_service)
    nodes = await persistence_service.node_repo.get_nodes_by_canvas(canvas_id)
    components: list[dict[str, Any]] = []

    for n in nodes:
        meta = n.component_metadata
        if meta:
            components.append(
                {
                    "node_id": str(n.id),
                    "component_key": n.component_key,
                    "name": n.label,
                    "overview": meta.overview,
                    "detailed_working": meta.detailed_working,
                    "inputs": meta.inputs,
                    "outputs": meta.outputs,
                    "dependencies": meta.dependencies,
                    "real_world_analogy": meta.real_world_analogy,
                    "difficulty_level": meta.difficulty_level,
                }
            )

    return {"success": True, "data": components}


@visual_router.get(
    "/{canvas_id}/relationships",
    summary="List conceptual relationships for a canvas",
)
async def get_canvas_relationships(
    canvas_id: uuid.UUID,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> dict[str, Any]:
    persistence_service = VisualPersistenceService(uow.session)
    await _assert_canvas_owner(canvas_id, user, persistence_service)
    rels = await persistence_service.rel_repo.get_by_canvas_id(canvas_id)
    return {
        "success": True,
        "data": [
            {
                "relationship_id": str(r.id),
                "source_key": r.source_key,
                "target_key": r.target_key,
                "relationship_type": r.relationship_type,
                "description": r.description,
                "is_bidirectional": r.is_bidirectional,
            }
            for r in rels
        ],
    }


@visual_router.get(
    "/{canvas_id}/quiz-blueprint",
    summary="Get visual quiz blueprint for a canvas",
)
async def get_canvas_quiz_blueprint(
    canvas_id: uuid.UUID,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> dict[str, Any]:
    persistence_service = VisualPersistenceService(uow.session)
    await _assert_canvas_owner(canvas_id, user, persistence_service)
    quiz_bp = await persistence_service.quiz_repo.get_by_canvas_id(canvas_id)
    return {
        "success": True,
        "data": {
            "blueprint_id": str(quiz_bp.id) if quiz_bp else None,
            "quiz_focus_areas": quiz_bp.quiz_focus_areas if quiz_bp else [],
            "suggested_question_types": quiz_bp.suggested_question_types if quiz_bp else [],
            "question_items": quiz_bp.question_items if quiz_bp else [],
        },
    }
