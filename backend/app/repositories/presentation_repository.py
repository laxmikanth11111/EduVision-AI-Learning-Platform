from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import ColumnElement, Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repository import BaseRepository, LoadType
from app.models.presentation import Presentation
from app.models.presentation_tag import PresentationTag
from shared.constants import PresentationStatus, PresentationVisibility

ALLOWED_SORT_FIELDS = {
    "title": Presentation.title,
    "created_at": Presentation.created_at,
    "updated_at": Presentation.updated_at,
    "published_at": Presentation.published_at,
    "slide_count": Presentation.slide_count,
}

ALLOWED_STATUSES = {status.value for status in PresentationStatus}
ALLOWED_VISIBILITIES = {visibility.value for visibility in PresentationVisibility}


class PresentationRepository(BaseRepository[Presentation]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Presentation)

    def _base_visible_query(self) -> Select[tuple[Presentation]]:
        return select(Presentation).where(Presentation.deleted_at.is_(None))

    async def get_by_public_id(
        self,
        public_id: str,
        load_options: LoadType | None = None,
    ) -> Presentation | None:
        stmt = self._base_visible_query().where(Presentation.public_id == public_id)
        stmt = self._apply_load_options(stmt, load_options)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_public_id_or_raise(
        self,
        public_id: str,
        load_options: LoadType | None = None,
    ) -> Presentation:
        instance = await self.get_by_public_id(public_id, load_options=load_options)
        if instance is None:
            raise self._not_found(public_id)
        return instance

    async def get_by_public_id_including_deleted(
        self,
        public_id: str,
    ) -> Presentation | None:
        stmt = select(Presentation).where(Presentation.public_id == public_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_deleted_by_public_id(
        self,
        public_id: str,
    ) -> Presentation | None:
        stmt = select(Presentation).where(
            Presentation.public_id == public_id,
            Presentation.deleted_at.is_not(None),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    def _not_found(self, public_id: str) -> Exception:
        from app.core.exceptions import NotFoundError

        return NotFoundError(
            message="Presentation not found",
            details={"presentation_id": public_id},
        )

    async def list_viewable_for_user(
        self,
        user_id: uuid.UUID,
        limit: int = 200,
    ) -> list[Presentation]:
        """Presentations the user owns or collaborates on (not deleted)."""
        from app.models.presentation_collaborator import PresentationCollaborator

        stmt = (
            select(Presentation)
            .where(
                Presentation.deleted_at.is_(None),
                or_(
                    Presentation.owner_id == user_id,
                    Presentation.id.in_(
                        select(PresentationCollaborator.presentation_id).where(
                            PresentationCollaborator.user_id == user_id
                        )
                    ),
                ),
            )
            .order_by(Presentation.updated_at.desc(), Presentation.id)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def search(
        self,
        *,
        user_id: uuid.UUID | str | None,
        q: str | None = None,
        status: str | None = None,
        subject_id: str | None = None,
        grade_level: str | None = None,
        folder_id: uuid.UUID | None = None,
        tag: str | None = None,
        topic: str | None = None,
        visibility: str | None = None,
        is_admin: bool = False,
        page: int = 1,
        page_size: int = 25,
        sort: str = "updated_at",
        descending: bool = True,
    ) -> tuple[list[Presentation], int]:
        page = max(1, page)
        page_size = min(max(1, page_size), 100)

        conditions: list[ColumnElement[bool]] = [Presentation.deleted_at.is_(None)]

        if not is_admin and user_id is not None:
            conditions.append(Presentation.owner_id == user_id)

        if q:
            conditions.append(
                or_(
                    Presentation.title.ilike(f"%{q}%"),
                    Presentation.description.ilike(f"%{q}%"),
                    Presentation.topic.ilike(f"%{q}%"),
                )
            )
        if status:
            if status not in ALLOWED_STATUSES:
                from app.core.exceptions import ValidationError

                raise ValidationError(
                    message=f"Invalid status '{status}'",
                    details={"allowed": sorted(ALLOWED_STATUSES)},
                )
            conditions.append(Presentation.status == status)
        if visibility:
            if visibility not in ALLOWED_VISIBILITIES:
                from app.core.exceptions import ValidationError

                raise ValidationError(
                    message=f"Invalid visibility '{visibility}'",
                    details={"allowed": sorted(ALLOWED_VISIBILITIES)},
                )
            conditions.append(Presentation.visibility == visibility)
        if subject_id:
            conditions.append(Presentation.subject_id == subject_id)
        if grade_level:
            conditions.append(Presentation.grade_level == grade_level)
        if folder_id:
            conditions.append(Presentation.folder_id == folder_id)
        if topic:
            conditions.append(Presentation.topic.ilike(f"%{topic}%"))
        if tag:
            conditions.append(
                Presentation.id.in_(
                    select(PresentationTag.presentation_id).where(
                        PresentationTag.name == tag
                    )
                )
            )

        base_stmt = select(Presentation).where(*conditions)

        count_stmt = select(func.count()).select_from(
            Presentation
        ).where(*conditions)
        count_result = await self._session.execute(count_stmt)
        total = count_result.scalar_one()

        sort_col = ALLOWED_SORT_FIELDS.get(sort)
        if sort_col is None:
            from app.core.exceptions import ValidationError

            raise ValidationError(
                message=f"Invalid sort field '{sort}'",
                details={"allowed": sorted(ALLOWED_SORT_FIELDS.keys())},
            )
        order_cols: list[Any] = [sort_col.desc() if descending else sort_col.asc()]
        if sort != "id":
            order_cols.append(Presentation.id.asc())

        offset = (page - 1) * page_size
        stmt = base_stmt.order_by(*order_cols).offset(offset).limit(page_size)

        result = await self._session.execute(stmt)
        items = list(result.scalars().all())
        return items, total

    async def update_public(
        self, public_id: str, **kwargs: Any
    ) -> Presentation:
        instance = await self.get_by_public_id_or_raise(public_id)
        for key, value in kwargs.items():
            if hasattr(instance, key):
                setattr(instance, key, value)
        await self._session.flush()
        await self._session.refresh(instance)
        return instance

    async def count_by_owner(self, owner_id: uuid.UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(Presentation)
            .where(
                Presentation.owner_id == owner_id,
                Presentation.deleted_at.is_(None),
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()
