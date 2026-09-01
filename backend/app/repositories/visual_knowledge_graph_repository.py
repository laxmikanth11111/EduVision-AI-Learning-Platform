"""Repositories for Phase 4I.3 Visual Knowledge Graph Persistence Layer.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import NotFoundError
from app.database.repository import BaseRepository
from app.models.visual_knowledge_graph import (
    ComponentMetadata,
    LearningObjective,
    SimulationCandidate,
    VisualCanvas,
    VisualEdge,
    VisualLayout,
    VisualNode,
    VisualQuizBlueprint,
    VisualRelationship,
)


async def _ensure_canvas_active(
    session: AsyncSession, canvas_id: uuid.UUID | str
) -> None:
    """Raise NotFoundError if the canvas does not exist or is soft-deleted.

    Sub-graph queries (nodes/edges/layout/...) must never return data that
    belongs to a soft-deleted canvas, otherwise a deleted canvas's graph
    would remain reachable through standalone repository queries.
    """
    stmt = select(VisualCanvas.id).where(
        VisualCanvas.id == canvas_id,
        VisualCanvas.deleted_at.is_(None),
    )
    result = await session.execute(stmt)
    if result.scalar_one_or_none() is None:
        raise NotFoundError(
            message="Visual canvas not found or has been deleted",
            details={"canvas_id": str(canvas_id)},
        )


class VisualCanvasRepository(BaseRepository[VisualCanvas]):

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, VisualCanvas)

    async def get_by_public_id(self, public_id: str) -> VisualCanvas | None:
        return await self.find_one(public_id=public_id, deleted_at=None)

    async def get_canvas_with_full_graph(self, canvas_id: uuid.UUID) -> VisualCanvas | None:
        stmt = (
            select(VisualCanvas)
            .where(VisualCanvas.id == canvas_id, VisualCanvas.deleted_at.is_(None))
            .options(
                selectinload(VisualCanvas.nodes).selectinload(VisualNode.component_metadata),
                selectinload(VisualCanvas.edges),
                selectinload(VisualCanvas.learning_objective),
                selectinload(VisualCanvas.relationships),
                selectinload(VisualCanvas.layout),
                selectinload(VisualCanvas.simulation_candidates),
                selectinload(VisualCanvas.quiz_blueprint),
            )
        )
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_user_canvases(
        self,
        user_id: uuid.UUID | str,
        category: str | None = None,
        page: int = 1,
        page_size: int = 20,
        presentation_id: uuid.UUID | None = None,
    ) -> tuple[list[VisualCanvas], int]:
        filters: dict[str, Any] = {"user_id": user_id, "deleted_at": None}
        if category:
            filters["category"] = category
        if presentation_id is not None:
            filters["presentation_id"] = presentation_id

        return await self.paginate(
            page=page,
            page_size=page_size,
            order_by="created_at",
            descending=True,
            **filters,
        )


class VisualNodeRepository(BaseRepository[VisualNode]):

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, VisualNode)

    async def get_nodes_by_canvas(self, canvas_id: uuid.UUID) -> list[VisualNode]:
        await _ensure_canvas_active(self._session, canvas_id)
        stmt = (
            select(VisualNode)
            .where(VisualNode.canvas_id == canvas_id)
            .options(selectinload(VisualNode.component_metadata))
            .order_by(VisualNode.sort_order.asc())
        )
        res = await self._session.execute(stmt)
        return list(res.scalars().all())

    async def get_by_public_id(self, public_id: str) -> VisualNode | None:
        return await self.find_one(
            load_options=[selectinload(VisualNode.component_metadata)],
            public_id=public_id,
        )


class VisualEdgeRepository(BaseRepository[VisualEdge]):

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, VisualEdge)

    async def get_edges_by_canvas(self, canvas_id: uuid.UUID) -> list[VisualEdge]:
        await _ensure_canvas_active(self._session, canvas_id)
        return await self.find(canvas_id=canvas_id)


class ComponentMetadataRepository(BaseRepository[ComponentMetadata]):

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ComponentMetadata)

    async def get_by_node_id(self, node_id: uuid.UUID) -> ComponentMetadata | None:
        return await self.find_one(node_id=node_id)


class LearningObjectiveRepository(BaseRepository[LearningObjective]):

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, LearningObjective)

    async def get_by_canvas_id(self, canvas_id: uuid.UUID) -> LearningObjective | None:
        await _ensure_canvas_active(self._session, canvas_id)
        return await self.find_one(canvas_id=canvas_id)


class VisualRelationshipRepository(BaseRepository[VisualRelationship]):

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, VisualRelationship)

    async def get_by_canvas_id(self, canvas_id: uuid.UUID) -> list[VisualRelationship]:
        await _ensure_canvas_active(self._session, canvas_id)
        return await self.find(canvas_id=canvas_id)


class VisualLayoutRepository(BaseRepository[VisualLayout]):

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, VisualLayout)

    async def get_by_canvas_id(self, canvas_id: uuid.UUID) -> VisualLayout | None:
        await _ensure_canvas_active(self._session, canvas_id)
        return await self.find_one(canvas_id=canvas_id)


class SimulationCandidateRepository(BaseRepository[SimulationCandidate]):

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, SimulationCandidate)

    async def get_by_canvas_id(self, canvas_id: uuid.UUID) -> list[SimulationCandidate]:
        await _ensure_canvas_active(self._session, canvas_id)
        return await self.find(canvas_id=canvas_id)


class VisualQuizBlueprintRepository(BaseRepository[VisualQuizBlueprint]):

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, VisualQuizBlueprint)

    async def get_by_canvas_id(self, canvas_id: uuid.UUID) -> VisualQuizBlueprint | None:
        await _ensure_canvas_active(self._session, canvas_id)
        return await self.find_one(canvas_id=canvas_id)
