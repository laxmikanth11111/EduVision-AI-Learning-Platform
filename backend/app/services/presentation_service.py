from __future__ import annotations

import asyncio
import io
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from app.core.config import settings
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.database.unit_of_work import UnitOfWork
from app.models.content_block import ContentBlock
from app.models.content_unit import ContentUnit
from app.models.presentation import Presentation
from app.models.topic_outline import TopicOutline
from app.repositories.presentation_repository import PresentationRepository
from app.schemas.generated_lesson import LessonGenerationRequest
from app.schemas.presentation import (
    AutosaveRequest,
    PresentationCreateRequest,
    PresentationManualRequest,
    PresentationUpdateRequest,
)
from app.services.presentation_analytics_service import PresentationAnalyticsService
from app.services.presentation_audit_service import PresentationAuditService
from app.services.presentation_folder_service import PresentationFolderService
from app.services.presentation_tag_service import PresentationTagService
from app.services.presentation_version_service import PresentationVersionService
from app.storage.factory import get_storage_backend
from app.utils.file_helpers import (
    SUPPORTED_DOCUMENT_EXTENSIONS,
    get_content_type,
    get_file_extension,
    is_document_extension_allowed,
    is_within_size_limit,
    safe_filename,
    validate_magic_bytes,
)
from shared.constants import (
    PresentationAction,
    PresentationStatus,
    PresentationVisibility,
)

logger = get_logger(__name__)

DRAFT_RECOVERY_WINDOW_DAYS = 30

_background_tasks: set[asyncio.Task[Any]] = set()


def _spawn_background(coro: Any) -> None:
    """Run a coroutine on the event loop while keeping a strong reference.

    The event loop only holds weak references to tasks; without this set a
    fire-and-forget task can be garbage-collected before it completes.
    Exceptions are logged, never swallowed.
    """

    def _done(task: asyncio.Task[Any]) -> None:
        _background_tasks.discard(task)
        if not task.cancelled() and task.exception() is not None:
            logger.error(
                "background_task_failed",
                error=f"{type(task.exception()).__name__}: {task.exception()}",
            )

    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_done)


class PresentationService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow
        self._repo = PresentationRepository(uow.session)
        self._folder_service = PresentationFolderService(uow)
        self._version_service = PresentationVersionService(uow)
        self._analytics_service = PresentationAnalyticsService(uow)
        self._tag_service = PresentationTagService(uow)
        self._audit_service = PresentationAuditService(uow)

    async def _get_presentation(self, public_id: str) -> Presentation:
        return await self._repo.get_by_public_id_or_raise(public_id)

    async def assert_ownership(self, public_id: str, owner_id: uuid.UUID) -> Presentation:
        """Return presentation if it belongs to *owner_id*, else raise 404."""
        presentation = await self._get_presentation(public_id)
        if presentation.owner_id is not None and str(presentation.owner_id) != str(owner_id):
            raise NotFoundError(
                message="Presentation not found",
                details={"presentation_id": public_id},
            )
        return presentation

    @staticmethod
    def _same_moment(left: datetime, right: datetime) -> bool:
        if left is None or right is None:
            return left is right
        if left.tzinfo is not None and right.tzinfo is not None:
            return left.astimezone(UTC) == right.astimezone(UTC)
        return left.replace(tzinfo=None) == right.replace(tzinfo=None)

    @staticmethod
    def _assert_updated_at_matches(
        presentation: Presentation,
        expected_updated_at: datetime | None,
    ) -> None:
        if expected_updated_at is None:
            return
        if not PresentationService._same_moment(presentation.updated_at, expected_updated_at):
            raise ConflictError(
                message=(
                    "This presentation was modified by another editor. "
                    "Reload the latest version and try again."
                ),
                details={
                    "current_updated_at": presentation.updated_at,
                    "expected_updated_at": expected_updated_at,
                },
            )

    # ── Serialization ───────────────────────────────────────────────────────────

    async def _serialize(self, presentation: Presentation) -> dict[str, Any]:
        tags = await self._tag_service.tag_names(presentation.id)
        return {
            "id": presentation.public_id,
            "title": presentation.title,
            "description": presentation.description,
            "status": PresentationStatus(presentation.status),
            "topic": presentation.topic,
            "visibility": PresentationVisibility(presentation.visibility),
            "slide_count": presentation.slide_count,
            "owner_id": str(presentation.owner_id),
            "folder_id": presentation.folder_id,
            "subject_id": presentation.subject_id,
            "subject_confidence": presentation.subject_confidence,
            "grade_level": presentation.grade_level,
            "file_key": presentation.file_key,
            "file_name": presentation.file_name,
            "file_size": presentation.file_size,
            "mime_type": presentation.mime_type,
            "source_status": ("uploaded" if presentation.file_key else "pending"),
            "extraction_status": (presentation.extraction_status or "none"),
            "thumbnail_key": presentation.thumbnail_key,
            "tags": tags,
            "published_at": presentation.published_at,
            "archived_at": presentation.archived_at,
            "created_at": presentation.created_at,
            "updated_at": presentation.updated_at,
        }

    def _serialize_summary(self, presentation: Presentation) -> dict[str, Any]:
        return {
            "id": presentation.public_id,
            "title": presentation.title,
            "status": PresentationStatus(presentation.status),
            "topic": presentation.topic,
            "slide_count": presentation.slide_count,
            "subject_id": presentation.subject_id,
            "subject_confidence": presentation.subject_confidence,
            "grade_level": presentation.grade_level,
            "file_size": presentation.file_size,
            "thumbnail_key": presentation.thumbnail_key,
            "extraction_status": (presentation.extraction_status or "none"),
            "created_at": presentation.created_at,
            "updated_at": presentation.updated_at,
            "published_at": presentation.published_at,
        }

    # ── Core operations ─────────────────────────────────────────────────────────

    async def create_presentation(
        self,
        request: PresentationCreateRequest,
        owner_id: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        if request.folder_id is not None:
            await self._folder_service.validate_folder_ownership(request.folder_id)

        presentation = await self._repo.create(
            title=request.title,
            description=request.description,
            topic=request.topic,
            visibility=request.visibility.value,
            folder_id=request.folder_id,
            file_key=request.file_key,
            file_name=request.file_name,
            subject_id=request.subject_id,
            grade_level=request.grade_level,
            owner_id=owner_id,
        )
        if request.tags:
            await self._tag_service.set_tags(presentation.id, request.tags)
        await self._analytics_service.ensure_exists(presentation.id)
        await self._audit_service.log(
            presentation.id,
            PresentationAction.CREATED,
            details={"title": request.title},
        )
        await self._uow.flush()
        logger.info("presentation_created", presentation_id=presentation.public_id)
        return await self._serialize(presentation)

    async def create_manual_presentation(
        self,
        request: PresentationManualRequest,
        owner_id: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        if request.folder_id is not None:
            await self._folder_service.validate_folder_ownership(request.folder_id)

        presentation = await self._repo.create(
            title=request.title,
            description=request.description,
            topic=request.title,
            visibility=request.visibility.value,
            folder_id=request.folder_id,
            subject_id=request.subject_id,
            grade_level=request.grade_level,
            owner_id=owner_id,
            extraction_status="ready",
            slide_count=len(request.topics),
        )
        if request.tags:
            await self._tag_service.set_tags(presentation.id, request.tags)
        await self._analytics_service.ensure_exists(presentation.id)

        for position, topic_title in enumerate(request.topics):
            unit = ContentUnit(
                presentation_id=presentation.id,
                unit_type="section",
                position=position,
                title=topic_title,
                raw_text=topic_title,
            )
            self._uow.session.add(unit)
            await self._uow.flush()

            block = ContentBlock(
                content_unit_id=unit.id,
                block_type="heading",
                position=0,
                content=topic_title,
            )
            self._uow.session.add(block)

        outline_topics = [
            {"title": t, "slide_ranges": [i + 1, i + 1]}
            for i, t in enumerate(request.topics)
        ]
        outline = TopicOutline(
            presentation_id=presentation.id,
            title=request.title,
            topics=outline_topics,
            status="succeeded",
        )
        self._uow.session.add(outline)

        await self._audit_service.log(
            presentation.id,
            PresentationAction.CREATED,
            details={"title": request.title, "manual_topics": len(request.topics)},
        )
        await self._uow.flush()

        from app.schemas.generated_lesson import LessonGenerationRequest
        from shared.constants import LearningMode

        await self.generate_lesson(
            presentation.public_id,
            LessonGenerationRequest(mode=LearningMode.SLIDE, title=request.title),
        )

        logger.info(
            "manual_presentation_created",
            presentation_id=presentation.public_id,
            topic_count=len(request.topics),
        )
        return await self._serialize(presentation)

    async def get_presentation(self, public_id: str) -> dict[str, Any]:
        presentation = await self._get_presentation(public_id)
        return await self._serialize(presentation)

    async def update_presentation(
        self,
        public_id: str,
        request: PresentationUpdateRequest,
    ) -> dict[str, Any]:
        presentation = await self._get_presentation(public_id)
        self._assert_updated_at_matches(presentation, request.expected_updated_at)

        if request.folder_id is not None:
            await self._folder_service.validate_folder_ownership(request.folder_id)

        update_data: dict[str, Any] = {}
        if request.title is not None:
            update_data["title"] = request.title
        if request.description is not None:
            update_data["description"] = request.description
        if request.topic is not None:
            update_data["topic"] = request.topic
        if request.visibility is not None:
            update_data["visibility"] = request.visibility.value
        if request.subject_id is not None:
            update_data["subject_id"] = request.subject_id
        if request.grade_level is not None:
            update_data["grade_level"] = request.grade_level
        if request.folder_id is not None:
            update_data["folder_id"] = request.folder_id

        if update_data:
            presentation = await self._repo.update_public(public_id, **update_data)

        if request.tags is not None:
            await self._tag_service.set_tags(presentation.id, request.tags)

        await self._audit_service.log(
            presentation.id,
            PresentationAction.UPDATED,
            details={key: str(value) for key, value in update_data.items()},
        )
        if request.visibility is not None:
            await self._audit_service.log(
                presentation.id,
                PresentationAction.VISIBILITY_CHANGED,
                details={
                    "visibility": request.visibility.value,
                    "expected_updated_at": request.expected_updated_at,
                },
            )
        await self._uow.flush()
        logger.info("presentation_updated", presentation_id=public_id)
        return await self._serialize(presentation)

    async def delete_presentation(self, public_id: str) -> None:
        presentation = await self._get_presentation(public_id)
        await self._repo.delete(presentation.id)
        await self._audit_service.log(
            presentation.id,
            PresentationAction.DELETED,
        )
        await self._uow.flush()
        logger.info("presentation_deleted", presentation_id=public_id)

    async def publish_presentation(self, public_id: str) -> dict[str, Any]:
        presentation = await self._get_presentation(public_id)

        if presentation.status == PresentationStatus.PUBLISHED.value:
            raise ConflictError(message="Presentation is already published")
        if presentation.status == PresentationStatus.ARCHIVED.value:
            raise ConflictError(message="Archived presentations cannot be published")

        presentation.status = PresentationStatus.PUBLISHED.value
        presentation.published_at = datetime.now(UTC)
        presentation.archived_at = None

        version = await self._version_service.create_version(
            presentation,
            diff_summary="Published snapshot",
        )
        await self._analytics_service.record_publish(presentation.id)
        await self._audit_service.log(
            presentation.id,
            PresentationAction.PUBLISHED,
            details={"version": version.public_id},
        )
        await self._uow.flush()
        logger.info("presentation_published", presentation_id=public_id)
        return {
            "presentation_id": presentation.public_id,
            "status": PresentationStatus.PUBLISHED,
            "published_version": f"v{version.version_number}",
            "published_at": presentation.published_at,
            "snapshot_id": version.public_id,
        }

    async def unpublish_presentation(self, public_id: str) -> dict[str, Any]:
        presentation = await self._get_presentation(public_id)

        if presentation.status != PresentationStatus.PUBLISHED.value:
            raise ConflictError(message="Presentation is not published")

        presentation.status = PresentationStatus.DRAFT.value
        unpublished_at = datetime.now(UTC)
        await self._audit_service.log(
            presentation.id,
            PresentationAction.UNPUBLISHED,
        )
        await self._uow.flush()
        logger.info("presentation_unpublished", presentation_id=public_id)
        return {
            "presentation_id": presentation.public_id,
            "status": PresentationStatus.DRAFT,
            "unpublished_at": unpublished_at,
        }

    async def archive_presentation(self, public_id: str) -> dict[str, Any]:
        presentation = await self._get_presentation(public_id)

        if presentation.status == PresentationStatus.ARCHIVED.value:
            raise ConflictError(message="Presentation is already archived")

        presentation.status = PresentationStatus.ARCHIVED.value
        presentation.archived_at = datetime.now(UTC)
        await self._audit_service.log(
            presentation.id,
            PresentationAction.ARCHIVED,
        )
        await self._uow.flush()
        return await self._serialize(presentation)

    async def restore_presentation(self, public_id: str) -> dict[str, Any]:
        presentation = await self._get_presentation(public_id)

        if presentation.status != PresentationStatus.ARCHIVED.value:
            raise ConflictError(message="Presentation is not archived")

        presentation.status = PresentationStatus.DRAFT.value
        presentation.archived_at = None
        await self._audit_service.log(
            presentation.id,
            PresentationAction.RESTORED,
        )
        await self._uow.flush()
        return await self._serialize(presentation)

    async def duplicate_presentation(
        self,
        public_id: str,
        owner_id: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        presentation = await self._get_presentation(public_id)

        copy_title = f"Copy of {presentation.title}"[:300]
        copy = await self._repo.create(
            title=copy_title,
            description=presentation.description,
            topic=presentation.topic,
            visibility=PresentationVisibility.PRIVATE.value,
            folder_id=presentation.folder_id,
            subject_id=presentation.subject_id,
            grade_level=presentation.grade_level,
            status=PresentationStatus.DRAFT.value,
            owner_id=owner_id,
        )
        tag_names = await self._tag_service.tag_names(presentation.id)
        if tag_names:
            await self._tag_service.set_tags(copy.id, tag_names)
        await self._analytics_service.ensure_exists(copy.id)
        await self._audit_service.log(
            copy.id,
            PresentationAction.DUPLICATED,
            details={"source_id": presentation.public_id},
        )
        await self._uow.flush()
        logger.info(
            "presentation_duplicated",
            source_id=presentation.public_id,
            copy_id=copy.public_id,
        )
        return await self._serialize(copy)

    async def recover_presentation(
        self,
        public_id: str,
    ) -> dict[str, Any]:
        presentation = await self._repo.get_deleted_by_public_id(public_id)
        if presentation is None:
            raise NotFoundError(
                message="Deleted presentation not found",
                details={"presentation_id": public_id},
            )

        if presentation.deleted_at is None:
            raise ConflictError(message="Presentation is not deleted")

        cutoff = datetime.now(UTC) - timedelta(days=DRAFT_RECOVERY_WINDOW_DAYS)
        deleted_at = presentation.deleted_at
        if deleted_at.tzinfo is not None:
            deleted_at = deleted_at.astimezone(UTC)
        if deleted_at < cutoff:
            raise ConflictError(
                message=(
                    f"Recovery window of {DRAFT_RECOVERY_WINDOW_DAYS} days has expired. "
                    "This presentation can no longer be recovered."
                ),
                details={"recovery_window_days": DRAFT_RECOVERY_WINDOW_DAYS},
            )

        presentation.restore()
        await self._audit_service.log(
            presentation.id,
            PresentationAction.DRAFT_RECOVERED,
        )
        await self._uow.flush()
        logger.info("presentation_recovered", presentation_id=public_id)
        return await self._serialize(presentation)

    async def save_version(
        self,
        public_id: str,
        diff_summary: str | None = None,
    ) -> dict[str, Any]:
        presentation = await self._get_presentation(public_id)

        version = await self._version_service.create_version(
            presentation,
            diff_summary=diff_summary,
        )
        await self._audit_service.log(
            presentation.id,
            PresentationAction.VERSION_SAVED,
            details={
                "version": version.public_id,
                "version_number": version.version_number,
                "diff_summary": diff_summary,
            },
        )
        await self._uow.flush()
        logger.info(
            "presentation_version_saved",
            presentation_id=public_id,
            version_number=version.version_number,
        )
        return self._version_service._serialize(version)

    async def restore_version(
        self,
        public_id: str,
        version_id: str,
    ) -> dict[str, Any]:
        presentation = await self._get_presentation(public_id)

        version = await self._version_service.get_version_for_presentation(
            presentation.id, version_id
        )
        restored = await self._version_service.create_version(
            presentation,
            diff_summary=f"Restored from v{version.version_number}",
        )
        presentation.title = version.title
        presentation.slide_count = version.slide_count

        await self._audit_service.log(
            presentation.id,
            PresentationAction.VERSION_RESTORED,
            details={
                "from_version": version.public_id,
                "from_version_number": version.version_number,
                "to_version": restored.public_id,
                "to_version_number": restored.version_number,
            },
        )
        await self._uow.flush()
        logger.info(
            "presentation_version_restored",
            presentation_id=public_id,
            version_id=version_id,
        )
        return self._version_service._serialize(restored)

    async def compare_versions(
        self,
        public_id: str,
        from_version_id: str,
        to_version_id: str,
    ) -> dict[str, Any]:
        presentation = await self._get_presentation(public_id)

        from_version = await self._version_service.get_version_for_presentation(
            presentation.id, from_version_id
        )
        to_version = await self._version_service.get_version_for_presentation(
            presentation.id, to_version_id
        )
        return {
            "presentation_id": presentation.public_id,
            **self._version_service.compare(from_version, to_version),
        }

    # ── Thumbnail management ───────────────────────────────────────────────────

    async def set_thumbnail(
        self,
        public_id: str,
        content: bytes,
        content_type: str | None = None,
        filename: str | None = None,
    ) -> dict[str, Any]:
        presentation = await self._get_presentation(public_id)

        if not content:
            raise ConflictError(message="Thumbnail content is empty")

        extension = self._thumbnail_extension(filename, content_type)
        if not validate_magic_bytes(content[:512], f"thumbnail{extension}"):
            raise ValidationError(
                message="Thumbnail content does not match its file type",
                details={
                    "extension": extension,
                    "content_type": content_type,
                },
            )
        key = f"thumbnails/{presentation.public_id}{extension}"
        storage = await get_storage_backend()
        await storage.upload_fileobj(
            io.BytesIO(content),
            key,
            content_type=content_type or "image/png",
        )
        try:
            presentation.thumbnail_key = key
            await self._audit_service.log(
                presentation.id,
                PresentationAction.THUMBNAIL_UPDATED,
                details={"thumbnail_key": key},
            )
            await self._uow.flush()
        except Exception:
            await self._storage_delete_best_effort(storage, key)
            raise
        logger.info("presentation_thumbnail_uploaded", presentation_id=public_id)
        return {"presentation_id": presentation.public_id, "thumbnail_key": key}

    async def set_source(
        self,
        public_id: str,
        content: bytes,
        filename: str,
        content_type: str | None = None,
    ) -> dict[str, Any]:
        presentation = await self._get_presentation(public_id)

        if not filename:
            raise ValidationError(message="Source filename is required")

        if not is_document_extension_allowed(filename):
            raise ValidationError(
                message="Unsupported source file extension",
                details={
                    "allowed_extensions": sorted(SUPPORTED_DOCUMENT_EXTENSIONS),
                },
            )

        if not content:
            raise ConflictError(message="Source content is empty")

        if not is_within_size_limit(len(content)):
            raise ValidationError(
                message="Source file size exceeds the allowed limit",
                details={
                    "max_size": settings.UPLOAD_MAX_FILE_SIZE,
                    "actual_size": len(content),
                },
            )

        if not validate_magic_bytes(content[:512], filename):
            raise ValidationError(
                message="Source file content does not match its file extension",
                details={
                    "filename": filename,
                    "extension": get_file_extension(filename),
                },
            )

        content_type = content_type or get_content_type(filename)
        key = f"sources/{presentation.public_id}/{uuid.uuid4().hex}_{safe_filename(filename)}"
        storage = await get_storage_backend()
        await storage.upload_fileobj(
            io.BytesIO(content),
            key,
            content_type=content_type,
        )

        try:
            presentation.file_key = key
            presentation.file_name = filename
            presentation.file_size = len(content)
            presentation.mime_type = content_type

            await self._audit_service.log(
                presentation.id,
                PresentationAction.UPDATED,
                details={
                    "file_key": key,
                    "file_name": filename,
                    "file_size": presentation.file_size,
                },
            )
            await self._uow.flush()
            await self._uow.session.refresh(presentation)

            # Commit before dispatch in every mode: a worker session must never
            # read a transaction the request hasn't committed yet, or it races the
            # commit and fails with stale/absent state ("No source file has been
            # uploaded"). Eager mode runs the task on the same loop, so it acquires
            # the fresh state only after this commit as well.
            await self._uow.commit()
        except Exception:
            # The upload already hit object storage but the DB write rolled
            # back; remove the orphaned object so no unreferenced file leaks.
            await self._storage_delete_best_effort(storage, key)
            raise

        if settings.CELERY_TASK_ALWAYS_EAGER:
            _spawn_background(self.start_source_ingestion(public_id))
        else:
            import app.workers.tasks as worker_tasks
            worker_tasks.safe_dispatch(worker_tasks.process_source_ingestion_task, public_id)

        logger.info("presentation_source_uploaded", presentation_id=public_id)
        return await self._serialize(presentation)

    async def start_source_ingestion(self, public_id: str) -> str:
        from app.services.content_extraction_service import ContentExtractionService

        async with UnitOfWork() as uow:
            result = await ContentExtractionService(uow).extract_presentation(public_id)
            presentation_id = str(result["presentation_id"])

        try:
            from app.schemas.generated_lesson import LessonGenerationRequest
            from shared.constants import LearningMode

            async with UnitOfWork() as uow:
                await PresentationService(uow).generate_lesson(
                    public_id,
                    LessonGenerationRequest(mode=LearningMode.SLIDE, title="Auto-generated lesson"),
                )
        except Exception as e:
            logger.error(
                "auto_lesson_generation_failed",
                presentation_id=public_id,
                error=str(e),
            )

        if settings.RAG_INDEXING_ENABLED:
            from app.workers.rag_tasks import rag_indexing_task
            from app.workers.tasks import safe_dispatch

            safe_dispatch(rag_indexing_task, "presentation", public_id)
            logger.info(
                "rag_indexing_dispatched",
                scope="presentation",
                entity_id=public_id,
            )
        return presentation_id

    async def get_extraction_status(
        self,
        public_id: str,
    ) -> dict[str, Any]:
        from app.services.content_extraction_service import ContentExtractionService

        presentation = await self._get_presentation(public_id)
        return await ContentExtractionService(self._uow).get_status(presentation)

    async def get_content(
        self,
        public_id: str,
        include_blocks: bool = True,
    ) -> dict[str, Any]:
        from app.services.content_extraction_service import ContentExtractionService

        presentation = await self._get_presentation(public_id)
        return await ContentExtractionService(self._uow).list_content(
            presentation,
            include_blocks=include_blocks,
        )

    # ── Topic outline ─────────────────────────────────────────────────────────

    async def get_topics(
        self,
        public_id: str,
    ) -> dict[str, Any]:
        from app.services.topic_outline_service import TopicOutlineService

        presentation = await self._get_presentation(public_id)
        return await TopicOutlineService(self._uow).get_outline_data(presentation)

    async def regenerate_topics(
        self,
        public_id: str,
    ) -> dict[str, Any]:
        from app.services.topic_outline_service import TopicOutlineService

        presentation = await self._get_presentation(public_id)
        return await TopicOutlineService(self._uow).regenerate(presentation)

    # ── AI lesson generation ──────────────────────────────────────────────────

    async def generate_lesson(
        self,
        public_id: str,
        request: LessonGenerationRequest,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        from app.services.lesson_generation_service import LessonGenerationService

        presentation = await self._get_presentation(public_id)
        result = await LessonGenerationService(self._uow).create_lesson(
            presentation,
            request,
            idempotency_key=idempotency_key,
        )
        if not result.get("duplicate"):
            # Persist the QUEUED lesson before dispatch so the worker never
            # observes an uncommitted transaction (same ordering guarantee as
            # upload_source above).
            await self._uow.commit()
            if settings.CELERY_TASK_ALWAYS_EAGER:
                # Eager mode: run generation directly on the server loop (same
                # pattern as start_source_ingestion). Going through the Celery
                # task here would execute it inline on a foreign event loop
                # before the creating transaction commits.
                _spawn_background(self._run_lesson_generation_eager(result["id"]))
            else:
                from app.workers.tasks import lesson_generation_task, safe_dispatch

                safe_dispatch(lesson_generation_task, result["id"])
        return result

    async def _run_lesson_generation_eager(self, lesson_public_id: str) -> None:
        """Eager-mode stand-in for the ``eduvision.lessons.generate`` task."""
        from app.services.lesson_generation_service import LessonGenerationService

        try:
            async with UnitOfWork() as uow:
                await LessonGenerationService(uow).run_generation(lesson_public_id)
            logger.info("eager_lesson_generation_completed", lesson_id=lesson_public_id)
        except Exception as exc:
            logger.error(
                "eager_lesson_generation_failed",
                lesson_id=lesson_public_id,
                error=str(exc),
            )

    async def list_generated_lessons(
        self,
        public_id: str,
        *,
        page: int,
        page_size: int,
        mode: str | None,
        status: str | None,
    ) -> tuple[list[dict[str, Any]], int]:
        from app.services.lesson_generation_service import LessonGenerationService

        presentation = await self._get_presentation(public_id)
        return await LessonGenerationService(self._uow).list_lessons(
            presentation,
            page=page,
            page_size=page_size,
            mode=mode,
            status=status,
        )

    async def get_generated_lesson(
        self,
        public_id: str,
        lesson_id: str,
    ) -> dict[str, Any]:
        from app.services.lesson_generation_service import LessonGenerationService

        presentation = await self._get_presentation(public_id)
        return await LessonGenerationService(self._uow).get_lesson(presentation, lesson_id)

    async def get_generated_lesson_status(
        self,
        public_id: str,
        lesson_id: str,
    ) -> dict[str, Any]:
        from app.services.lesson_generation_service import LessonGenerationService

        presentation = await self._get_presentation(public_id)
        return await LessonGenerationService(self._uow).get_status(presentation, lesson_id)

    async def list_generated_lesson_versions(
        self,
        public_id: str,
        lesson_id: str,
    ) -> list[dict[str, Any]]:
        from app.services.lesson_generation_service import LessonGenerationService

        presentation = await self._get_presentation(public_id)
        return await LessonGenerationService(self._uow).list_versions(presentation, lesson_id)

    async def get_generated_lesson_version(
        self,
        public_id: str,
        lesson_id: str,
        version_id: str,
    ) -> dict[str, Any]:
        from app.services.lesson_generation_service import LessonGenerationService

        presentation = await self._get_presentation(public_id)
        return await LessonGenerationService(self._uow).get_version(
            presentation, lesson_id, version_id
        )

    async def delete_generated_lesson(
        self,
        public_id: str,
        lesson_id: str,
    ) -> None:
        from app.services.lesson_generation_service import LessonGenerationService

        presentation = await self._get_presentation(public_id)
        await LessonGenerationService(self._uow).delete_lesson(presentation, lesson_id)

    async def delete_thumbnail(
        self,
        public_id: str,
    ) -> dict[str, Any]:
        presentation = await self._get_presentation(public_id)

        if presentation.thumbnail_key:
            try:
                storage = await get_storage_backend()
                if await storage.object_exists(presentation.thumbnail_key):
                    await storage.delete_object(presentation.thumbnail_key)
            except Exception:
                logger.exception(
                    "thumbnail_delete_storage_failed",
                    presentation_id=public_id,
                    key=presentation.thumbnail_key,
                )
        presentation.thumbnail_key = None
        await self._audit_service.log(
            presentation.id,
            PresentationAction.THUMBNAIL_DELETED,
        )
        await self._uow.flush()
        logger.info("presentation_thumbnail_deleted", presentation_id=public_id)
        return {"presentation_id": presentation.public_id, "thumbnail_key": None}

    async def regenerate_thumbnail(
        self,
        public_id: str,
    ) -> dict[str, Any]:
        presentation = await self._get_presentation(public_id)

        from app.workers.tasks import generate_thumbnail_task, safe_dispatch

        safe_dispatch(generate_thumbnail_task, public_id)
        await self._audit_service.log(
            presentation.id,
            PresentationAction.THUMBNAIL_REGENERATED,
        )
        await self._uow.flush()
        logger.info("presentation_thumbnail_regeneration_scheduled", presentation_id=public_id)
        return {"presentation_id": presentation.public_id, "task_scheduled": True}

    @staticmethod
    async def _storage_delete_best_effort(storage: object, key: str) -> None:
        """Remove a freshly-uploaded object when the DB write rolled back.

        Keeps storage and the database consistent: an object uploaded before a
        failed flush/commit has no database reference and would otherwise be
        orphaned. Best-effort by design so a storage hiccup never masks the
        original database error.
        """
        try:
            await storage.delete_object(key)
        except Exception:
            logger.exception(
                "storage_cleanup_after_db_failure_failed",
                key=key,
            )

    @staticmethod
    def _thumbnail_extension(
        filename: str | None,
        content_type: str | None,
    ) -> str:
        if filename and "." in filename:
            ext = filename.rsplit(".", 1)[-1].lower()
            if len(ext) <= 5 and ext.isalnum():
                return f".{ext}"
        if content_type == "image/jpeg":
            return ".jpg"
        return ".png"

    # ── Learning sessions / views ──────────────────────────────────────────────

    async def record_learning_session(
        self,
        public_id: str,
    ) -> dict[str, Any]:
        presentation = await self._get_presentation(public_id)

        analytics = await self._analytics_service.record_learning_session(presentation.id)
        await self._audit_service.log(
            presentation.id,
            PresentationAction.LEARNING_SESSION_STARTED,
        )
        return {
            "presentation_id": presentation.public_id,
            "session_started_at": datetime.now(UTC),
            "learning_sessions": analytics.learning_sessions,
        }

    # ── Listing / search ────────────────────────────────────────────────────────

    async def list_presentations(
        self,
        *,
        owner_id: uuid.UUID | None = None,
        q: str | None = None,
        status: str | None = None,
        subject_id: str | None = None,
        grade_level: str | None = None,
        folder_id: uuid.UUID | None = None,
        tag: str | None = None,
        topic: str | None = None,
        visibility: str | None = None,
        page: int = 1,
        page_size: int = 25,
        sort: str = "updated_at",
        descending: bool = True,
    ) -> tuple[list[dict[str, Any]], int]:
        items, total = await self._repo.search(
            user_id=owner_id,
            q=q,
            status=status,
            subject_id=subject_id,
            grade_level=grade_level,
            folder_id=folder_id,
            tag=tag,
            topic=topic,
            visibility=visibility,
            page=page,
            page_size=page_size,
            sort=sort,
            descending=descending,
        )
        return [self._serialize_summary(item) for item in items], total

    async def list_versions(
        self,
        public_id: str,
    ) -> list[dict[str, Any]]:
        presentation = await self._get_presentation(public_id)
        return await self._version_service.list_versions(presentation.id)

    async def list_audit_logs(
        self,
        public_id: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        presentation = await self._get_presentation(public_id)
        return await self._audit_service.list_logs(presentation.id, limit=limit)

    # ── Drafts / autosave ───────────────────────────────────────────────────────

    async def autosave(
        self,
        public_id: str,
        request: AutosaveRequest,
    ) -> dict[str, Any]:
        presentation = await self._get_presentation(public_id)
        self._assert_updated_at_matches(presentation, request.expected_updated_at)

        update_data: dict[str, Any] = {}
        if request.title is not None:
            update_data["title"] = request.title
        if request.description is not None:
            update_data["description"] = request.description
        if request.topic is not None:
            update_data["topic"] = request.topic
        if update_data:
            presentation = await self._repo.update_public(public_id, **update_data)
        if request.tags is not None:
            await self._tag_service.set_tags(presentation.id, request.tags)

        await self._uow.flush()
        logger.info("presentation_autosaved", presentation_id=public_id)
        return {
            "presentation_id": presentation.public_id,
            "saved_at": datetime.now(UTC),
            "draft_saved": True,
        }

    # ── Analytics ───────────────────────────────────────────────────────────────

    async def get_analytics(
        self,
        public_id: str,
    ) -> dict[str, Any] | None:
        presentation = await self._get_presentation(public_id)
        return await self._analytics_service.get_analytics(presentation.id)

    async def record_view(
        self,
        public_id: str,
        is_new_viewer: bool = False,
    ) -> dict[str, Any]:
        presentation = await self._get_presentation(public_id)
        analytics = await self._analytics_service.record_view(
            presentation.id,
            is_new_viewer=is_new_viewer,
        )
        return {
            "presentation_id": presentation.public_id,
            "view_count": analytics.view_count,
            "last_viewed_at": analytics.last_viewed_at,
        }

    async def generate_thumbnail(self, public_id: str) -> str:
        presentation = await self._get_presentation(public_id)
        thumbnail_key = f"thumbnails/{presentation.public_id}.png"
        presentation.thumbnail_key = thumbnail_key
        await self._uow.flush()
        logger.info("presentation_thumbnail_generated", presentation_id=public_id)
        return thumbnail_key

    # ── Maintenance (Celery) ────────────────────────────────────────────────────

    async def cleanup_draft_presentations(self, max_age_days: int = 30) -> int:
        cutoff = datetime.now(UTC) - timedelta(days=max_age_days)
        stmt = select(Presentation).where(
            Presentation.status == PresentationStatus.DRAFT.value,
            Presentation.deleted_at.is_(None),
            Presentation.updated_at < cutoff,
        )
        result = await self._uow.session.execute(stmt)
        presentations = list(result.scalars().all())
        for presentation in presentations:
            await self._repo.delete(presentation.id, hard=True)
        if presentations:
            await self._uow.flush()
            logger.info(
                "draft_presentations_cleaned",
                count=len(presentations),
                max_age_days=max_age_days,
            )
        return len(presentations)

    async def cleanup_archived_presentations(self, retention_days: int = 30) -> int:
        cutoff = datetime.now(UTC) - timedelta(days=retention_days)
        stmt = select(Presentation).where(
            Presentation.status == PresentationStatus.ARCHIVED.value,
            Presentation.deleted_at.is_(None),
            Presentation.archived_at.is_not(None),
            Presentation.archived_at < cutoff,
        )
        result = await self._uow.session.execute(stmt)
        presentations = list(result.scalars().all())
        for presentation in presentations:
            await self._repo.delete(presentation.id, hard=True)
        if presentations:
            await self._uow.flush()
            logger.info(
                "archived_presentations_cleaned",
                count=len(presentations),
                retention_days=retention_days,
            )
        return len(presentations)

    async def cleanup_soft_deleted_presentations(
        self, retention_days: int = DRAFT_RECOVERY_WINDOW_DAYS
    ) -> int:
        cutoff = datetime.now(UTC) - timedelta(days=retention_days)
        stmt = select(Presentation).where(
            Presentation.deleted_at.is_not(None),
            Presentation.deleted_at < cutoff,
        )
        result = await self._uow.session.execute(stmt)
        presentations = list(result.scalars().all())
        for presentation in presentations:
            await self._repo.delete(presentation.id, hard=True)
        if presentations:
            await self._uow.flush()
            logger.info(
                "soft_deleted_presentations_cleaned",
                count=len(presentations),
                retention_days=retention_days,
            )
        return len(presentations)
