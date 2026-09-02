"""Concept repository — data access for concept CRUD and queries."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repository import BaseRepository
from app.models.concept import Concept


class ConceptRepository(BaseRepository[Concept]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Concept)

    async def get_by_public_id(self, public_id: str) -> Concept | None:
        stmt = select(Concept).where(Concept.public_id == public_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_public_id_or_raise(self, public_id: str) -> Concept:
        concept = await self.get_by_public_id(public_id)
        if concept is None:
            from app.core.exceptions import NotFoundError
            raise NotFoundError(
                message="Concept not found",
                details={"concept_id": public_id},
            )
        return concept

    async def find_by_name_and_presentation(
        self,
        name: str,
        presentation_id: uuid.UUID | None,
    ) -> Concept | None:
        """Find an existing concept by name and presentation."""
        stmt = select(Concept).where(
            Concept.name == name,
            Concept.presentation_id == presentation_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_or_create(
        self,
        name: str,
        *,
        description: str | None = None,
        topic: str | None = None,
        presentation_id: uuid.UUID | None = None,
        lesson_id: uuid.UUID | None = None,
        difficulty_level: str = "intermediate",
    ) -> Concept:
        """Get existing concept by name+presentation, or create new one."""
        existing = await self.find_by_name_and_presentation(name, presentation_id)
        if existing:
            return existing

        concept = Concept(
            name=name,
            description=description,
            topic=topic,
            presentation_id=presentation_id,
            lesson_id=lesson_id,
            difficulty_level=difficulty_level,
        )
        self._session.add(concept)
        await self._session.flush()
        await self._session.refresh(concept)
        return concept

    async def list_by_presentation(
        self,
        presentation_id: uuid.UUID,
    ) -> list[Concept]:
        stmt = (
            select(Concept)
            .where(Concept.presentation_id == presentation_id)
            .order_by(Concept.name)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_lesson(
        self,
        lesson_id: uuid.UUID,
    ) -> list[Concept]:
        stmt = (
            select(Concept)
            .where(Concept.lesson_id == lesson_id)
            .order_by(Concept.name)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_topic(
        self,
        topic: str,
    ) -> list[Concept]:
        stmt = (
            select(Concept)
            .where(Concept.topic == topic)
            .order_by(Concept.name)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_ids(self, concept_ids: list[uuid.UUID]) -> list[Concept]:
        if not concept_ids:
            return []
        stmt = select(Concept).where(Concept.id.in_(concept_ids))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
