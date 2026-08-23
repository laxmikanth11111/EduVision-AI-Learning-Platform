from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import settings
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.schemas.presentation import (
    AutosaveRequest,
    PresentationCreateRequest,
    PresentationUpdateRequest,
)
from app.services.presentation_service import PresentationService
from shared.constants import (
    PresentationAction,
    PresentationStatus,
    PresentationVisibility,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_uow() -> MagicMock:
    uow = MagicMock()
    uow.session = AsyncMock()
    uow.flush = AsyncMock()
    uow.commit = AsyncMock()
    return uow


@pytest.fixture
def presentation_service(mock_uow: MagicMock) -> PresentationService:
    service = PresentationService(mock_uow)
    service._tag_service.tag_names = AsyncMock(return_value=[])
    service._tag_service.set_tags = AsyncMock(return_value=[])
    service._tag_service.list_tags = AsyncMock(return_value=[])
    service._audit_service.log = AsyncMock(return_value=MagicMock())
    service._analytics_service.ensure_exists = AsyncMock(return_value=MagicMock())
    service._analytics_service.record_publish = AsyncMock(return_value=MagicMock())
    service._folder_service.validate_folder_ownership = AsyncMock()
    return service


def _make_presentation(**overrides: dict) -> MagicMock:
    now = datetime.now(UTC)
    presentation = MagicMock()
    presentation.id = overrides.get("id", uuid.uuid4())
    presentation.public_id = overrides.get("public_id", f"pres_{uuid.uuid4().hex[:16]}")
    presentation.title = overrides.get("title", "Test Presentation")
    presentation.description = overrides.get("description")
    presentation.status = overrides.get("status", PresentationStatus.DRAFT.value)
    presentation.topic = overrides.get("topic")
    presentation.visibility = overrides.get(
        "visibility", PresentationVisibility.PRIVATE.value
    )
    presentation.slide_count = overrides.get("slide_count", 10)
    presentation.owner_id = overrides.get("owner_id", uuid.uuid4())
    presentation.folder_id = overrides.get("folder_id")
    presentation.subject_id = overrides.get("subject_id")
    presentation.subject_confidence = overrides.get("subject_confidence")
    presentation.grade_level = overrides.get("grade_level")
    presentation.file_key = overrides.get("file_key")
    presentation.file_name = overrides.get("file_name")
    presentation.file_size = overrides.get("file_size", 0)
    presentation.mime_type = overrides.get("mime_type")
    presentation.thumbnail_key = overrides.get("thumbnail_key")
    presentation.published_at = overrides.get("published_at")
    presentation.archived_at = overrides.get("archived_at")
    presentation.created_at = overrides.get("created_at", now)
    presentation.updated_at = overrides.get("updated_at", now)
    return presentation


def _make_version(**overrides: dict) -> MagicMock:
    version = MagicMock()
    version.id = overrides.get("id", uuid.uuid4())
    version.public_id = overrides.get("public_id", f"ver_{uuid.uuid4().hex[:16]}")
    version.presentation_id = overrides.get("presentation_id", uuid.uuid4())
    version.version_number = overrides.get("version_number", 1)
    version.title = overrides.get("title", "Test Presentation")
    version.slide_count = overrides.get("slide_count", 10)
    version.diff_summary = overrides.get("diff_summary")
    version.status = overrides.get("status", PresentationStatus.PUBLISHED.value)
    version.created_by = overrides.get("created_by")
    version.created_at = overrides.get("created_at", datetime.now(UTC))
    return version


class TestCreatePresentation:
    async def test_create_success(
        self, presentation_service: PresentationService, mock_uow: MagicMock
    ) -> None:
        presentation = _make_presentation(title="New Deck")
        presentation_service._repo.create = AsyncMock(return_value=presentation)

        request = PresentationCreateRequest(title="New Deck", tags=["math", "math"])
        result = await presentation_service.create_presentation(request)

        assert result["id"] == presentation.public_id
        assert result["title"] == "New Deck"
        assert result["status"] == PresentationStatus.DRAFT
        presentation_service._analytics_service.ensure_exists.assert_awaited_once_with(
            presentation.id
        )
        presentation_service._audit_service.log.assert_awaited_once_with(
            presentation.id,
            PresentationAction.CREATED,
            details={"title": "New Deck"},
        )
        mock_uow.flush.assert_awaited_once()

    async def test_create_with_folder_validates_ownership(
        self, presentation_service: PresentationService,
    ) -> None:
        folder_id = uuid.uuid4()
        presentation = _make_presentation(folder_id=folder_id)
        presentation_service._repo.create = AsyncMock(return_value=presentation)

        request = PresentationCreateRequest(title="Deck", folder_id=folder_id)
        await presentation_service.create_presentation(request)

        presentation_service._folder_service.validate_folder_ownership.assert_awaited_once_with(
            folder_id
        )


class TestGetPresentation:
    async def test_get_presentation(
        self, presentation_service: PresentationService,
    ) -> None:
        presentation = _make_presentation()
        presentation_service._repo.get_by_public_id_or_raise = AsyncMock(
            return_value=presentation
        )
        presentation_service._tag_service.tag_names = AsyncMock(return_value=["math"])

        result = await presentation_service.get_presentation(presentation.public_id)

        assert result["title"] == "Test Presentation"
        assert result["tags"] == ["math"]

    async def test_not_found(
        self, presentation_service: PresentationService,
    ) -> None:
        presentation_service._repo.get_by_public_id_or_raise = AsyncMock(
            side_effect=NotFoundError(
                message="Presentation not found",
                details={"presentation_id": "pres_missing"},
            )
        )
        with pytest.raises(NotFoundError, match="not found"):
            await presentation_service.get_presentation("pres_missing")


class TestUpdatePresentation:
    async def test_update_success(
        self, presentation_service: PresentationService,
    ) -> None:
        presentation = _make_presentation()
        presentation_service._repo.get_by_public_id_or_raise = AsyncMock(
            return_value=presentation
        )
        updated = _make_presentation(title="Renamed")
        updated.id = presentation.id
        presentation_service._repo.update_public = AsyncMock(return_value=updated)
        presentation_service._tag_service.set_tags = AsyncMock()

        request = PresentationUpdateRequest(title="Renamed", tags=["new"])
        result = await presentation_service.update_presentation(
            presentation.public_id, request
        )

        presentation_service._repo.update_public.assert_awaited_once_with(
            presentation.public_id, title="Renamed"
        )
        presentation_service._tag_service.set_tags.assert_awaited_once_with(
            presentation.id, ["new"]
        )
        assert result["title"] == "Renamed"


class TestDeletePresentation:
    async def test_delete_success(
        self, presentation_service: PresentationService,
    ) -> None:
        presentation = _make_presentation()
        presentation_service._repo.get_by_public_id_or_raise = AsyncMock(
            return_value=presentation
        )
        presentation_service._repo.delete = AsyncMock()

        await presentation_service.delete_presentation(presentation.public_id)

        presentation_service._repo.delete.assert_awaited_once_with(presentation.id)
        presentation_service._audit_service.log.assert_awaited_once_with(
            presentation.id,
            PresentationAction.DELETED,
        )


class TestPublish:
    async def test_publish_success(
        self, presentation_service: PresentationService,
    ) -> None:
        presentation = _make_presentation(status=PresentationStatus.DRAFT.value)
        version = _make_version(presentation_id=presentation.id, version_number=1)
        presentation_service._repo.get_by_public_id_or_raise = AsyncMock(
            return_value=presentation
        )
        presentation_service._version_service.create_version = AsyncMock(return_value=version)

        result = await presentation_service.publish_presentation(presentation.public_id)

        assert presentation.status == PresentationStatus.PUBLISHED.value
        assert presentation.published_at is not None
        assert presentation.archived_at is None
        assert result["published_version"] == "v1"
        assert result["snapshot_id"] == version.public_id
        assert result["status"] == PresentationStatus.PUBLISHED
        presentation_service._version_service.create_version.assert_awaited_once_with(
            presentation,
            diff_summary="Published snapshot",
        )

    async def test_publish_already_published(
        self, presentation_service: PresentationService,
    ) -> None:
        presentation = _make_presentation(
            status=PresentationStatus.PUBLISHED.value
        )
        presentation_service._repo.get_by_public_id_or_raise = AsyncMock(
            return_value=presentation
        )
        with pytest.raises(ConflictError, match="already published"):
            await presentation_service.publish_presentation(presentation.public_id)

    async def test_publish_archived(
        self, presentation_service: PresentationService,
    ) -> None:
        presentation = _make_presentation(
            status=PresentationStatus.ARCHIVED.value
        )
        presentation_service._repo.get_by_public_id_or_raise = AsyncMock(
            return_value=presentation
        )
        with pytest.raises(ConflictError, match="cannot be published"):
            await presentation_service.publish_presentation(presentation.public_id)


class TestUnpublish:
    async def test_unpublish_success(
        self, presentation_service: PresentationService,
    ) -> None:
        presentation = _make_presentation(
            status=PresentationStatus.PUBLISHED.value
        )
        presentation_service._repo.get_by_public_id_or_raise = AsyncMock(
            return_value=presentation
        )

        result = await presentation_service.unpublish_presentation(presentation.public_id)

        assert presentation.status == PresentationStatus.DRAFT.value
        assert result["status"] == PresentationStatus.DRAFT
        assert result["unpublished_at"] is not None

    async def test_unpublish_when_not_published(
        self, presentation_service: PresentationService,
    ) -> None:
        presentation = _make_presentation()
        presentation_service._repo.get_by_public_id_or_raise = AsyncMock(
            return_value=presentation
        )
        with pytest.raises(ConflictError, match="not published"):
            await presentation_service.unpublish_presentation(presentation.public_id)


class TestArchiveRestore:
    async def test_archive_success(
        self, presentation_service: PresentationService,
    ) -> None:
        presentation = _make_presentation()
        presentation_service._repo.get_by_public_id_or_raise = AsyncMock(
            return_value=presentation
        )

        result = await presentation_service.archive_presentation(presentation.public_id)

        assert presentation.status == PresentationStatus.ARCHIVED.value
        assert presentation.archived_at is not None
        assert result["status"] == PresentationStatus.ARCHIVED

    async def test_archive_already_archived(
        self, presentation_service: PresentationService,
    ) -> None:
        presentation = _make_presentation(
            status=PresentationStatus.ARCHIVED.value
        )
        presentation_service._repo.get_by_public_id_or_raise = AsyncMock(
            return_value=presentation
        )
        with pytest.raises(ConflictError, match="already archived"):
            await presentation_service.archive_presentation(presentation.public_id)

    async def test_restore_success(
        self, presentation_service: PresentationService,
    ) -> None:
        presentation = _make_presentation(
            status=PresentationStatus.ARCHIVED.value
        )
        presentation_service._repo.get_by_public_id_or_raise = AsyncMock(
            return_value=presentation
        )

        result = await presentation_service.restore_presentation(presentation.public_id)

        assert presentation.status == PresentationStatus.DRAFT.value
        assert presentation.archived_at is None
        assert result["status"] == PresentationStatus.DRAFT

    async def test_restore_when_not_archived(
        self, presentation_service: PresentationService,
    ) -> None:
        presentation = _make_presentation()
        presentation_service._repo.get_by_public_id_or_raise = AsyncMock(
            return_value=presentation
        )
        with pytest.raises(ConflictError, match="not archived"):
            await presentation_service.restore_presentation(presentation.public_id)


class TestListPresentations:
    async def test_list_delegates_to_repository(
        self, presentation_service: PresentationService,
    ) -> None:
        presentation = _make_presentation()
        presentation_service._repo.search = AsyncMock(return_value=([presentation], 1))

        items, total = await presentation_service.list_presentations(
            q="deck",
            status="draft",
            page=2,
            page_size=10,
            sort="title",
        )

        assert total == 1
        assert items[0]["id"] == presentation.public_id
        assert items[0]["status"] == PresentationStatus.DRAFT


class TestVersions:
    async def test_list_versions(
        self, presentation_service: PresentationService,
    ) -> None:
        presentation = _make_presentation()
        presentation_service._repo.get_by_public_id_or_raise = AsyncMock(
            return_value=presentation
        )
        presentation_service._version_service.list_versions = AsyncMock(
            return_value=[{"id": "ver_1", "version": "v1"}]
        )

        versions = await presentation_service.list_versions(presentation.public_id)

        assert versions[0]["version"] == "v1"
        presentation_service._version_service.list_versions.assert_awaited_once_with(
            presentation.id
        )

    async def test_list_audit_logs(
        self, presentation_service: PresentationService,
    ) -> None:
        presentation = _make_presentation()
        presentation_service._repo.get_by_public_id_or_raise = AsyncMock(
            return_value=presentation
        )
        presentation_service._audit_service.list_logs = AsyncMock(return_value=[{}])

        logs = await presentation_service.list_audit_logs(presentation.public_id)
        assert len(logs) == 1


class TestAutosave:
    async def test_autosave_updates_fields(
        self, presentation_service: PresentationService,
    ) -> None:
        presentation = _make_presentation()
        presentation_service._repo.get_by_public_id_or_raise = AsyncMock(
            return_value=presentation
        )
        presentation_service._repo.update_public = AsyncMock(return_value=presentation)
        presentation_service._tag_service.set_tags = AsyncMock()

        request = AutosaveRequest(title="Draft title", description="Notes")
        result = await presentation_service.autosave(presentation.public_id, request)

        assert result["draft_saved"] is True
        assert result["presentation_id"] == presentation.public_id
        presentation_service._repo.update_public.assert_awaited_once_with(
            presentation.public_id, title="Draft title", description="Notes"
        )


class TestAnalytics:
    async def test_get_analytics(
        self, presentation_service: PresentationService,
    ) -> None:
        presentation = _make_presentation()
        presentation_service._repo.get_by_public_id_or_raise = AsyncMock(
            return_value=presentation
        )
        presentation_service._analytics_service.get_analytics = AsyncMock(
            return_value={"view_count": 5}
        )

        analytics = await presentation_service.get_analytics(presentation.public_id)

        assert analytics["view_count"] == 5
        presentation_service._analytics_service.get_analytics.assert_awaited_once_with(
            presentation.id
        )

    async def test_generate_thumbnail(
        self, presentation_service: PresentationService,
    ) -> None:
        presentation = _make_presentation()
        presentation_service._repo.get_by_public_id_or_raise = AsyncMock(
            return_value=presentation
        )

        key = await presentation_service.generate_thumbnail(presentation.public_id)

        assert key == f"thumbnails/{presentation.public_id}.png"
        assert presentation.thumbnail_key == key


class TestMaintenance:
    async def test_cleanup_draft_presentations(
        self, presentation_service: PresentationService, mock_uow: MagicMock
    ) -> None:
        presentation = _make_presentation()
        mock_query = MagicMock()
        mock_query.scalars.return_value.all.return_value = [presentation]
        mock_uow.session.execute = AsyncMock(return_value=mock_query)
        presentation_service._repo.delete = AsyncMock()

        count = await presentation_service.cleanup_draft_presentations(max_age_days=10)

        assert count == 1
        presentation_service._repo.delete.assert_awaited_once_with(presentation.id, hard=True)
        mock_uow.flush.assert_awaited_once()

    async def test_cleanup_archived_presentations(
        self, presentation_service: PresentationService, mock_uow: MagicMock
    ) -> None:
        presentation = _make_presentation(status=PresentationStatus.ARCHIVED.value)
        mock_query = MagicMock()
        mock_query.scalars.return_value.all.return_value = [presentation]
        mock_uow.session.execute = AsyncMock(return_value=mock_query)
        presentation_service._repo.delete = AsyncMock()

        count = await presentation_service.cleanup_archived_presentations(retention_days=20)

        assert count == 1
        presentation_service._repo.delete.assert_awaited_once_with(presentation.id, hard=True)


class TestDuplicatePresentation:
    async def test_duplicate_success(
        self, presentation_service: PresentationService,
    ) -> None:
        presentation = _make_presentation(title="Algebra Basics")
        copy = _make_presentation(
            title="Copy of Algebra Basics", status=PresentationStatus.DRAFT.value
        )
        presentation_service._repo.get_by_public_id_or_raise = AsyncMock(
            return_value=presentation
        )
        presentation_service._repo.create = AsyncMock(return_value=copy)
        presentation_service._tag_service.tag_names = AsyncMock(return_value=["math"])
        presentation_service._tag_service.set_tags = AsyncMock(return_value=[])

        result = await presentation_service.duplicate_presentation(presentation.public_id)

        assert result["id"] == copy.public_id
        assert result["status"] == PresentationStatus.DRAFT
        presentation_service._repo.create.assert_awaited_once()
        create_kwargs = presentation_service._repo.create.await_args.kwargs
        assert create_kwargs["title"] == "Copy of Algebra Basics"
        assert create_kwargs["visibility"] == PresentationVisibility.PRIVATE.value
        presentation_service._tag_service.set_tags.assert_awaited_once_with(
            copy.id, ["math"]
        )
        audit_args = presentation_service._audit_service.log.await_args.args
        assert audit_args[1] == PresentationAction.DUPLICATED


class TestRecoverPresentation:
    def _deleted_presentation(self, **overrides: dict) -> MagicMock:
        presentation = _make_presentation()
        presentation.deleted_at = overrides.get(
            "deleted_at", datetime.now(UTC) - timedelta(days=1)
        )
        presentation.restore = MagicMock()
        return presentation

    async def test_recover_within_window(
        self, presentation_service: PresentationService,
    ) -> None:
        presentation = self._deleted_presentation()
        presentation_service._repo.get_deleted_by_public_id = AsyncMock(
            return_value=presentation
        )

        result = await presentation_service.recover_presentation(presentation.public_id)

        assert result["id"] == presentation.public_id
        presentation.restore.assert_called_once()
        audit_args = presentation_service._audit_service.log.await_args.args
        assert audit_args[1] == PresentationAction.DRAFT_RECOVERED

    async def test_expired_window_conflict(
        self, presentation_service: PresentationService,
    ) -> None:
        presentation = self._deleted_presentation(
            deleted_at=datetime.now(UTC) - timedelta(days=45)
        )
        presentation_service._repo.get_deleted_by_public_id = AsyncMock(
            return_value=presentation
        )

        with pytest.raises(ConflictError, match="Recovery window"):
            await presentation_service.recover_presentation(presentation.public_id)

    async def test_not_found(
        self, presentation_service: PresentationService,
    ) -> None:
        presentation_service._repo.get_deleted_by_public_id = AsyncMock(return_value=None)

        with pytest.raises(NotFoundError, match="not found"):
            await presentation_service.recover_presentation("pres_missing")


class TestSaveVersion:
    async def test_save_version_success(
        self, presentation_service: PresentationService,
    ) -> None:
        presentation = _make_presentation()
        version = _make_version(presentation_id=presentation.id, version_number=2)
        presentation_service._repo.get_by_public_id_or_raise = AsyncMock(
            return_value=presentation
        )
        presentation_service._version_service.create_version = AsyncMock(
            return_value=version
        )

        result = await presentation_service.save_version(
            presentation.public_id, diff_summary="Added section"
        )

        assert result["version"] == "v2"
        presentation_service._version_service.create_version.assert_awaited_once_with(
            presentation,
            diff_summary="Added section",
        )
        audit_args = presentation_service._audit_service.log.await_args.args
        assert audit_args[1] == PresentationAction.VERSION_SAVED


class TestRestoreVersion:
    async def test_restore_updates_presentation(
        self, presentation_service: PresentationService,
    ) -> None:
        presentation = _make_presentation(slide_count=3)
        version = _make_version(
            presentation_id=presentation.id, version_number=1, title="Old Title", slide_count=12
        )
        restored = _make_version(
            presentation_id=presentation.id, version_number=3, title="Old Title", slide_count=12
        )
        presentation_service._repo.get_by_public_id_or_raise = AsyncMock(
            return_value=presentation
        )
        presentation_service._version_service.get_version_for_presentation = AsyncMock(
            return_value=version
        )
        presentation_service._version_service.create_version = AsyncMock(
            return_value=restored
        )

        result = await presentation_service.restore_version(
            presentation.public_id, version.public_id
        )

        assert presentation.title == "Old Title"
        assert presentation.slide_count == 12
        assert result["version"] == "v3"
        presentation_service._version_service.create_version.assert_awaited_once_with(
            presentation,
            diff_summary="Restored from v1",
        )
        audit_args = presentation_service._audit_service.log.await_args.args
        assert audit_args[1] == PresentationAction.VERSION_RESTORED

    async def test_restore_version_not_found(
        self, presentation_service: PresentationService,
    ) -> None:
        presentation = _make_presentation()
        presentation_service._repo.get_by_public_id_or_raise = AsyncMock(
            return_value=presentation
        )
        presentation_service._version_service.get_version_for_presentation = AsyncMock(
            side_effect=NotFoundError(
                message="Version not found",
                details={"version_id": "ver_missing"},
            )
        )

        with pytest.raises(NotFoundError, match="not found"):
            await presentation_service.restore_version(
                presentation.public_id, "ver_missing"
            )


class TestCompareVersions:
    async def test_compare_reports_differences(
        self, presentation_service: PresentationService,
    ) -> None:
        presentation = _make_presentation()
        from_version = _make_version(
            presentation_id=presentation.id, title="Old Title", slide_count=5
        )
        to_version = _make_version(
            presentation_id=presentation.id, title="New Title", slide_count=8
        )
        presentation_service._repo.get_by_public_id_or_raise = AsyncMock(
            return_value=presentation
        )
        presentation_service._version_service.get_version_for_presentation = AsyncMock(
            side_effect=[from_version, to_version]
        )

        result = await presentation_service.compare_versions(
            presentation.public_id, from_version.public_id, to_version.public_id
        )

        assert result["presentation_id"] == presentation.public_id
        assert "title" in result["differences"]
        assert result["differences"]["title"]["from"] == "Old Title"
        assert result["differences"]["title"]["to"] == "New Title"
        assert result["differences"]["slide_count"]["from"] == 5


class TestThumbnailManagement:
    async def test_set_thumbnail_uploads(
        self, presentation_service: PresentationService,
    ) -> None:
        presentation = _make_presentation()
        presentation_service._repo.get_by_public_id_or_raise = AsyncMock(
            return_value=presentation
        )
        storage = MagicMock()
        storage.upload_fileobj = AsyncMock(return_value="thumbnails/thumb.png")
        with patch(
            "app.services.presentation_service.get_storage_backend",
            AsyncMock(return_value=storage),
        ):
            result = await presentation_service.set_thumbnail(
                presentation.public_id, b"png-data", content_type="image/png"
            )

        assert result["thumbnail_key"] == f"thumbnails/{presentation.public_id}.png"
        assert presentation.thumbnail_key == result["thumbnail_key"]
        storage.upload_fileobj.assert_awaited_once()
        audit_args = presentation_service._audit_service.log.await_args.args
        assert audit_args[1] == PresentationAction.THUMBNAIL_UPDATED

    async def test_set_thumbnail_empty_content(
        self, presentation_service: PresentationService,
    ) -> None:
        presentation = _make_presentation()
        presentation_service._repo.get_by_public_id_or_raise = AsyncMock(
            return_value=presentation
        )

        with pytest.raises(ConflictError, match="empty"):
            await presentation_service.set_thumbnail(presentation.public_id, b"")

    async def test_set_source_uploads_and_updates_metadata(
        self, presentation_service: PresentationService,
    ) -> None:
        presentation = _make_presentation()
        presentation_service._repo.get_by_public_id_or_raise = AsyncMock(
            return_value=presentation
        )
        storage = MagicMock()
        storage.upload_fileobj = AsyncMock(return_value="sources/test-key")

        delay_mock = MagicMock()
        with patch(
            "app.workers.tasks.process_source_ingestion_task.delay",
            new=delay_mock,
        ), patch(
            "app.services.presentation_service.get_storage_backend",
            AsyncMock(return_value=storage),
        ), patch(
            "app.core.config.settings.CELERY_TASK_ALWAYS_EAGER",
            False,
        ):
            result = await presentation_service.set_source(
                presentation.public_id,
                b"pdf-content",
                filename="slides.pdf",
                content_type="application/pdf",
            )

        assert result["file_key"].startswith("sources/")
        assert result["file_name"] == "slides.pdf"
        assert result["file_size"] == len(b"pdf-content")
        assert result["mime_type"] == "application/pdf"
        storage.upload_fileobj.assert_awaited_once()
        delay_mock.assert_called_once_with(presentation.public_id)
        audit_args = presentation_service._audit_service.log.await_args.args
        assert audit_args[1] == PresentationAction.UPDATED

    async def test_set_source_rejects_invalid_extension(
        self, presentation_service: PresentationService,
    ) -> None:
        presentation = _make_presentation()
        presentation_service._repo.get_by_public_id_or_raise = AsyncMock(
            return_value=presentation
        )

        with pytest.raises(ValidationError, match="Unsupported source file extension"):
            await presentation_service.set_source(
                presentation.public_id,
                b"data",
                filename="slides.exe",
                content_type="application/octet-stream",
            )

    async def test_set_source_rejects_oversize_file(
        self, presentation_service: PresentationService,
    ) -> None:
        presentation = _make_presentation()
        presentation_service._repo.get_by_public_id_or_raise = AsyncMock(
            return_value=presentation
        )

        oversized = b"a" * (settings.UPLOAD_MAX_FILE_SIZE + 1)
        with pytest.raises(ValidationError, match="exceeds the allowed limit"):
            await presentation_service.set_source(
                presentation.public_id,
                oversized,
                filename="slides.pdf",
                content_type="application/pdf",
            )

    async def test_set_source_rejects_missing_filename(
        self, presentation_service: PresentationService,
    ) -> None:
        presentation = _make_presentation()
        presentation_service._repo.get_by_public_id_or_raise = AsyncMock(
            return_value=presentation
        )

        with pytest.raises(ValidationError, match="Source filename is required"):
            await presentation_service.set_source(
                presentation.public_id,
                b"pdf-content",
                filename="",
                content_type="application/pdf",
            )

    async def test_set_source_rejects_empty_content(
        self, presentation_service: PresentationService,
    ) -> None:
        presentation = _make_presentation()
        presentation_service._repo.get_by_public_id_or_raise = AsyncMock(
            return_value=presentation
        )

        with pytest.raises(ConflictError, match="Source content is empty"):
            await presentation_service.set_source(
                presentation.public_id,
                b"",
                filename="slides.pdf",
                content_type="application/pdf",
            )

    async def test_set_source_falls_back_to_guessed_content_type(
        self, presentation_service: PresentationService,
    ) -> None:
        presentation = _make_presentation()
        presentation_service._repo.get_by_public_id_or_raise = AsyncMock(
            return_value=presentation
        )
        storage = MagicMock()
        storage.upload_fileobj = AsyncMock(return_value="sources/test-key")

        with patch(
            "app.services.presentation_service.get_storage_backend",
            AsyncMock(return_value=storage),
        ):
            result = await presentation_service.set_source(
                presentation.public_id,
                b"pdf-content",
                filename="slides.pdf",
                content_type=None,
            )

        assert result["mime_type"] == "application/pdf"
        storage.upload_fileobj.assert_awaited_once()

    async def test_set_source_sanitizes_filename_in_storage_key(
        self, presentation_service: PresentationService,
    ) -> None:
        presentation = _make_presentation()
        presentation_service._repo.get_by_public_id_or_raise = AsyncMock(
            return_value=presentation
        )
        storage = MagicMock()
        storage.upload_fileobj = AsyncMock(return_value="sources/test-key")

        with patch(
            "app.services.presentation_service.get_storage_backend",
            AsyncMock(return_value=storage),
        ):
            await presentation_service.set_source(
                presentation.public_id,
                b"pdf-content",
                filename="../secret slides.pdf",
                content_type="application/pdf",
            )

        storage_key = storage.upload_fileobj.await_args.args[1]
        assert ".." not in storage_key
        assert "secret_slides.pdf" in storage_key

    async def test_delete_thumbnail_removes_storage_object(
        self, presentation_service: PresentationService,
    ) -> None:
        presentation = _make_presentation(thumbnail_key="thumbnails/old.png")
        presentation_service._repo.get_by_public_id_or_raise = AsyncMock(
            return_value=presentation
        )
        storage = MagicMock()
        storage.object_exists = AsyncMock(return_value=True)
        storage.delete_object = AsyncMock(return_value=None)
        with patch(
            "app.services.presentation_service.get_storage_backend",
            AsyncMock(return_value=storage),
        ):
            result = await presentation_service.delete_thumbnail(presentation.public_id)

        assert result["thumbnail_key"] is None
        assert presentation.thumbnail_key is None
        storage.delete_object.assert_awaited_once_with("thumbnails/old.png")
        audit_args = presentation_service._audit_service.log.await_args.args
        assert audit_args[1] == PresentationAction.THUMBNAIL_DELETED

    async def test_regenerate_thumbnail_schedules_task(
        self, presentation_service: PresentationService,
    ) -> None:
        presentation = _make_presentation()
        presentation_service._repo.get_by_public_id_or_raise = AsyncMock(
            return_value=presentation
        )
        task_mock = MagicMock()
        with patch(
            "app.workers.tasks.generate_thumbnail_task",
            task_mock,
        ):
            result = await presentation_service.regenerate_thumbnail(
                presentation.public_id
            )

        assert result["task_scheduled"] is True
        task_mock.delay.assert_called_once_with(presentation.public_id)
        audit_args = presentation_service._audit_service.log.await_args.args
        assert audit_args[1] == PresentationAction.THUMBNAIL_REGENERATED


class TestConcurrency:
    async def test_update_raises_conflict_on_stale_updated_at(
        self, presentation_service: PresentationService,
    ) -> None:
        presentation = _make_presentation(
            updated_at=datetime.now(UTC) - timedelta(minutes=5)
        )
        presentation_service._repo.get_by_public_id_or_raise = AsyncMock(
            return_value=presentation
        )

        request = PresentationUpdateRequest(
            title="Renamed",
            expected_updated_at=datetime.now(UTC),
        )
        with pytest.raises(ConflictError, match="modified by another editor"):
            await presentation_service.update_presentation(
                presentation.public_id, request
            )

    async def test_autosave_raises_conflict_on_stale_updated_at(
        self, presentation_service: PresentationService,
    ) -> None:
        presentation = _make_presentation(
            updated_at=datetime.now(UTC) - timedelta(minutes=1)
        )
        presentation_service._repo.get_by_public_id_or_raise = AsyncMock(
            return_value=presentation
        )

        request = AutosaveRequest(
            title="Draft",
            expected_updated_at=datetime.now(UTC),
        )
        with pytest.raises(ConflictError, match="modified by another editor"):
            await presentation_service.autosave(presentation.public_id, request)

    async def test_update_visibility_audits_change(
        self, presentation_service: PresentationService,
    ) -> None:
        presentation = _make_presentation()
        updated = _make_presentation(
            visibility=PresentationVisibility.PUBLIC.value,
        )
        updated.id = presentation.id
        presentation_service._repo.get_by_public_id_or_raise = AsyncMock(
            return_value=presentation
        )
        presentation_service._repo.update_public = AsyncMock(return_value=updated)

        request = PresentationUpdateRequest(visibility=PresentationVisibility.PUBLIC)
        result = await presentation_service.update_presentation(
            presentation.public_id, request
        )

        assert result["visibility"] == PresentationVisibility.PUBLIC
        calls = presentation_service._audit_service.log.await_args_list
        actions = [call.args[1] for call in calls]
        assert PresentationAction.VISIBILITY_CHANGED in actions

    async def test_cleanup_soft_deleted_presentations(
        self, presentation_service: PresentationService,
    ) -> None:
        deleted = _make_presentation(deleted_at=datetime.now(UTC) - timedelta(days=35))
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [deleted]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        presentation_service._uow.session.execute = AsyncMock(return_value=mock_result)
        presentation_service._repo.delete = AsyncMock()

        count = await presentation_service.cleanup_soft_deleted_presentations(retention_days=30)

        assert count == 1
        presentation_service._repo.delete.assert_awaited_once_with(deleted.id, hard=True)


class TestVersionConcurrency:
    async def test_create_version_raises_conflict_error_on_persistent_integrity_error(
        self, presentation_service: PresentationService,
    ) -> None:
        from sqlalchemy.exc import IntegrityError
        presentation = _make_presentation()
        version_service = presentation_service._version_service
        version_service._repo.next_version_number = AsyncMock(return_value=2)
        version_service._repo.create = AsyncMock(return_value=MagicMock())
        version_service._uow.flush = AsyncMock(side_effect=IntegrityError("stmt", {}, Exception("unique")))
        version_service._uow.session.rollback = AsyncMock()

        with pytest.raises(ConflictError, match="Concurrent version creation conflict"):
            await version_service.create_version(presentation, max_retries=2)

        assert version_service._uow.session.rollback.await_count == 2


class TestCeleryBeatSchedule:
    async def test_beat_schedule_contains_all_tasks(self) -> None:
        from app.workers.celery_app import celery_app

        schedule = celery_app.conf.beat_schedule
        assert "health-check" in schedule
        assert "aggregate-analytics-hourly" in schedule
        assert "cleanup-drafts-daily" in schedule
        assert "cleanup-archived-daily" in schedule
        assert "cleanup-soft-deleted-daily" in schedule
        assert schedule["cleanup-drafts-daily"]["kwargs"]["max_age_days"] == 30
        assert schedule["cleanup-archived-daily"]["kwargs"]["retention_days"] == 30
        assert schedule["cleanup-soft-deleted-daily"]["kwargs"]["retention_days"] == 30


class TestSourceIngestionRAGDispatch:
    async def test_rag_index_dispatched_without_name_error(
        self, presentation_service: PresentationService,
    ) -> None:
        from app.workers.rag_tasks import rag_indexing_task

        fake_uow = MagicMock()
        fake_uow.__aenter__ = AsyncMock(return_value=MagicMock())
        fake_uow.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "app.services.presentation_service.UnitOfWork",
                return_value=fake_uow,
            ),
            patch(
                "app.services.content_extraction_service.ContentExtractionService"
            ) as mock_ext,
            patch.object(settings, "RAG_INDEXING_ENABLED", True),
            patch("app.workers.tasks.safe_dispatch") as mock_dispatch,
        ):
            mock_ext.return_value.extract_presentation = AsyncMock(
                return_value={"presentation_id": "pres_x"}
            )
            result = await presentation_service.start_source_ingestion("pres_x")

        assert result == "pres_x"
        mock_dispatch.assert_called_once_with(
            rag_indexing_task, "presentation", "pres_x"
        )
