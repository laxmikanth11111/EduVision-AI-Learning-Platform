from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.database.repository import BaseRepository
from app.models.generated_block import GeneratedBlock
from app.models.generated_lesson import GeneratedLesson
from app.models.generated_lesson_version import GeneratedLessonVersion


def _version_with_blocks() -> Any:
    from sqlalchemy.orm import selectinload

    return selectinload(GeneratedLessonVersion.blocks)


def _lesson_graph() -> Any:
    """Eager-load the presentation relationship used by player serialization."""
    from sqlalchemy.orm import selectinload

    return selectinload(GeneratedLesson.presentation)


class GeneratedLessonRepository(BaseRepository[GeneratedLesson]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, GeneratedLesson)

    async def get_by_public_id(self, public_id: str) -> GeneratedLesson | None:
        stmt = (
            select(GeneratedLesson)
            .where(GeneratedLesson.public_id == public_id)
            .options(_lesson_graph())
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_public_id_for_presentation(
        self,
        presentation_id: uuid.UUID,
        public_id: str,
    ) -> GeneratedLesson | None:
        stmt = select(GeneratedLesson).where(
            GeneratedLesson.presentation_id == presentation_id,
            GeneratedLesson.public_id == public_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_public_id_for_presentation_or_raise(
        self,
        presentation_id: uuid.UUID,
        public_id: str,
    ) -> GeneratedLesson:
        lesson = await self.get_by_public_id_for_presentation(presentation_id, public_id)
        if lesson is None:
            raise NotFoundError(
                message="Generated lesson not found",
                details={"lesson_id": public_id},
            )
        return lesson

    async def list_for_presentation(
        self,
        presentation_id: uuid.UUID,
        page: int = 1,
        page_size: int = 25,
        mode: str | None = None,
        status: str | None = None,
    ) -> tuple[list[GeneratedLesson], int]:
        filters = [GeneratedLesson.presentation_id == presentation_id]
        if mode:
            filters.append(GeneratedLesson.mode == mode)
        if status:
            filters.append(GeneratedLesson.status == status)

        count_stmt = (
            select(func.count()).select_from(GeneratedLesson).where(*filters)
        )
        total = (await self._session.execute(count_stmt)).scalar_one()

        stmt = (
            select(GeneratedLesson)
            .where(*filters)
            .order_by(GeneratedLesson.created_at.desc(), GeneratedLesson.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all()), int(total)

    async def count_for_presentation(self, presentation_id: uuid.UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(GeneratedLesson)
            .where(GeneratedLesson.presentation_id == presentation_id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def list_ready_for_presentations(
        self,
        presentation_ids: list[uuid.UUID],
        limit: int = 100,
    ) -> list[GeneratedLesson]:
        if not presentation_ids:
            return []
        stmt = (
            select(GeneratedLesson)
            .where(
                GeneratedLesson.presentation_id.in_(presentation_ids),
                GeneratedLesson.status == "ready",
            )
            .order_by(GeneratedLesson.updated_at.desc(), GeneratedLesson.id)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def find_by_idempotency_key(
        self,
        user_id: uuid.UUID | None,
        idempotency_key: str,
    ) -> GeneratedLesson | None:
        stmt = (
            select(GeneratedLesson)
            .where(
                GeneratedLesson.idempotency_key == idempotency_key,
            )
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


class GeneratedLessonVersionRepository(BaseRepository[GeneratedLessonVersion]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, GeneratedLessonVersion)

    async def get_by_public_id(
        self,
        public_id: str,
    ) -> GeneratedLessonVersion | None:
        stmt = (
            select(GeneratedLessonVersion)
            .where(GeneratedLessonVersion.public_id == public_id)
            .options(_version_with_blocks())
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_public_id_for_lesson(
        self,
        lesson_id: uuid.UUID,
        public_id: str,
    ) -> GeneratedLessonVersion | None:
        stmt = (
            select(GeneratedLessonVersion)
            .where(
                GeneratedLessonVersion.lesson_id == lesson_id,
                GeneratedLessonVersion.public_id == public_id,
            )
            .options(_version_with_blocks())
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_public_id_for_lesson_or_raise(
        self,
        lesson_id: uuid.UUID,
        public_id: str,
    ) -> GeneratedLessonVersion:
        version = await self.get_by_public_id_for_lesson(lesson_id, public_id)
        if version is None:
            raise NotFoundError(
                message="Generated lesson version not found",
                details={"version_id": public_id},
            )
        return version

    async def get_by_lesson_and_version(
        self,
        lesson_id: uuid.UUID,
        version: int,
    ) -> GeneratedLessonVersion | None:
        stmt = (
            select(GeneratedLessonVersion)
            .where(
                GeneratedLessonVersion.lesson_id == lesson_id,
                GeneratedLessonVersion.version == version,
            )
            .options(_version_with_blocks())
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_latest_succeeded_for_lesson(
        self,
        lesson_id: uuid.UUID,
    ) -> GeneratedLessonVersion | None:
        stmt = (
            select(GeneratedLessonVersion)
            .where(
                GeneratedLessonVersion.lesson_id == lesson_id,
                GeneratedLessonVersion.status == "succeeded",
            )
            .options(_version_with_blocks())
            .order_by(GeneratedLessonVersion.version.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_lesson(
        self,
        lesson_id: uuid.UUID,
    ) -> list[GeneratedLessonVersion]:
        stmt = (
            select(GeneratedLessonVersion)
            .where(GeneratedLessonVersion.lesson_id == lesson_id)
            .options(_version_with_blocks())
            .order_by(GeneratedLessonVersion.version.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_for_lesson(self, lesson_id: uuid.UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(GeneratedLessonVersion)
            .where(GeneratedLessonVersion.lesson_id == lesson_id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def delete_for_lesson(self, lesson_id: uuid.UUID) -> int:
        from sqlalchemy import delete

        version_ids = select(GeneratedLessonVersion.id).where(
            GeneratedLessonVersion.lesson_id == lesson_id
        )
        await self._session.execute(
            delete(GeneratedBlock).where(GeneratedBlock.lesson_version_id.in_(version_ids))
        )
        result = await self._session.execute(
            delete(GeneratedLessonVersion).where(
                GeneratedLessonVersion.lesson_id == lesson_id
            )
        )
        return int(getattr(result, "rowcount", 0) or 0)
