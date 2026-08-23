from __future__ import annotations

import contextlib
from datetime import UTC, datetime
from typing import Any

from app.core.config import settings
from app.core.exceptions import ConflictError, ExtractionError
from app.core.logging import get_logger
from app.database.unit_of_work import UnitOfWork
from app.models.content_block import ContentBlock
from app.models.presentation import Presentation
from app.parsers.document_parser import parse_document
from app.repositories.content_repository import ContentUnitRepository
from app.repositories.presentation_repository import PresentationRepository
from app.storage.factory import get_storage_backend
from shared.constants import ContentBlockType, ContentUnitType, ExtractionStatus

logger = get_logger(__name__)

UNIT_TITLE_MAX_LENGTH = 500


def _fit_unit_title(title: str | None) -> str | None:
    if title is None:
        return None
    return title[:UNIT_TITLE_MAX_LENGTH]


class ContentExtractionService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow
        self._repo = ContentUnitRepository(uow.session)
        self._presentation_repo = PresentationRepository(uow.session)

    async def extract_presentation(self, public_id: str) -> dict[str, Any]:
        presentation = await self._presentation_repo.get_by_public_id_or_raise(public_id)

        if not presentation.file_key:
            raise ConflictError(
                message="No source file has been uploaded for this presentation",
                details={"presentation_id": public_id},
            )

        presentation.extraction_status = ExtractionStatus.PROCESSING.value
        presentation.extracted_at = None
        presentation.extraction_error = None
        await self._uow.flush()

        try:
            storage = await get_storage_backend()
            content = await storage.download_fileobj(presentation.file_key)
            units = parse_document(content, presentation.file_name or "")

            if not units:
                raise ExtractionError(
                    message="No content could be extracted from the source file",
                    details={"presentation_id": public_id},
                )

            if len(units) > settings.EXTRACTION_MAX_UNITS:
                raise ExtractionError(
                    message=(
                        f"Source file contains {len(units)} content units, "
                        f"exceeding the limit of {settings.EXTRACTION_MAX_UNITS}"
                    ),
                    details={
                        "units_count": len(units),
                        "max_units": settings.EXTRACTION_MAX_UNITS,
                    },
                )

            await self._repo.delete_for_presentation(presentation.id)
            for unit in units:
                unit_model = await self._repo.create(
                    presentation_id=presentation.id,
                    unit_type=unit.unit_type,
                    position=unit.position,
                    title=_fit_unit_title(unit.title),
                    raw_text=unit.raw_text,
                    source_page=unit.source_page,
                    metadata={},
                )
                for position, block in enumerate(
                    unit.blocks[: settings.EXTRACTION_MAX_BLOCKS_PER_UNIT]
                ):
                    self._uow.session.add(
                        ContentBlock(
                            content_unit_id=unit_model.id,
                            block_type=block.block_type,
                            position=position,
                            content=block.content,
                            meta=block.metadata or {},
                        )
                    )
                await self._uow.flush()

            presentation.extraction_status = ExtractionStatus.READY.value
            presentation.extracted_at = datetime.now(UTC)
            presentation.extraction_error = None
            presentation.slide_count = len(units)
            await self._uow.flush()

            logger.info(
                "content_extraction_completed",
                presentation_id=public_id,
                units=len(units),
            )
            return await self.get_status(presentation)
        except Exception as exc:
            logger.error(
                "content_extraction_failed",
                presentation_id=public_id,
                error=str(exc)[:500],
            )
            try:
                await self._uow.session.rollback()
            except Exception:
                logger.exception("content_extraction_rollback_failed")
            try:
                presentation = await self._presentation_repo.get_by_public_id_or_raise(public_id)
                presentation.extraction_status = ExtractionStatus.FAILED.value
                presentation.extraction_error = str(exc)[:1000]
                presentation.extracted_at = None
                await self._uow.flush()
                await self._uow.session.commit()
            except Exception:
                with contextlib.suppress(Exception):
                    await self._uow.session.rollback()
                logger.exception("content_extraction_failed_status_commit_failed")
            raise

    async def get_status(self, presentation: Presentation) -> dict[str, Any]:
        status = presentation.extraction_status or ExtractionStatus.NONE.value
        units_count = await self._repo.count_for_presentation(presentation.id)
        return {
            "presentation_id": presentation.public_id,
            "extraction_status": ExtractionStatus(status),
            "units_count": units_count,
            "extracted_at": presentation.extracted_at,
            "extraction_error": presentation.extraction_error,
        }

    async def list_content(
        self,
        presentation: Presentation,
        include_blocks: bool = True,
    ) -> dict[str, Any]:
        units = await self._repo.list_for_presentation(
            presentation.id,
            include_blocks=include_blocks,
        )
        status = presentation.extraction_status or ExtractionStatus.NONE.value
        return {
            "presentation_id": presentation.public_id,
            "extraction_status": ExtractionStatus(status),
            "units": [self._serialize_unit(unit, include_blocks=include_blocks) for unit in units],
        }

    @staticmethod
    def _serialize_unit(
        unit: Any,
        include_blocks: bool = True,
    ) -> dict[str, Any]:
        blocks: list[dict[str, Any]] = []
        if include_blocks:
            blocks = [
                {
                    "id": block.public_id,
                    "block_type": ContentBlockType(block.block_type),
                    "position": block.position,
                    "content": block.content,
                    "metadata": block.meta or {},
                }
                for block in unit.blocks
            ]
        return {
            "id": unit.public_id,
            "unit_type": ContentUnitType(unit.unit_type),
            "position": unit.position,
            "title": unit.title,
            "raw_text": unit.raw_text,
            "source_page": unit.source_page,
            "blocks": blocks,
        }
