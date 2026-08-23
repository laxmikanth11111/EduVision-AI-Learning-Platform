from __future__ import annotations

import uuid

from sqlalchemy import delete as sql_delete

from app.database.unit_of_work import UnitOfWork
from app.models.presentation_tag import PresentationTag
from app.repositories.presentation_tag_repository import PresentationTagRepository


class PresentationTagService:
    MAX_TAGS = 50
    TAG_MAX_LENGTH = 50

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow
        self._repo = PresentationTagRepository(uow.session)

    def _clean(self, names: list[str]) -> list[str]:
        cleaned: list[str] = []
        seen: set[str] = set()
        for raw in names:
            name = raw.strip()
            if not name:
                continue
            if len(name) > self.TAG_MAX_LENGTH:
                name = name[: self.TAG_MAX_LENGTH]
            lower = name.casefold()
            if lower in seen:
                continue
            seen.add(lower)
            cleaned.append(name)
        return cleaned[: self.MAX_TAGS]

    async def set_tags(self, presentation_id: uuid.UUID, names: list[str]) -> list[PresentationTag]:
        cleaned = self._clean(names)
        stmt = sql_delete(PresentationTag).where(
            PresentationTag.presentation_id == presentation_id
        )
        await self._uow.session.execute(stmt)

        for name in cleaned:
            await self._repo.create(presentation_id=presentation_id, name=name)
        return await self.list_tags(presentation_id)

    async def list_tags(self, presentation_id: uuid.UUID) -> list[PresentationTag]:
        return await self._repo.list_for_presentation(presentation_id)

    async def tag_names(self, presentation_id: uuid.UUID) -> list[str]:
        return [tag.name for tag in await self.list_tags(presentation_id)]
