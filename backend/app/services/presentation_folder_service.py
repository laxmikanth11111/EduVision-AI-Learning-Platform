from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import update

from app.core.exceptions import ConflictError, NotFoundError
from app.core.logging import get_logger
from app.database.unit_of_work import UnitOfWork
from app.models.presentation import Presentation
from app.models.presentation_folder import PresentationFolder
from app.repositories.presentation_folder_repository import PresentationFolderRepository

logger = get_logger(__name__)


class PresentationFolderService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow
        self._repo = PresentationFolderRepository(uow.session)

    async def _assert_folder_owner(
        self, folder: PresentationFolder, owner_id: uuid.UUID
    ) -> None:
        # A folder owned by someone else is indistinguishable from a missing
        # one (no resource-existence or ownership oracle at the API boundary).
        if folder.owner_id != owner_id:
            raise NotFoundError(message="Folder not found")

    async def validate_folder_ownership(
        self, folder_id: uuid.UUID, owner_id: uuid.UUID | None
    ) -> PresentationFolder:
        """Return *folder_id* if it belongs to *owner_id*, else raise 404.

        Used when a caller attaches an existing folder to a presentation. The
        caller must supply the acting owner: without it there is nothing to
        compare against, so the check fails closed rather than trusting an
        unauthenticated ``folder_id``.

        This method used to be referenced by ``PresentationService`` but never
        existed (only the private ``_assert_folder_owner`` did), so every
        presentation create/update carrying a ``folder_id`` raised
        ``AttributeError`` -> 500.
        """
        if owner_id is None:
            raise NotFoundError(message="Folder not found")
        folder = await self._repo.get(folder_id)
        if folder is None:
            raise NotFoundError(message="Folder not found")
        await self._assert_folder_owner(folder, owner_id)
        return folder

    async def create_folder(
        self,
        name: str,
        owner_id: uuid.UUID,
        parent_id: uuid.UUID | None = None,
    ) -> PresentationFolder:
        if parent_id is not None:
            parent = await self._repo.get(parent_id)
            if parent is None or parent.owner_id != owner_id:
                raise NotFoundError(message="Parent folder not found")
        folder = await self._repo.create(
            name=name,
            owner_id=owner_id,
            parent_id=parent_id,
        )
        logger.info(
            "folder_created",
            folder_id=str(folder.id),
            actor_id=str(owner_id),
            name=name,
            parent_id=str(parent_id) if parent_id else None,
        )
        await self._uow.flush()
        return folder

    async def update_folder(
        self,
        folder_id: uuid.UUID,
        owner_id: uuid.UUID,
        name: str | None = None,
        parent_id: uuid.UUID | None = None,
    ) -> PresentationFolder:
        folder = await self._repo.get(folder_id)
        if folder is None:
            raise NotFoundError(message="Folder not found")
        await self._assert_folder_owner(folder, owner_id)

        new_parent_id = parent_id if parent_id is not None else folder.parent_id
        if new_parent_id is not None:
            if new_parent_id == folder.id:
                raise ConflictError(message="A folder cannot be its own parent")
            parent = await self._repo.get(new_parent_id)
            if parent is None or parent.owner_id != owner_id:
                raise NotFoundError(message="Parent folder not found")
            await self._ensure_cycle_free(folder.id, parent.id)

        if name is not None:
            folder.name = name
        folder.parent_id = new_parent_id

        logger.info(
            "folder_updated",
            folder_id=str(folder.id),
            actor_id=str(owner_id),
            name=name,
            parent_id=str(new_parent_id) if new_parent_id else None,
        )
        await self._uow.flush()
        fresh = await self._repo.get(folder.id)
        return fresh if fresh is not None else folder

    async def delete_folder(self, folder_id: uuid.UUID, owner_id: uuid.UUID) -> None:
        folder = await self._repo.get(folder_id)
        if folder is None:
            raise NotFoundError(message="Folder not found")
        await self._assert_folder_owner(folder, owner_id)

        stmt = update(Presentation).where(
            Presentation.folder_id == folder.id,
            Presentation.deleted_at.is_(None),
        ).values(folder_id=None)
        await self._uow.session.execute(stmt)

        for child in await self._repo.find_all(parent_id=folder.id):
            child.parent_id = None

        logger.info(
            "folder_deleted",
            folder_id=str(folder.id),
            actor_id=str(owner_id),
        )
        await self._repo.delete(folder.id, hard=True)
        await self._uow.flush()
        logger.info("folder_deleted_done", folder_id=str(folder.id))

    async def list_folders(
        self, owner_id: uuid.UUID, include_presentation_count: bool = True
    ) -> list[dict[str, Any]]:
        folders = await self._repo.find_owned(owner_id=owner_id)
        result: list[dict[str, Any]] = []
        for folder in folders:
            count = 0
            if include_presentation_count:
                count = await self._repo.count_presentations(folder.id)
            result.append(self._serialize(folder, presentation_count=count))
        return result

    async def get_breadcrumbs(
        self, folder_id: uuid.UUID, owner_id: uuid.UUID
    ) -> list[dict[str, Any]]:
        folder = await self._repo.get(folder_id)
        if folder is None:
            raise NotFoundError(message="Folder not found")
        await self._assert_folder_owner(folder, owner_id)
        crumbs: list[dict[str, Any]] = []
        current: PresentationFolder | None = folder
        visited: set[uuid.UUID] = set()
        while current is not None and current.id not in visited:
            visited.add(current.id)
            crumbs.append(
                {
                    "id": current.id,
                    "name": current.name,
                    "parent_id": current.parent_id,
                }
            )
            if current.parent_id is None:
                break
            parent = await self._repo.get(current.parent_id)
            current = parent
        crumbs.reverse()
        return crumbs

    async def _ensure_cycle_free(
        self,
        folder_id: uuid.UUID,
        new_parent_id: uuid.UUID,
    ) -> None:
        current: uuid.UUID | None = new_parent_id
        visited: set[uuid.UUID] = set()
        while current is not None:
            if current == folder_id:
                raise ConflictError(message="Folder move would create a cycle")
            if current in visited:
                break
            visited.add(current)
            parent = await self._repo.get(current)
            if parent is None:
                break
            current = parent.parent_id

    @staticmethod
    def _serialize(
        folder: PresentationFolder,
        presentation_count: int = 0,
    ) -> dict[str, Any]:
        return {
            "id": folder.id,
            "name": folder.name,
            "owner_id": folder.owner_id,
            "parent_id": folder.parent_id,
            "presentation_count": presentation_count,
            "created_at": folder.created_at,
            "updated_at": folder.updated_at,
        }

