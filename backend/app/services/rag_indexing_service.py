"""Source-to-index trigger for the RAG pipeline (F2-13 Phase 1).

Before this service existed the whole RAG stack (chunking engine, embedding
jobs/batches, vector index metadata) was built but never wired: nothing ever
created ``DocumentChunk`` rows or dispatched ``embedding_generation_task``, so
the AI tutor always searched an empty corpus.

This service is the missing producer. It is invoked by the background worker
after a successful source extraction (presentation scope) or AI lesson
generation (lesson scope) and, for each scope:

* guards that the scope is actually indexable (extraction READY / succeeded
  lesson version present) — raising a non-retryable ``RagIndexingError``
  otherwise so the caller logs a clean failure instead of ghosting a stuck
  state;
* chunks the source content with the shared ``ChunkingService``;
* replaces the scope's previous chunks (soft-delete + insert);
* reuses or (re)builds the scope's ``VectorIndex`` metadata row;
* creates a deterministic-idempotency ``EmbeddingJob`` and best-effort
  dispatches ``embedding_generation_task``.

Re-indexing is content-addressed: when the scope's content hash is unchanged
and its index is already READY the whole pass is skipped, and a re-trigger for
unchanged content never dispatches a second embedding job.
"""

from __future__ import annotations

import hashlib
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.logging import get_logger
from app.database.unit_of_work import UnitOfWork
from app.models.document_chunk import DocumentChunk
from app.models.embedding_job import EmbeddingJob
from app.models.generated_lesson_version import GeneratedLessonVersion
from app.models.vector_index import VectorIndex
from app.repositories.content_repository import ContentUnitRepository
from app.repositories.generated_lesson_repository import GeneratedLessonRepository
from app.repositories.presentation_repository import PresentationRepository
from app.repositories.rag_repository import (
    DocumentChunkRepository,
    EmbeddingJobRepository,
    VectorIndexRepository,
)
from app.services.chunking_service import (
    ChunkingService,
    ChunkSourceUnit,
    units_from_content_unit,
    units_from_generated_lesson_version,
)
from shared.constants import (
    ChunkingStrategy,
    ChunkSource,
    EmbeddingJobStatus,
    EmbeddingJobType,
    ExtractionStatus,
    LessonStatus,
    LessonVersionStatus,
    VectorIndexStatus,
    VectorIndexType,
)

logger = get_logger(__name__)

_REBUILD_STATUSES = {
    VectorIndexStatus.BUILDING.value,
    VectorIndexStatus.REBUILDING.value,
    VectorIndexStatus.FAILED.value,
}


class RagIndexingError(Exception):
    """Raised when a scope cannot be indexed (deterministic, non-retryable).

    These are guard failures (scope missing / not ready / no content), so the
    caller should log them and acknowledge the task rather than retry.
    """


class RagIndexingService:
    """Producer for the RAG pipeline: chunks a scope and enqueues embedding."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow
        session: AsyncSession = uow.session
        self._presentations = PresentationRepository(session)
        self._lessons = GeneratedLessonRepository(session)
        self._units = ContentUnitRepository(session)
        self._chunks = DocumentChunkRepository(session)
        self._jobs = EmbeddingJobRepository(session)
        self._indexes = VectorIndexRepository(session)

    # ── Presentation scope ────────────────────────────────────────────────────

    async def index_presentation(self, public_id: str) -> dict[str, object]:
        presentation = await self._presentations.get_by_public_id(public_id)
        if presentation is None:
            raise RagIndexingError(
                f"Presentation {public_id} not found — nothing to index"
            )
        if presentation.extraction_status != ExtractionStatus.READY.value:
            raise RagIndexingError(
                f"Presentation {public_id} extraction status is "
                f"{presentation.extraction_status!r}, expected 'ready'"
            )

        units = await self._units.list_for_presentation(
            presentation.id, include_blocks=True
        )
        source_units = [
            unit for content_unit in units
            for unit in units_from_content_unit(content_unit)
        ]
        if not source_units:
            raise RagIndexingError(
                f"Presentation {public_id} has no extractable content blocks"
            )

        source_hash = _source_hash([unit.content for unit in source_units])
        index = await self._indexes.get_for_presentation(presentation.id)
        if index is not None and index.source_hash == source_hash:
            if index.status == VectorIndexStatus.READY.value:
                return self._result(
                    "presentation",
                    public_id,
                    index=index,
                    job=None,
                    chunks=0,
                    skipped=True,
                )
            if index.status not in _REBUILD_STATUSES:
                # Unknown status and unchanged content: not safe to overwrite.
                raise RagIndexingError(
                    f"Presentation {public_id} index is in status "
                    f"{index.status!r}; refusing to rebuild"
                )

        candidates = self._chunk(
            source_units, source=ChunkSource.PRESENTATION.value
        )
        chunk_ids = await self._replace_presentation_chunks(presentation.id, candidates)
        index = await self._ensure_index(
            index=index,
            presentation_id=presentation.id,
            lesson_id=None,
            index_type=VectorIndexType.PRESENTATION.value,
            source_hash=source_hash,
        )
        job = await self._ensure_job(
            user_id=presentation.owner_id,
            presentation_id=presentation.id,
            lesson_id=None,
            index_id=index.id,
            idempotency_base=f"pres:{presentation.id}:{source_hash}",
            total_items=len(chunk_ids),
        )
        await self._dispatch(job)
        return self._result(
            "presentation", public_id, index=index, job=job, chunks=len(chunk_ids)
        )

    # ── Lesson scope ──────────────────────────────────────────────────────────

    async def index_lesson(self, public_id: str) -> dict[str, object]:
        lesson = await self._lessons.get_by_public_id(public_id)
        if lesson is None:
            raise RagIndexingError(f"Lesson {public_id} not found — nothing to index")
        if lesson.status != LessonStatus.READY.value:
            raise RagIndexingError(
                f"Lesson {public_id} status is {lesson.status!r}, expected 'ready'"
            )

        version = await self._latest_succeeded_version(lesson.id)
        if version is None:
            raise RagIndexingError(
                f"Lesson {public_id} has no succeeded lesson version to index"
            )

        source_units = units_from_generated_lesson_version(version)
        if not source_units:
            raise RagIndexingError(
                f"Lesson {public_id} version {version.version} has no blocks"
            )

        source_hash = _source_hash([unit.content for unit in source_units])
        index = await self._indexes.get_for_lesson(lesson.id)
        if index is not None and index.source_hash == source_hash:
            if index.status == VectorIndexStatus.READY.value:
                return self._result(
                    "lesson",
                    public_id,
                    index=index,
                    job=None,
                    chunks=0,
                    skipped=True,
                )
            if index.status not in _REBUILD_STATUSES:
                raise RagIndexingError(
                    f"Lesson {public_id} index is in status {index.status!r}; "
                    "refusing to rebuild"
                )

        candidates = self._chunk(source_units, source=ChunkSource.LESSON.value)
        chunk_ids = await self._replace_lesson_chunks(
            lesson.id, version.id, candidates
        )
        index = await self._ensure_index(
            index=index,
            presentation_id=None,
            lesson_id=lesson.id,
            index_type=VectorIndexType.LESSON.value,
            source_hash=source_hash,
        )
        job = await self._ensure_job(
            user_id=lesson.user_id or lesson.presentation.owner_id,
            presentation_id=None,
            lesson_id=lesson.id,
            index_id=index.id,
            idempotency_base=f"lesson:{lesson.id}:{version.version}:{source_hash}",
            total_items=len(chunk_ids),
        )
        await self._dispatch(job)
        return self._result(
            "lesson", public_id, index=index, job=job, chunks=len(chunk_ids)
        )

    # ── Internals ─────────────────────────────────────────────────────────────

    def _chunk(
        self, source_units: list[ChunkSourceUnit], *, source: str
    ) -> list[DocumentChunk]:
        chunker = ChunkingService(
            strategy=settings.RAG_INDEXING_STRATEGY or ChunkingStrategy.SEMANTIC.value,
            chunk_size=settings.CHUNK_SIZE,
            chunk_overlap=settings.CHUNK_OVERLAP,
            max_chunk_tokens=settings.MAX_CHUNK_TOKENS,
            max_chunk_characters=settings.MAX_CHUNK_CHARACTERS,
        )
        rows: list[DocumentChunk] = []
        for candidate in chunker.chunk(source_units):
            rows.append(
                DocumentChunk(
                    source=source,
                    chunk_type=candidate.chunk_type,
                    position=candidate.position,
                    level=candidate.level,
                    title=candidate.title,
                    content=candidate.content,
                    heading_path=(
                        {"path": candidate.heading_path}
                        if candidate.heading_path
                        else None
                    ),
                    token_count=candidate.token_count,
                    character_count=candidate.character_count,
                    chunk_hash=candidate.chunk_hash,
                    checksum=candidate.checksum,
                    language=candidate.language,
                    source_page=candidate.source_page,
                    source_slide=candidate.source_slide,
                    source_unit_position=candidate.source_unit_position,
                    meta=candidate.meta or None,
                    status="pending",
                    retry_state="none",
                )
            )
        return rows

    async def _replace_presentation_chunks(
        self, presentation_id: uuid.UUID, candidates: list[DocumentChunk]
    ) -> list[uuid.UUID]:
        existing = await self._chunks.list_for_presentation(
            presentation_id, limit=1000
        )
        if existing:
            await self._chunks.soft_delete_many([chunk.id for chunk in existing])
        next_version = await self._next_chunk_version(presentation_id)
        for chunk in candidates:
            chunk.presentation_id = presentation_id
            chunk.version = next_version
        self._uow.session.add_all(candidates)
        await self._uow.flush()
        return [chunk.id for chunk in candidates]

    async def _replace_lesson_chunks(
        self,
        lesson_id: uuid.UUID,
        lesson_version_id: uuid.UUID,
        candidates: list[DocumentChunk],
    ) -> list[uuid.UUID]:
        existing = await self._chunks.list_for_lesson(lesson_id, limit=1000)
        if existing:
            await self._chunks.soft_delete_many([chunk.id for chunk in existing])
        for chunk in candidates:
            chunk.lesson_id = lesson_id
            chunk.lesson_version_id = lesson_version_id
        self._uow.session.add_all(candidates)
        await self._uow.flush()
        return [chunk.id for chunk in candidates]

    async def _next_chunk_version(self, presentation_id: uuid.UUID) -> int:
        stmt = select(func.max(DocumentChunk.version)).where(
            DocumentChunk.presentation_id == presentation_id
        )
        result = await self._uow.session.execute(stmt)
        current = result.scalar_one_or_none()
        return int(current or 0) + 1

    async def _ensure_index(
        self,
        *,
        index: VectorIndex | None,
        presentation_id: uuid.UUID | None,
        lesson_id: uuid.UUID | None,
        index_type: str,
        source_hash: str,
    ) -> VectorIndex:
        if index is not None:
            index = await self._indexes.mark_rebuilding(index)
            index.source_hash = source_hash
            return index
        provider, model, dimension = self._resolved_provider()
        return await self._indexes.create_for_scope(
            presentation_id=presentation_id,
            lesson_id=lesson_id,
            index_type=index_type,
            strategy=settings.RAG_INDEXING_STRATEGY or ChunkingStrategy.SEMANTIC.value,
            chunk_size=settings.CHUNK_SIZE,
            chunk_overlap=settings.CHUNK_OVERLAP,
            max_chunk_tokens=settings.MAX_CHUNK_TOKENS,
            provider=provider,
            model=model,
            dimension=dimension,
            source_hash=source_hash,
        )

    async def _ensure_job(
        self,
        *,
        user_id: uuid.UUID | str | None,
        presentation_id: uuid.UUID | None,
        lesson_id: uuid.UUID | None,
        index_id: uuid.UUID,
        idempotency_base: str,
        total_items: int,
    ) -> EmbeddingJob:
        normalized_user_id = uuid.UUID(user_id) if isinstance(user_id, str) else user_id
        idempotency_key = f"index:{idempotency_base}"[:128]
        existing = await self._jobs.get_by_idempotency_key(normalized_user_id, idempotency_key)
        if existing is not None and existing.status in {
            EmbeddingJobStatus.QUEUED.value,
            EmbeddingJobStatus.PROCESSING.value,
        }:
            logger.info(
                "rag_indexing_job_reused",
                job_id=existing.public_id,
                idempotency_key=idempotency_key,
            )
            return existing
        if existing is not None:
            # A terminal job already exists for this content hash; bump the key
            # so a rebuild after a failure gets a fresh, unique job row.
            idempotency_key = f"{idempotency_key}:{uuid.uuid4().hex[:8]}"[:128]
        return await self._jobs.create_job(
            job_type=EmbeddingJobType.INDEX.value,
            user_id=normalized_user_id,
            presentation_id=presentation_id,
            lesson_id=lesson_id,
            index_id=index_id,
            total_items=total_items,
            payload={
                "scope": "lesson" if lesson_id else "presentation",
                "idempotency_key": idempotency_key,
            },
            idempotency_key=idempotency_key,
            priority=5,
            max_attempts=3,
        )

    def _resolved_provider(self) -> tuple[str | None, str | None, int]:
        provider = settings.EMBEDDING_PROVIDER or settings.AI_PROVIDER or None
        model = settings.EMBEDDING_MODEL or settings.AI_MODEL or None
        dimension = 0
        try:
            from app.ai.embeddings import create_embedding_provider

            dimension = int(create_embedding_provider().dimension or 0)
        except Exception:  # noqa: BLE001 - metadata must not fail indexing
            logger.warning(
                "rag_indexing_provider_dimension_unavailable",
                provider=provider,
                model=model,
            )
        return provider, model, dimension

    async def _latest_succeeded_version(
        self, lesson_id: uuid.UUID
    ) -> GeneratedLessonVersion | None:
        stmt = (
            select(GeneratedLessonVersion)
            .options(selectinload(GeneratedLessonVersion.blocks))
            .where(
                GeneratedLessonVersion.lesson_id == lesson_id,
                GeneratedLessonVersion.status == LessonVersionStatus.SUCCEEDED.value,
            )
            .order_by(GeneratedLessonVersion.version.desc(), GeneratedLessonVersion.id.desc())
            .limit(1)
        )
        result = await self._uow.session.execute(stmt)
        return result.scalar_one_or_none()

    async def _dispatch(self, job: EmbeddingJob) -> None:
        from app.workers.rag_tasks import embedding_generation_task
        from app.workers.tasks import safe_dispatch

        safe_dispatch(embedding_generation_task, job.public_id)

    @staticmethod
    def _result(
        scope: str,
        public_id: str,
        *,
        index: VectorIndex,
        job: EmbeddingJob | None,
        chunks: int,
        skipped: bool = False,
    ) -> dict[str, object]:
        return {
            "scope": scope,
            "public_id": public_id,
            "index_id": index.public_id,
            "job_id": job.public_id if job is not None else None,
            "chunks": chunks,
            "skipped": skipped,
        }


def _source_hash(contents: list[str]) -> str:
    digest = hashlib.sha256()
    for content in contents:
        digest.update((content or "").encode("utf-8"))
        digest.update(b"\x00")
    return digest.hexdigest()
