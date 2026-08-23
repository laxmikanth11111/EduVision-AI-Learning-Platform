from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import settings
from app.core.exceptions import ConflictError, ExtractionError
from app.parsers.document_parser import ExtractedBlock, ExtractedUnit
from app.services.content_extraction_service import ContentExtractionService
from shared.constants import ContentBlockType, ContentUnitType, ExtractionStatus

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_uow() -> MagicMock:
    uow = MagicMock()
    uow.session = AsyncMock()
    uow.flush = AsyncMock()
    return uow


@pytest.fixture
def extraction_service(mock_uow: MagicMock) -> ContentExtractionService:
    service = ContentExtractionService(mock_uow)
    service._repo.count_for_presentation = AsyncMock(return_value=0)
    return service


def _make_presentation(**overrides: dict) -> MagicMock:
    presentation = MagicMock()
    presentation.id = overrides.get("id", uuid.uuid4())
    presentation.public_id = overrides.get("public_id", f"pres_{uuid.uuid4().hex[:16]}")
    presentation.file_key = overrides.get("file_key", "sources/key.pdf")
    presentation.file_name = overrides.get("file_name", "slides.pdf")
    presentation.slide_count = overrides.get("slide_count", 0)
    presentation.extraction_status = overrides.get("extraction_status", ExtractionStatus.NONE.value)
    presentation.extracted_at = overrides.get("extracted_at")
    presentation.extraction_error = overrides.get("extraction_error")
    presentation.content_units = overrides.get("content_units", [])
    return presentation


def _make_unit(**overrides: dict) -> ExtractedUnit:
    return ExtractedUnit(
        unit_type=overrides.get("unit_type", ContentUnitType.SLIDE.value),
        position=overrides.get("position", 1),
        title=overrides.get("title", "Slide One"),
        raw_text=overrides.get("raw_text", "Content"),
        source_page=overrides.get("source_page", 1),
        blocks=overrides.get(
            "blocks",
            [
                ExtractedBlock(
                    block_type=ContentBlockType.PARAGRAPH.value,
                    content="Content",
                    metadata=None,
                )
            ],
        ),
    )


class TestExtractPresentation:
    async def test_success_persists_units_and_blocks(
        self, extraction_service: ContentExtractionService, mock_uow: MagicMock
    ) -> None:
        presentation = _make_presentation()
        extraction_service._presentation_repo.get_by_public_id_or_raise = AsyncMock(
            return_value=presentation
        )
        storage = MagicMock()
        storage.download_fileobj = AsyncMock(return_value=b"%PDF-1.4")
        unit_model = MagicMock()
        unit_model.id = uuid.uuid4()
        unit_model.public_id = "unit_x"
        extraction_service._repo.create = AsyncMock(return_value=unit_model)
        extraction_service._repo.delete_for_presentation = AsyncMock(return_value=0)
        extraction_service._repo.count_for_presentation = AsyncMock(return_value=1)
        units = [_make_unit()]

        with (
            patch(
                "app.services.content_extraction_service.parse_document",
                return_value=units,
            ),
            patch(
                "app.services.content_extraction_service.get_storage_backend",
                AsyncMock(return_value=storage),
            ),
        ):
            result = await extraction_service.extract_presentation(presentation.public_id)

        assert result["extraction_status"] == ExtractionStatus.READY
        assert result["units_count"] == 1
        assert presentation.extraction_status == ExtractionStatus.READY.value
        assert presentation.slide_count == 1
        assert presentation.extracted_at is not None
        extraction_service._repo.delete_for_presentation.assert_awaited_once_with(presentation.id)
        extraction_service._repo.create.assert_awaited_once()
        assert mock_uow.session.add.call_count == 1

    async def test_re_extraction_replaces_existing_content(
        self, extraction_service: ContentExtractionService, mock_uow: MagicMock
    ) -> None:
        presentation = _make_presentation(extraction_status=ExtractionStatus.READY.value)
        extraction_service._presentation_repo.get_by_public_id_or_raise = AsyncMock(
            return_value=presentation
        )
        storage = MagicMock()
        storage.download_fileobj = AsyncMock(return_value=b"data")
        unit_model = MagicMock()
        unit_model.id = uuid.uuid4()
        extraction_service._repo.create = AsyncMock(return_value=unit_model)
        extraction_service._repo.delete_for_presentation = AsyncMock(return_value=0)
        extraction_service._repo.count_for_presentation = AsyncMock(return_value=2)
        units = [_make_unit(), _make_unit(position=2, title="Slide Two")]

        with (
            patch(
                "app.services.content_extraction_service.parse_document",
                return_value=units,
            ),
            patch(
                "app.services.content_extraction_service.get_storage_backend",
                AsyncMock(return_value=storage),
            ),
        ):
            result = await extraction_service.extract_presentation(presentation.public_id)

        extraction_service._repo.delete_for_presentation.assert_awaited_once_with(presentation.id)
        assert extraction_service._repo.create.await_count == 2
        assert result["units_count"] == 2
        assert presentation.slide_count == 2

    async def test_no_source_file_conflict(
        self, extraction_service: ContentExtractionService
    ) -> None:
        presentation = _make_presentation(file_key=None)
        extraction_service._presentation_repo.get_by_public_id_or_raise = AsyncMock(
            return_value=presentation
        )

        with pytest.raises(ConflictError, match="No source file"):
            await extraction_service.extract_presentation(presentation.public_id)

    async def test_parser_failure_marks_failed(
        self, extraction_service: ContentExtractionService
    ) -> None:
        presentation = _make_presentation()
        extraction_service._presentation_repo.get_by_public_id_or_raise = AsyncMock(
            return_value=presentation
        )
        storage = MagicMock()
        storage.download_fileobj = AsyncMock(return_value=b"data")

        with (
            patch(
                "app.services.content_extraction_service.parse_document",
                side_effect=ExtractionError(message="Failed to extract content from the PDF file"),
            ),
            patch(
                "app.services.content_extraction_service.get_storage_backend",
                AsyncMock(return_value=storage),
            ),
            pytest.raises(ExtractionError, match="Failed to extract"),
        ):
            await extraction_service.extract_presentation(presentation.public_id)

        assert presentation.extraction_status == ExtractionStatus.FAILED.value
        assert presentation.extraction_error is not None
        assert presentation.extracted_at is None

    async def test_exceeds_max_units_raises(
        self, extraction_service: ContentExtractionService
    ) -> None:
        presentation = _make_presentation()
        extraction_service._presentation_repo.get_by_public_id_or_raise = AsyncMock(
            return_value=presentation
        )
        storage = MagicMock()
        storage.download_fileobj = AsyncMock(return_value=b"data")
        many_units = [_make_unit(position=i) for i in range(settings.EXTRACTION_MAX_UNITS + 1)]

        with (
            patch(
                "app.services.content_extraction_service.parse_document",
                return_value=many_units,
            ),
            patch(
                "app.services.content_extraction_service.get_storage_backend",
                AsyncMock(return_value=storage),
            ),
            pytest.raises(ExtractionError, match="exceeding the limit"),
        ):
            await extraction_service.extract_presentation(presentation.public_id)

        assert presentation.extraction_status == ExtractionStatus.FAILED.value


class TestStatusAndContent:
    async def test_get_status_serializes(
        self, extraction_service: ContentExtractionService
    ) -> None:
        presentation = _make_presentation(
            extraction_status=ExtractionStatus.READY.value,
            extracted_at=datetime.now(UTC),
        )
        result = await extraction_service.get_status(presentation)
        assert result["presentation_id"] == presentation.public_id
        assert result["extraction_status"] == ExtractionStatus.READY
        assert result["units_count"] == 0

    async def test_list_content_serializes_units_and_blocks(
        self, extraction_service: ContentExtractionService, mock_uow: MagicMock
    ) -> None:
        presentation = _make_presentation(extraction_status=ExtractionStatus.READY.value)
        unit_model = MagicMock()
        unit_model.public_id = "unit_x"
        unit_model.unit_type = ContentUnitType.SLIDE.value
        unit_model.position = 1
        unit_model.title = "Slide One"
        unit_model.raw_text = "Content"
        unit_model.source_page = 1
        block_model = MagicMock()
        block_model.public_id = "block_x"
        block_model.block_type = ContentBlockType.PARAGRAPH.value
        block_model.position = 0
        block_model.content = "Content"
        block_model.meta = None
        unit_model.blocks = [block_model]
        extraction_service._repo.list_for_presentation = AsyncMock(return_value=[unit_model])

        result = await extraction_service.list_content(presentation)

        assert result["extraction_status"] == ExtractionStatus.READY
        assert result["units"][0]["id"] == "unit_x"
        assert result["units"][0]["blocks"][0]["content"] == "Content"
        extraction_service._repo.list_for_presentation.assert_awaited_once_with(
            presentation.id, include_blocks=True
        )

    async def test_list_content_without_blocks(
        self, extraction_service: ContentExtractionService, mock_uow: MagicMock
    ) -> None:
        presentation = _make_presentation()
        unit_model = MagicMock()
        unit_model.public_id = "unit_x"
        unit_model.unit_type = ContentUnitType.SLIDE.value
        unit_model.position = 1
        unit_model.title = None
        unit_model.raw_text = None
        unit_model.source_page = None

        def _raise_on_blocks() -> None:
            raise AssertionError("unit.blocks must not be accessed when include_blocks=False")

        unit_model.blocks = MagicMock(side_effect=_raise_on_blocks)
        extraction_service._repo.list_for_presentation = AsyncMock(
            return_value=[unit_model]
        )

        result = await extraction_service.list_content(
            presentation, include_blocks=False
        )

        extraction_service._repo.list_for_presentation.assert_awaited_once_with(
            presentation.id, include_blocks=False
        )
        assert result["units"][0]["blocks"] == []
