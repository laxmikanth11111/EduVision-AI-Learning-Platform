"""Repository for C3 Topic Visual Assets persistence."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repository import BaseRepository
from app.models.topic_visual_asset import TopicVisualAsset


class TopicVisualAssetRepository(BaseRepository[TopicVisualAsset]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(model=TopicVisualAsset, session=session)

    async def get_by_fingerprint(self, fingerprint: str) -> TopicVisualAsset | None:
        stmt = select(TopicVisualAsset).where(
            TopicVisualAsset.fingerprint == fingerprint,
            TopicVisualAsset.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def get_ready_by_fingerprint(self, fingerprint: str) -> TopicVisualAsset | None:
        stmt = select(TopicVisualAsset).where(
            TopicVisualAsset.fingerprint == fingerprint,
            TopicVisualAsset.status == "ready",
            TopicVisualAsset.deleted_at.is_(None),
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
    ) -> tuple[list[TopicVisualAsset], int]:
        base = select(TopicVisualAsset).where(
            TopicVisualAsset.presentation_id == presentation_id,
            TopicVisualAsset.deleted_at.is_(None),
        )
        if status:
            base = base.where(TopicVisualAsset.status == status)
        if topic_id:
            base = base.where(TopicVisualAsset.topic_id == topic_id)

        count_stmt = select(func.count()).select_from(base.subquery())
        total = (await self._session.execute(count_stmt)).scalar() or 0

        base = base.order_by(
            TopicVisualAsset.topic_id,
            TopicVisualAsset.subtopic_id,
            TopicVisualAsset.version.desc(),
        )
        base = base.offset((page - 1) * page_size).limit(page_size)

        result = await self._session.execute(base)
        return list(result.scalars().all()), total

    async def list_by_topic(
        self,
        presentation_id: uuid.UUID,
        topic_id: str,
    ) -> list[TopicVisualAsset]:
        stmt = (
            select(TopicVisualAsset)
            .where(
                TopicVisualAsset.presentation_id == presentation_id,
                TopicVisualAsset.topic_id == topic_id,
                TopicVisualAsset.deleted_at.is_(None),
            )
            .order_by(
                TopicVisualAsset.subtopic_id,
                TopicVisualAsset.version.desc(),
            )
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id_and_user(
        self,
        asset_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> TopicVisualAsset | None:
        stmt = select(TopicVisualAsset).where(
            TopicVisualAsset.id == asset_id,
            TopicVisualAsset.user_id == user_id,
            TopicVisualAsset.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def get_ready_assets_for_presentation(
        self,
        presentation_id: uuid.UUID,
    ) -> list[TopicVisualAsset]:
        stmt = (
            select(TopicVisualAsset)
            .where(
                TopicVisualAsset.presentation_id == presentation_id,
                TopicVisualAsset.status == "ready",
                TopicVisualAsset.deleted_at.is_(None),
            )
            .order_by(
                TopicVisualAsset.topic_id,
                TopicVisualAsset.subtopic_id,
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
            update(TopicVisualAsset)
            .where(
                TopicVisualAsset.fingerprint == fingerprint,
                TopicVisualAsset.status == "ready",
                TopicVisualAsset.id != exclude_id,
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
            .select_from(TopicVisualAsset)
            .where(
                TopicVisualAsset.presentation_id == presentation_id,
                TopicVisualAsset.deleted_at.is_(None),
            )
        )
        if status:
            base = base.where(TopicVisualAsset.status == status)
        result = await self._session.execute(base)
        return result.scalar() or 0
