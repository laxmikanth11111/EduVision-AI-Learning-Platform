from __future__ import annotations

import uuid
from typing import Any

from app.core.exceptions import NotFoundError
from app.database.unit_of_work import UnitOfWork
from app.models.presentation import Presentation
from app.models.presentation_version import PresentationVersion
from app.repositories.presentation_version_repository import PresentationVersionRepository
from shared.constants import PresentationStatus


class PresentationVersionService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow
        self._repo = PresentationVersionRepository(uow.session)

    async def create_version(
        self,
        presentation: Presentation,
        created_by: uuid.UUID | None = None,
        diff_summary: str | None = None,
        max_retries: int = 3,
    ) -> PresentationVersion:
        from sqlalchemy.exc import IntegrityError

        from app.core.exceptions import ConflictError

        for attempt in range(max_retries):
            try:
                version_number = await self._repo.next_version_number(presentation.id)
                version = await self._repo.create(
                    presentation_id=presentation.id,
                    version_number=version_number,
                    title=presentation.title,
                    slide_count=presentation.slide_count,
                    diff_summary=diff_summary,
                    status=presentation.status,
                    created_by=created_by,
                )
                await self._uow.flush()
                return version
            except IntegrityError as exc:
                await self._uow.session.rollback()
                if attempt == max_retries - 1:
                    raise ConflictError(
                        message="Concurrent version creation conflict. Please retry your request.",
                        details={"presentation_id": presentation.public_id},
                    ) from exc
        raise ConflictError(message="Concurrent version creation conflict")

    async def get_version_for_presentation(
        self,
        presentation_id: uuid.UUID,
        public_id: str,
    ) -> PresentationVersion:
        version = await self._repo.get_by_public_id_for_presentation(
            presentation_id, public_id
        )
        if version is None:
            raise NotFoundError(
                message="Version not found",
                details={"version_id": public_id},
            )
        return version

    async def list_versions(
        self,
        presentation_id: uuid.UUID,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        versions = await self._repo.list_for_presentation(presentation_id, limit=limit)
        return [self._serialize(version) for version in versions]

    @staticmethod
    def _serialize(version: PresentationVersion) -> dict[str, Any]:
        return {
            "id": version.public_id,
            "presentation_id": version.presentation_id,
            "version": f"v{version.version_number}",
            "version_number": version.version_number,
            "title": version.title,
            "slide_count": version.slide_count,
            "diff_summary": version.diff_summary,
            "status": PresentationStatus(version.status),
            "created_by": version.created_by,
            "created_at": version.created_at,
        }

    @staticmethod
    def compare(
        from_version: PresentationVersion,
        to_version: PresentationVersion,
    ) -> dict[str, Any]:
        fields = [
            ("title", "title"),
            ("slide_count", "slide_count"),
            ("status", "status"),
        ]
        differences: dict[str, Any] = {}
        for field_name, attr in fields:
            left = getattr(from_version, attr)
            right = getattr(to_version, attr)
            if left != right:
                differences[field_name] = {
                    "from": PresentationVersionService._serialize_value(left),
                    "to": PresentationVersionService._serialize_value(right),
                }
        return {
            "from_version": PresentationVersionService._serialize(from_version),
            "to_version": PresentationVersionService._serialize(to_version),
            "differences": differences,
        }

    @staticmethod
    def _serialize_value(value: Any) -> Any:
        if isinstance(value, PresentationStatus):
            return value.value
        return value
