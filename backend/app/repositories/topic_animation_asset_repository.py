"""Repository for C4 Topic Animation Assets persistence."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repository import BaseRepository
from app.models.presentation import Presentation
from app.models.topic_animation_asset import TopicAnimationAsset


class TopicAnimationAssetRepository(BaseRepository[TopicAnimationAsset]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(model=TopicAnimationAsset, session=session)

    async def lock_generation(self, presentation_id: uuid.UUID, user_id: uuid.UUID) -> None:
        """Serialize generation on the owner-scoped parent row until commit.

        PostgreSQL row locks protect empty-asset races as well as regeneration;
        a worker crash releases the transaction lock automatically.
        """
        result = await self._session.execute(
            select(Presentation.id).where(
                Presentation.id == presentation_id,
                Presentation.owner_id == user_id,
                Presentation.deleted_at.is_(None),
            ).with_for_update()
        )
        if result.scalar_one_or_none() is None:
            from app.core.exceptions import NotFoundError

            raise NotFoundError(message="Presentation not found")

    async def next_version(self, fingerprint: str) -> int:
        result = await self._session.execute(
            select(func.max(TopicAnimationAsset.version)).where(
                TopicAnimationAsset.fingerprint == fingerprint
            )
        )
        return int(result.scalar() or 0) + 1

    async def get_by_fingerprint(self, fingerprint: str) -> TopicAnimationAsset | None:
        stmt = select(TopicAnimationAsset).where(
            TopicAnimationAsset.fingerprint == fingerprint,
            TopicAnimationAsset.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def get_ready_by_fingerprint(self, fingerprint: str) -> TopicAnimationAsset | None:
        stmt = select(TopicAnimationAsset).where(
            TopicAnimationAsset.fingerprint == fingerprint,
            TopicAnimationAsset.status == "ready",
            TopicAnimationAsset.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def list_by_presentation(
        self,
        presentation_id: uuid.UUID,
        *,
        status: str | None = None,
        topic_id: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[TopicAnimationAsset], int]:
        base = select(TopicAnimationAsset).where(
            TopicAnimationAsset.presentation_id == presentation_id,
            TopicAnimationAsset.deleted_at.is_(None),
        )
        if status:
            base = base.where(TopicAnimationAsset.status == status)
        if topic_id:
            base = base.where(TopicAnimationAsset.topic_id == topic_id)

        count_stmt = select(func.count()).select_from(base.subquery())
        total = (await self._session.execute(count_stmt)).scalar() or 0

        base = base.order_by(
            TopicAnimationAsset.topic_id,
            TopicAnimationAsset.subtopic_id,
            TopicAnimationAsset.version.desc(),
        )
        base = base.offset((page - 1) * page_size).limit(page_size)

        result = await self._session.execute(base)
        return list(result.scalars().all()), total

    async def list_by_topic(
        self,
        presentation_id: uuid.UUID,
        topic_id: str,
    ) -> list[TopicAnimationAsset]:
        stmt = (
            select(TopicAnimationAsset)
            .where(
                TopicAnimationAsset.presentation_id == presentation_id,
                TopicAnimationAsset.topic_id == topic_id,
                TopicAnimationAsset.deleted_at.is_(None),
            )
            .order_by(
                TopicAnimationAsset.subtopic_id,
                TopicAnimationAsset.version.desc(),
            )
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id_and_user(
        self,
        asset_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> TopicAnimationAsset | None:
        stmt = select(TopicAnimationAsset).where(
            TopicAnimationAsset.id == asset_id,
            TopicAnimationAsset.user_id == user_id,
            TopicAnimationAsset.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def get_ready_assets_for_presentation(
        self,
        presentation_id: uuid.UUID,
    ) -> list[TopicAnimationAsset]:
        stmt = (
            select(TopicAnimationAsset)
            .where(
                TopicAnimationAsset.presentation_id == presentation_id,
                TopicAnimationAsset.status == "ready",
                TopicAnimationAsset.deleted_at.is_(None),
            )
            .order_by(
                TopicAnimationAsset.topic_id,
                TopicAnimationAsset.subtopic_id,
            )
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def supersede_old_version(
        self,
        fingerprint: str,
        exclude_id: uuid.UUID,
    ) -> int:
        """Mark older ready versions as superseded when a new version is created."""
        from sqlalchemy import update

        stmt = (
            update(TopicAnimationAsset)
            .where(
                TopicAnimationAsset.fingerprint == fingerprint,
                TopicAnimationAsset.status == "ready",
                TopicAnimationAsset.id != exclude_id,
            )
            .values(status="superseded")
        )
        result = await self._session.execute(stmt)
        return int(getattr(result, "rowcount", 0) or 0)

    async def count_by_presentation(
        self,
        presentation_id: uuid.UUID,
        *,
        status: str | None = None,
    ) -> int:
        base = (
            select(func.count())
            .select_from(TopicAnimationAsset)
            .where(
                TopicAnimationAsset.presentation_id == presentation_id,
                TopicAnimationAsset.deleted_at.is_(None),
            )
        )
        if status:
            base = base.where(TopicAnimationAsset.status == status)
        result = await self._session.execute(base)
        return result.scalar() or 0
