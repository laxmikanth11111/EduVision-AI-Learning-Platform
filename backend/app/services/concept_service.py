"""Concept service — business logic for concept creation and queries."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.repositories.concept_repository import ConceptRepository

logger = get_logger(__name__)


class ConceptService:

    def __init__(self, session: AsyncSession) -> None:
        self._repo = ConceptRepository(session)
        self._session = session

    async def get_or_create_concept(
        self,
        name: str,
        *,
        description: str | None = None,
        topic: str | None = None,
        presentation_id: uuid.UUID | None = None,
        lesson_id: uuid.UUID | None = None,
        difficulty_level: str = "intermediate",
    ) -> dict[str, Any]:
        """Get or create a concept, returning it as a dict."""
        concept = await self._repo.get_or_create(
            name,
            description=description,
            topic=topic,
            presentation_id=presentation_id,
            lesson_id=lesson_id,
            difficulty_level=difficulty_level,
        )
        return {
            "id": concept.id,
            "public_id": concept.public_id,
            "name": concept.name,
        }

    async def get_concept(self, concept_public_id: str) -> dict[str, Any] | None:
        concept = await self._repo.get_by_public_id(concept_public_id)
        if concept is None:
            return None
        return {
            "id": concept.id,
            "public_id": concept.public_id,
            "name": concept.name,
            "description": concept.description,
            "topic": concept.topic,
            "difficulty_level": concept.difficulty_level,
        }

    async def list_concepts_for_presentation(
        self,
        presentation_id: uuid.UUID,
    ) -> list[dict[str, Any]]:
        concepts = await self._repo.list_by_presentation(presentation_id)
        return [
            {
                "id": c.id,
                "public_id": c.public_id,
                "name": c.name,
                "topic": c.topic,
            }
            for c in concepts
        ]

    async def find_concept_by_name(
        self,
        name: str,
        presentation_id: uuid.UUID | None,
    ) -> uuid.UUID | None:
        """Find concept by name+presentation, return its UUID or None."""
        concept = await self._repo.find_by_name_and_presentation(name, presentation_id)
        return concept.id if concept else None
