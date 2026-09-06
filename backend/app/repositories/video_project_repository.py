from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select

from app.database.repository import BaseRepository
from app.models.video_project import VideoProjectRecord, VideoRenderStatus


class VideoProjectRepository(BaseRepository[VideoProjectRecord]):
    def __init__(self, session: object) -> None:
        super().__init__(session, VideoProjectRecord)  # type: ignore[arg-type]

    async def create_project(
        self,
        user_id: uuid.UUID,
        video_id: str,
        topic: str,
        project_data: dict[str, object],
    ) -> VideoProjectRecord:
        return await self.create(
            user_id=user_id,
            video_id=video_id,
            topic=topic,
            status=VideoRenderStatus.QUEUED,
            progress_percentage=0.0,
            project_data=project_data,
        )

    async def get_by_user_and_public_id(
        self,
        user_id: uuid.UUID,
        public_id: str,
    ) -> VideoProjectRecord | None:
        return await self.find_one(public_id=public_id, user_id=user_id)

    async def get_by_user_and_video_id(
        self,
        user_id: uuid.UUID,
        video_id: str,
    ) -> VideoProjectRecord | None:
        return await self.find_one(video_id=video_id, user_id=user_id)

    async def list_by_user(self, user_id: uuid.UUID) -> Sequence[VideoProjectRecord]:
        rows = await self.find(user_id=user_id)
        return sorted(
            rows,
            key=lambda r: r.created_at or datetime.min,
            reverse=True,
        )

    async def count_active(self, user_id: uuid.UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(VideoProjectRecord)
            .where(
                VideoProjectRecord.user_id == user_id,
                VideoProjectRecord.status.in_(VideoRenderStatus.ACTIVE_STATUSES),
            )
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def exists_public_id(self, public_id: str) -> bool:
        return await self.exists(public_id=public_id)
