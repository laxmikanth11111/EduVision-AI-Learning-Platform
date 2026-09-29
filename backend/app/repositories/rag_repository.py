from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import NotFoundError
from app.database.repository import BaseRepository
from app.models.chunk_embedding import ChunkEmbedding
from app.models.document_chunk import DocumentChunk
from app.models.embedding_batch import EmbeddingBatch
from app.models.embedding_job import EmbeddingJob
from app.models.embedding_metadata import EmbeddingMetadata
from app.models.embedding_statistics import EmbeddingStatistics
from app.models.vector_index import VectorIndex
from app.models.vector_index_version import VectorIndexVersion
from shared.constants import (
    ChunkRetryState,
    ChunkStatus,
    EmbeddingBatchStatus,
    EmbeddingJobStatus,
    EmbeddingRetryState,
    EmbeddingStatisticsPeriod,
    EmbeddingVersionStatus,
    VectorIndexStatus,
    VectorIndexType,
)


def _active_embedding_predicate(provider: str, model: str) -> list[Any]:
    return [
        ChunkEmbedding.chunk_id == DocumentChunk.id,
        ChunkEmbedding.provider == provider,
        ChunkEmbedding.model == model,
        ChunkEmbedding.status == EmbeddingVersionStatus.ACTIVE.value,
        ChunkEmbedding.deleted_at.is_(None),
    ]


class DocumentChunkRepository(BaseRepository[DocumentChunk]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, DocumentChunk)

    async def get_for_scope_or_raise(
        self, presentation_id: uuid.UUID, public_id: str
    ) -> DocumentChunk:
        chunk = await self.find_one(
            presentation_id=presentation_id, public_id=public_id
        )
        if chunk is None:
            raise NotFoundError(
                message="Document chunk not found",
                details={"presentation_id": str(presentation_id), "chunk_id": public_id},
            )
        return chunk

    async def list_for_presentation(
        self,
        presentation_id: uuid.UUID,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[DocumentChunk]:
        stmt = (
            select(DocumentChunk)
            .where(
                DocumentChunk.presentation_id == presentation_id,
                DocumentChunk.deleted_at.is_(None),
            )
            .order_by(DocumentChunk.position.asc(), DocumentChunk.id)
            .limit(limit)
            .offset(offset)
        )
        if status is not None:
            stmt = stmt.where(DocumentChunk.status == status)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_lesson(
        self,
        lesson_id: uuid.UUID,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[DocumentChunk]:
        stmt = (
            select(DocumentChunk)
            .where(
                DocumentChunk.lesson_id == lesson_id,
                DocumentChunk.deleted_at.is_(None),
            )
            .order_by(DocumentChunk.position.asc(), DocumentChunk.id)
            .limit(limit)
            .offset(offset)
        )
        if status is not None:
            stmt = stmt.where(DocumentChunk.status == status)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_pending_for_scope(
        self, presentation_id: uuid.UUID, limit: int = 50
    ) -> list[DocumentChunk]:
        stmt = (
            select(DocumentChunk)
            .where(
                DocumentChunk.presentation_id == presentation_id,
                DocumentChunk.status == ChunkStatus.PENDING.value,
                DocumentChunk.deleted_at.is_(None),
            )
            .order_by(DocumentChunk.position.asc(), DocumentChunk.id)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_pending_for_lesson(
        self, lesson_id: uuid.UUID, limit: int = 50
    ) -> list[DocumentChunk]:
        stmt = (
            select(DocumentChunk)
            .where(
                DocumentChunk.lesson_id == lesson_id,
                DocumentChunk.status == ChunkStatus.PENDING.value,
                DocumentChunk.deleted_at.is_(None),
            )
            .order_by(DocumentChunk.position.asc(), DocumentChunk.id)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_unembedded(
        self,
        presentation_id: uuid.UUID,
        provider: str,
        model: str,
        limit: int = 50,
    ) -> list[DocumentChunk]:
        stmt = (
            select(DocumentChunk)
            .outerjoin(
                ChunkEmbedding,
                and_(*_active_embedding_predicate(provider, model)),
            )
            .where(
                DocumentChunk.presentation_id == presentation_id,
                DocumentChunk.deleted_at.is_(None),
                ChunkEmbedding.id.is_(None),
            )
            .order_by(DocumentChunk.position.asc(), DocumentChunk.id)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_unembedded_for_lesson(
        self,
        lesson_id: uuid.UUID,
        provider: str,
        model: str,
        limit: int = 50,
    ) -> list[DocumentChunk]:
        stmt = (
            select(DocumentChunk)
            .outerjoin(
                ChunkEmbedding,
                and_(*_active_embedding_predicate(provider, model)),
            )
            .where(
                DocumentChunk.lesson_id == lesson_id,
                DocumentChunk.deleted_at.is_(None),
                ChunkEmbedding.id.is_(None),
            )
            .order_by(DocumentChunk.position.asc(), DocumentChunk.id)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_embedded_pairs(
        self,
        presentation_id: uuid.UUID,
        provider: str,
        model: str,
        limit: int = 200,
    ) -> list[tuple[DocumentChunk, ChunkEmbedding]]:
        stmt = (
            select(DocumentChunk, ChunkEmbedding)
            .join(
                ChunkEmbedding,
                and_(*_active_embedding_predicate(provider, model)),
            )
            .where(
                DocumentChunk.presentation_id == presentation_id,
                DocumentChunk.deleted_at.is_(None),
            )
            .order_by(DocumentChunk.position.asc(), DocumentChunk.id)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [(chunk, embedding) for chunk, embedding in result.all()]

    async def list_embedded_pairs_for_lesson(
        self,
        lesson_id: uuid.UUID,
        provider: str,
        model: str,
        limit: int = 200,
    ) -> list[tuple[DocumentChunk, ChunkEmbedding]]:
        stmt = (
            select(DocumentChunk, ChunkEmbedding)
            .join(
                ChunkEmbedding,
                and_(*_active_embedding_predicate(provider, model)),
            )
            .where(
                DocumentChunk.lesson_id == lesson_id,
                DocumentChunk.deleted_at.is_(None),
            )
            .order_by(DocumentChunk.position.asc(), DocumentChunk.id)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [(chunk, embedding) for chunk, embedding in result.all()]

    async def list_embedded_pairs_for_content_units(
        self,
        content_unit_ids: list[uuid.UUID],
        provider: str,
        model: str,
        limit: int = 200,
    ) -> list[tuple[DocumentChunk, ChunkEmbedding]]:
        """Load active chunk/embedding pairs scoped to a set of content units.

        A single bounded query (chunk + active embedding inner join) so the
        retrieval layer can rank candidates in Python without any per-chunk
        SELECT/N+1 pattern. Soft-deleted chunks and embeddings are excluded,
        mirroring ``_active_embedding_predicate`` and the sibling list helpers.
        """
        stmt = (
            select(DocumentChunk, ChunkEmbedding)
            .join(
                ChunkEmbedding,
                and_(*_active_embedding_predicate(provider, model)),
            )
            .where(
                DocumentChunk.content_unit_id.in_(content_unit_ids),
                DocumentChunk.content.isnot(None),
                DocumentChunk.content != "",
                DocumentChunk.deleted_at.is_(None),
            )
            .order_by(DocumentChunk.position.asc(), DocumentChunk.id)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [(chunk, embedding) for chunk, embedding in result.all()]

    async def count_by_status(self, presentation_id: uuid.UUID) -> dict[str, int]:
        stmt = (
            select(DocumentChunk.status, func.count())
            .where(
                DocumentChunk.presentation_id == presentation_id,
                DocumentChunk.deleted_at.is_(None),
            )
            .group_by(DocumentChunk.status)
        )
        result = await self._session.execute(stmt)
        return {status: int(count) for status, count in result.all()}

    async def count_all_by_status(self) -> dict[str, int]:
        """Global chunk counts grouped by status (statistics worker)."""
        stmt = (
            select(DocumentChunk.status, func.count())
            .where(DocumentChunk.deleted_at.is_(None))
            .group_by(DocumentChunk.status)
        )
        result = await self._session.execute(stmt)
        return {status: int(count) for status, count in result.all()}

    async def sum_retries(self) -> int:
        """Global sum of chunk retry counts (statistics worker)."""
        stmt = select(func.coalesce(func.sum(DocumentChunk.retry_count), 0))
        result = await self._session.execute(stmt)
        return int(result.scalar_one() or 0)

    async def find_by_hash(self, chunk_hash: str) -> DocumentChunk | None:
        stmt = (
            select(DocumentChunk)
            .where(DocumentChunk.chunk_hash == chunk_hash)
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def mark_processed(self, chunk: DocumentChunk) -> DocumentChunk:
        chunk.status = ChunkStatus.PROCESSED.value
        chunk.retry_state = ChunkRetryState.NONE.value
        chunk.retry_count = 0
        chunk.next_retry_at = None
        await self._session.flush()
        await self._session.refresh(chunk)
        return chunk

    async def mark_failed(self, chunk: DocumentChunk) -> DocumentChunk:
        chunk.status = ChunkStatus.FAILED.value
        await self._session.flush()
        await self._session.refresh(chunk)
        return chunk

    async def record_retry(
        self,
        chunk: DocumentChunk,
        *,
        retry_count: int,
        max_retries: int,
        next_retry_at: datetime,
    ) -> DocumentChunk:
        chunk.retry_count = retry_count
        chunk.max_retries = max_retries
        chunk.next_retry_at = next_retry_at
        chunk.retry_state = (
            ChunkRetryState.EXHAUSTED.value
            if retry_count >= max_retries
            else ChunkRetryState.SCHEDULED.value
        )
        await self._session.flush()
        await self._session.refresh(chunk)
        return chunk

    async def soft_delete_many(self, chunk_ids: list[uuid.UUID]) -> int:
        stmt = select(DocumentChunk).where(
            DocumentChunk.id.in_(chunk_ids),
            DocumentChunk.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        chunks = list(result.scalars().all())
        now = datetime.now(UTC)
        for chunk in chunks:
            chunk.deleted_at = now
        await self._session.flush()
        return len(chunks)

    async def list_by_ids(self, chunk_ids: list[uuid.UUID]) -> list[DocumentChunk]:
        if not chunk_ids:
            return []
        stmt = (
            select(DocumentChunk)
            .where(
                DocumentChunk.id.in_(chunk_ids),
                DocumentChunk.deleted_at.is_(None),
            )
            .order_by(DocumentChunk.position.asc(), DocumentChunk.id)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class EmbeddingRepository(BaseRepository[ChunkEmbedding]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ChunkEmbedding)

    async def get_active(
        self, chunk_id: uuid.UUID, provider: str, model: str
    ) -> ChunkEmbedding | None:
        stmt = (
            select(ChunkEmbedding)
            .where(
                ChunkEmbedding.chunk_id == chunk_id,
                ChunkEmbedding.provider == provider,
                ChunkEmbedding.model == model,
                ChunkEmbedding.status == EmbeddingVersionStatus.ACTIVE.value,
                ChunkEmbedding.deleted_at.is_(None),
            )
            .order_by(ChunkEmbedding.version.desc(), ChunkEmbedding.id)
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_chunk(
        self, chunk_id: uuid.UUID, limit: int = 10
    ) -> list[ChunkEmbedding]:
        stmt = (
            select(ChunkEmbedding)
            .where(
                ChunkEmbedding.chunk_id == chunk_id,
                ChunkEmbedding.deleted_at.is_(None),
            )
            .order_by(ChunkEmbedding.version.desc(), ChunkEmbedding.id)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def create_for_chunk(
        self,
        chunk_id: uuid.UUID,
        provider: str,
        model: str,
        dimension: int,
        vector: list[float],
        token_count: int,
        embedding_hash: str,
        checksum: str,
        meta: dict[str, object] | None = None,
        version: int = 1,
    ) -> ChunkEmbedding:
        return await self.create(
            chunk_id=chunk_id,
            provider=provider,
            model=model,
            dimension=dimension,
            vector=vector,
            token_count=token_count,
            embedding_hash=embedding_hash,
            checksum=checksum,
            meta=meta,
            status=EmbeddingVersionStatus.ACTIVE.value,
            version=version,
        )

    async def supersede_for_chunk(
        self, chunk_id: uuid.UUID, provider: str, model: str
    ) -> int:
        stmt = (
            select(ChunkEmbedding)
            .where(
                ChunkEmbedding.chunk_id == chunk_id,
                ChunkEmbedding.provider == provider,
                ChunkEmbedding.model == model,
                ChunkEmbedding.status == EmbeddingVersionStatus.ACTIVE.value,
                ChunkEmbedding.deleted_at.is_(None),
            )
        )
        result = await self._session.execute(stmt)
        embeddings = list(result.scalars().all())
        for embedding in embeddings:
            embedding.status = EmbeddingVersionStatus.SUPERSEDED.value
        await self._session.flush()
        return len(embeddings)

    async def count_active_for_scope(
        self, presentation_id: uuid.UUID, provider: str, model: str
    ) -> int:
        stmt = (
            select(func.count())
            .select_from(ChunkEmbedding)
            .join(DocumentChunk, ChunkEmbedding.chunk_id == DocumentChunk.id)
            .where(
                DocumentChunk.presentation_id == presentation_id,
                DocumentChunk.deleted_at.is_(None),
                ChunkEmbedding.provider == provider,
                ChunkEmbedding.model == model,
                ChunkEmbedding.status == EmbeddingVersionStatus.ACTIVE.value,
                ChunkEmbedding.deleted_at.is_(None),
            )
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one() or 0)

    async def list_orphans(
        self,
        presentation_id: uuid.UUID,
        provider: str,
        model: str,
        limit: int = 50,
    ) -> list[ChunkEmbedding]:
        stmt = (
            select(ChunkEmbedding)
            .join(DocumentChunk, ChunkEmbedding.chunk_id == DocumentChunk.id)
            .where(
                DocumentChunk.presentation_id == presentation_id,
                DocumentChunk.deleted_at.isnot(None),
                ChunkEmbedding.provider == provider,
                ChunkEmbedding.model == model,
                ChunkEmbedding.status == EmbeddingVersionStatus.ACTIVE.value,
                ChunkEmbedding.deleted_at.is_(None),
            )
            .order_by(ChunkEmbedding.created_at.desc(), ChunkEmbedding.id)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_orphans(
        self, presentation_id: uuid.UUID, provider: str, model: str
    ) -> int:
        stmt = (
            select(func.count())
            .select_from(ChunkEmbedding)
            .join(DocumentChunk, ChunkEmbedding.chunk_id == DocumentChunk.id)
            .where(
                DocumentChunk.presentation_id == presentation_id,
                DocumentChunk.deleted_at.isnot(None),
                ChunkEmbedding.provider == provider,
                ChunkEmbedding.model == model,
                ChunkEmbedding.status == EmbeddingVersionStatus.ACTIVE.value,
                ChunkEmbedding.deleted_at.is_(None),
            )
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one() or 0)

    async def soft_delete(self, embedding: ChunkEmbedding) -> ChunkEmbedding:
        embedding.deleted_at = datetime.now(UTC)
        await self._session.flush()
        await self._session.refresh(embedding)
        return embedding

    async def soft_delete_for_chunks(self, chunk_ids: list[uuid.UUID]) -> int:
        stmt = select(ChunkEmbedding).where(
            ChunkEmbedding.chunk_id.in_(chunk_ids),
            ChunkEmbedding.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        embeddings = list(result.scalars().all())
        now = datetime.now(UTC)
        for embedding in embeddings:
            embedding.deleted_at = now
        await self._session.flush()
        return len(embeddings)

    async def list_superseded(
        self, older_than: datetime, limit: int = 50
    ) -> list[ChunkEmbedding]:
        """Obsolete (superseded) versions eligible for cleanup, oldest first."""
        stmt = (
            select(ChunkEmbedding)
            .where(
                ChunkEmbedding.status == EmbeddingVersionStatus.SUPERSEDED.value,
                ChunkEmbedding.deleted_at.is_(None),
                ChunkEmbedding.updated_at < older_than,
            )
            .order_by(ChunkEmbedding.updated_at.asc(), ChunkEmbedding.id)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def soft_delete_many(self, embeddings: list[ChunkEmbedding]) -> int:
        """Bulk soft-delete already-loaded embedding rows (cleanup worker)."""
        now = datetime.now(UTC)
        deleted = 0
        for embedding in embeddings:
            if embedding.deleted_at is None:
                embedding.deleted_at = now
                deleted += 1
        await self._session.flush()
        return deleted

    async def count_all_by_status(self) -> dict[str, int]:
        """Global embedding version counts grouped by status."""
        stmt = (
            select(ChunkEmbedding.status, func.count())
            .where(ChunkEmbedding.deleted_at.is_(None))
            .group_by(ChunkEmbedding.status)
        )
        result = await self._session.execute(stmt)
        return {status: int(count) for status, count in result.all()}

    async def count_by_provider_model(self) -> list[tuple[str, str, int]]:
        """Active embedding usage grouped by ``(provider, model)``."""
        stmt = (
            select(
                ChunkEmbedding.provider,
                ChunkEmbedding.model,
                func.count(),
            )
            .where(
                ChunkEmbedding.status == EmbeddingVersionStatus.ACTIVE.value,
                ChunkEmbedding.deleted_at.is_(None),
            )
            .group_by(ChunkEmbedding.provider, ChunkEmbedding.model)
            .order_by(ChunkEmbedding.provider, ChunkEmbedding.model)
        )
        result = await self._session.execute(stmt)
        return [(provider, model, int(count)) for provider, model, count in result.all()]

    async def count_active_total(self) -> int:
        """Global count of active embedding vectors."""
        stmt = select(func.count()).select_from(ChunkEmbedding).where(
            ChunkEmbedding.status == EmbeddingVersionStatus.ACTIVE.value,
            ChunkEmbedding.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one() or 0)

    async def average_dimension(self) -> float:
        """Global average vector dimension over active embeddings."""
        stmt = select(func.coalesce(func.avg(ChunkEmbedding.dimension), 0.0)).where(
            ChunkEmbedding.status == EmbeddingVersionStatus.ACTIVE.value,
            ChunkEmbedding.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return round(float(result.scalar_one() or 0.0), 4)


class EmbeddingJobRepository(BaseRepository[EmbeddingJob]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, EmbeddingJob)

    async def get_for_user(
        self, user_id: uuid.UUID, public_id: str
    ) -> EmbeddingJob | None:
        stmt = (
            select(EmbeddingJob)
            .options(selectinload(EmbeddingJob.batches))
            .where(
                EmbeddingJob.user_id == user_id,
                EmbeddingJob.public_id == public_id,
                EmbeddingJob.deleted_at.is_(None),
            )
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_for_user_or_raise(
        self, user_id: uuid.UUID, public_id: str
    ) -> EmbeddingJob:
        job = await self.get_for_user(user_id, public_id)
        if job is None:
            raise NotFoundError(
                message="Embedding job not found",
                details={"user_id": str(user_id), "embedding_job_id": public_id},
            )
        return job

    async def list_for_user(
        self, user_id: uuid.UUID, limit: int = 25
    ) -> list[EmbeddingJob]:
        stmt = (
            select(EmbeddingJob)
            .where(
                EmbeddingJob.user_id == user_id,
                EmbeddingJob.deleted_at.is_(None),
            )
            .order_by(EmbeddingJob.created_at.desc(), EmbeddingJob.id)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_queued(self, limit: int = 10) -> list[EmbeddingJob]:
        stmt = (
            select(EmbeddingJob)
            .where(
                EmbeddingJob.status == EmbeddingJobStatus.QUEUED.value,
                EmbeddingJob.deleted_at.is_(None),
            )
            .order_by(
                EmbeddingJob.priority.asc(),
                EmbeddingJob.created_at.asc(),
                EmbeddingJob.id,
            )
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_processing(self, limit: int = 10) -> list[EmbeddingJob]:
        stmt = (
            select(EmbeddingJob)
            .where(
                EmbeddingJob.status == EmbeddingJobStatus.PROCESSING.value,
                EmbeddingJob.deleted_at.is_(None),
            )
            .order_by(EmbeddingJob.started_at.asc(), EmbeddingJob.id)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_public_id(self, public_id: str) -> EmbeddingJob | None:
        """Resolve a job by its public id (worker entry point)."""
        return await self.find_one(public_id=public_id, deleted_at=None)

    async def list_stale(
        self, older_than: datetime, limit: int = 50
    ) -> list[EmbeddingJob]:
        """Queued/processing jobs untouched since ``older_than`` (cleanup)."""
        stmt = (
            select(EmbeddingJob)
            .where(
                EmbeddingJob.status.in_(
                    [EmbeddingJobStatus.QUEUED.value, EmbeddingJobStatus.PROCESSING.value]
                ),
                EmbeddingJob.deleted_at.is_(None),
                EmbeddingJob.updated_at < older_than,
            )
            .order_by(EmbeddingJob.updated_at.asc(), EmbeddingJob.id)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_idempotency_key(
        self, user_id: uuid.UUID | None, idempotency_key: str
    ) -> EmbeddingJob | None:
        """Look up a job by (user_id, idempotency_key).

        ``EmbeddingJob.user_id`` is nullable, so ``user_id`` must accept None:
        comparing the column to NULL would otherwise never match. A NULL user
        simply yields no row, which is the correct "no prior job" answer.
        """
        stmt = (
            select(EmbeddingJob)
            .where(
                EmbeddingJob.user_id == user_id,
                EmbeddingJob.idempotency_key == idempotency_key,
                EmbeddingJob.deleted_at.is_(None),
            )
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_job(
        self,
        *,
        job_type: str,
        user_id: uuid.UUID | None,
        presentation_id: uuid.UUID | None,
        lesson_id: uuid.UUID | None,
        index_id: uuid.UUID | None,
        total_items: int,
        payload: dict[str, object] | None,
        idempotency_key: str | None,
        priority: int = 5,
        max_attempts: int = 3,
    ) -> EmbeddingJob:
        return await self.create(
            job_type=job_type,
            user_id=user_id,
            presentation_id=presentation_id,
            lesson_id=lesson_id,
            index_id=index_id,
            total_items=total_items,
            payload=payload,
            idempotency_key=idempotency_key,
            priority=priority,
            max_attempts=max_attempts,
            status=EmbeddingJobStatus.QUEUED.value,
            retry_state=EmbeddingRetryState.NONE.value,
        )

    async def mark_processing(self, job: EmbeddingJob) -> EmbeddingJob:
        job.status = EmbeddingJobStatus.PROCESSING.value
        job.started_at = datetime.now(UTC)
        await self._session.flush()
        await self._session.refresh(job)
        return job

    async def mark_completed(
        self, job: EmbeddingJob, result: dict[str, object] | None = None
    ) -> EmbeddingJob:
        job.status = EmbeddingJobStatus.COMPLETED.value
        job.completed_at = datetime.now(UTC)
        job.result = result
        job.error_code = None
        job.error_message = None
        job.retry_state = EmbeddingRetryState.NONE.value
        await self._session.flush()
        await self._session.refresh(job)
        return job

    async def mark_partial(
        self,
        job: EmbeddingJob,
        processed: int,
        failed: int,
        result: dict[str, object] | None = None,
    ) -> EmbeddingJob:
        job.status = EmbeddingJobStatus.PARTIAL.value
        job.processed_items = processed
        job.failed_items = failed
        job.result = result
        await self._session.flush()
        await self._session.refresh(job)
        return job

    async def mark_failed(
        self, job: EmbeddingJob, error_code: str, error_message: str
    ) -> EmbeddingJob:
        job.status = EmbeddingJobStatus.FAILED.value
        job.completed_at = datetime.now(UTC)
        job.error_code = error_code
        job.error_message = error_message
        await self._session.flush()
        await self._session.refresh(job)
        return job

    async def mark_cancelled(self, job: EmbeddingJob) -> EmbeddingJob:
        job.status = EmbeddingJobStatus.CANCELLED.value
        job.completed_at = datetime.now(UTC)
        await self._session.flush()
        await self._session.refresh(job)
        return job

    async def increment_progress(
        self,
        job: EmbeddingJob,
        processed: int,
        failed: int,
        result: dict[str, object] | None = None,
    ) -> EmbeddingJob:
        job.processed_items = max(0, processed)
        job.failed_items = max(0, failed)
        if result is not None:
            job.result = result
        await self._session.flush()
        await self._session.refresh(job)
        return job

    async def record_retry(
        self, job: EmbeddingJob, next_retry_at: datetime
    ) -> EmbeddingJob:
        job.attempt_count = min(job.max_attempts, job.attempt_count + 1)
        job.next_retry_at = next_retry_at
        job.retry_state = (
            EmbeddingRetryState.EXHAUSTED.value
            if job.attempt_count >= job.max_attempts
            else EmbeddingRetryState.SCHEDULED.value
        )
        await self._session.flush()
        await self._session.refresh(job)
        return job

    async def count_by_status_for_scope(
        self, presentation_id: uuid.UUID
    ) -> dict[str, int]:
        stmt = (
            select(EmbeddingJob.status, func.count())
            .where(
                EmbeddingJob.presentation_id == presentation_id,
                EmbeddingJob.deleted_at.is_(None),
            )
            .group_by(EmbeddingJob.status)
        )
        result = await self._session.execute(stmt)
        return {status: int(count) for status, count in result.all()}


class EmbeddingBatchRepository(BaseRepository[EmbeddingBatch]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, EmbeddingBatch)

    async def create_batch(
        self,
        job_id: uuid.UUID,
        sequence: int,
        total_items: int,
        chunk_ids: list[uuid.UUID] | None = None,
    ) -> EmbeddingBatch:
        request_ids: dict[str, object] | None = None
        if chunk_ids:
            request_ids = {"chunk_ids": [str(chunk_id) for chunk_id in chunk_ids]}
        return await self.create(
            job_id=job_id,
            sequence=sequence,
            total_items=total_items,
            status=EmbeddingBatchStatus.QUEUED.value,
            request_ids=request_ids,
        )

    @staticmethod
    def chunk_ids_for(batch: EmbeddingBatch) -> list[uuid.UUID]:
        """Parse the chunk ids recorded on a batch back into UUIDs."""
        raw = (batch.request_ids or {}).get("chunk_ids")
        if not isinstance(raw, list):
            return []
        return [uuid.UUID(str(chunk_id)) for chunk_id in raw if chunk_id is not None]

    async def list_for_job(self, job_id: uuid.UUID) -> list[EmbeddingBatch]:
        stmt = (
            select(EmbeddingBatch)
            .where(
                EmbeddingBatch.job_id == job_id,
                EmbeddingBatch.deleted_at.is_(None),
            )
            .order_by(EmbeddingBatch.sequence.asc(), EmbeddingBatch.id)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_pending_for_job(
        self, job_id: uuid.UUID, limit: int = 10
    ) -> list[EmbeddingBatch]:
        stmt = (
            select(EmbeddingBatch)
            .where(
                EmbeddingBatch.job_id == job_id,
                EmbeddingBatch.status == EmbeddingBatchStatus.QUEUED.value,
                EmbeddingBatch.deleted_at.is_(None),
            )
            .order_by(EmbeddingBatch.sequence.asc(), EmbeddingBatch.id)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def mark_processing(self, batch: EmbeddingBatch) -> EmbeddingBatch:
        batch.status = EmbeddingBatchStatus.PROCESSING.value
        batch.started_at = datetime.now(UTC)
        await self._session.flush()
        await self._session.refresh(batch)
        return batch

    async def mark_completed(
        self, batch: EmbeddingBatch, result: dict[str, object] | None = None
    ) -> EmbeddingBatch:
        batch.status = EmbeddingBatchStatus.COMPLETED.value
        batch.completed_at = datetime.now(UTC)
        batch.result = result
        await self._session.flush()
        await self._session.refresh(batch)
        return batch

    async def mark_failed(
        self, batch: EmbeddingBatch, error_code: str, error_message: str
    ) -> EmbeddingBatch:
        batch.status = EmbeddingBatchStatus.FAILED.value
        batch.completed_at = datetime.now(UTC)
        batch.error_code = error_code
        batch.error_message = error_message
        await self._session.flush()
        await self._session.refresh(batch)
        return batch

    async def update_progress(
        self,
        batch: EmbeddingBatch,
        processed: int,
        failed: int,
        request_ids: list[str] | None = None,
    ) -> EmbeddingBatch:
        batch.processed_items = max(0, processed)
        batch.failed_items = max(0, failed)
        if request_ids is not None:
            batch.request_ids = {"ids": request_ids}
        await self._session.flush()
        await self._session.refresh(batch)
        return batch

    async def get_by_public_id(self, public_id: str) -> EmbeddingBatch | None:
        """Resolve a batch by its public id (batch worker entry point)."""
        return await self.find_one(public_id=public_id, deleted_at=None)

    async def list_failed(self, limit: int = 50) -> list[EmbeddingBatch]:
        """Failed batches eligible for the recovery path, oldest first."""
        stmt = (
            select(EmbeddingBatch)
            .where(
                EmbeddingBatch.status == EmbeddingBatchStatus.FAILED.value,
                EmbeddingBatch.deleted_at.is_(None),
            )
            .order_by(EmbeddingBatch.completed_at.asc(), EmbeddingBatch.id)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_completed(self, limit: int = 200) -> list[EmbeddingBatch]:
        """Recently completed batches (used to aggregate latency)."""
        stmt = (
            select(EmbeddingBatch)
            .where(
                EmbeddingBatch.status == EmbeddingBatchStatus.COMPLETED.value,
                EmbeddingBatch.deleted_at.is_(None),
            )
            .order_by(EmbeddingBatch.completed_at.desc(), EmbeddingBatch.id)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def reset_to_queued(
        self, batch: EmbeddingBatch, retries: int, max_retries: int
    ) -> EmbeddingBatch:
        """Requeue a failed batch for reprocessing (partial recovery).

        Idempotent: a batch already queued is left untouched.
        """
        if batch.status == EmbeddingBatchStatus.QUEUED.value:
            return batch
        batch.status = EmbeddingBatchStatus.QUEUED.value
        batch.completed_at = None
        batch.error_code = None
        batch.error_message = None
        result = dict(batch.result or {})
        result["retries"] = retries
        result["max_retries"] = max_retries
        batch.result = result
        await self._session.flush()
        await self._session.refresh(batch)
        return batch


class VectorIndexRepository(BaseRepository[VectorIndex]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, VectorIndex)

    async def get_for_presentation(
        self,
        presentation_id: uuid.UUID,
        index_type: str = VectorIndexType.PRESENTATION.value,
    ) -> VectorIndex | None:
        stmt = (
            select(VectorIndex)
            .where(
                VectorIndex.presentation_id == presentation_id,
                VectorIndex.index_type == index_type,
                VectorIndex.deleted_at.is_(None),
            )
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_for_presentation_or_raise(
        self,
        presentation_id: uuid.UUID,
        index_type: str = VectorIndexType.PRESENTATION.value,
    ) -> VectorIndex:
        index = await self.get_for_presentation(presentation_id, index_type)
        if index is None:
            raise NotFoundError(
                message="Vector index not found",
                details={"presentation_id": str(presentation_id), "index_type": index_type},
            )
        return index

    async def get_for_lesson(self, lesson_id: uuid.UUID) -> VectorIndex | None:
        stmt = (
            select(VectorIndex)
            .where(
                VectorIndex.lesson_id == lesson_id,
                VectorIndex.index_type == VectorIndexType.LESSON.value,
                VectorIndex.deleted_at.is_(None),
            )
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_building(self, limit: int = 10) -> list[VectorIndex]:
        stmt = (
            select(VectorIndex)
            .where(
                VectorIndex.status.in_(
                    [VectorIndexStatus.BUILDING.value, VectorIndexStatus.REBUILDING.value]
                ),
                VectorIndex.deleted_at.is_(None),
            )
            .order_by(VectorIndex.updated_at.asc(), VectorIndex.id)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_all(self, limit: int = 200) -> list[VectorIndex]:
        """All live indexes, oldest first (refresh/statistics workers)."""
        stmt = (
            select(VectorIndex)
            .where(VectorIndex.deleted_at.is_(None))
            .order_by(VectorIndex.created_at.asc(), VectorIndex.id)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def create_for_scope(
        self,
        *,
        presentation_id: uuid.UUID | None,
        lesson_id: uuid.UUID | None,
        index_type: str,
        strategy: str,
        chunk_size: int,
        chunk_overlap: int,
        max_chunk_tokens: int,
        provider: str | None,
        model: str | None,
        dimension: int,
        source_hash: str | None,
    ) -> VectorIndex:
        return await self.create(
            presentation_id=presentation_id,
            lesson_id=lesson_id,
            index_type=index_type,
            status=VectorIndexStatus.BUILDING.value,
            strategy=strategy,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            max_chunk_tokens=max_chunk_tokens,
            provider=provider,
            model=model,
            dimension=dimension,
            source_hash=source_hash,
            retry_state=EmbeddingRetryState.NONE.value,
        )

    async def mark_building(self, index: VectorIndex) -> VectorIndex:
        index.status = VectorIndexStatus.BUILDING.value
        index.started_at = datetime.now(UTC)
        index.error_message = None
        await self._session.flush()
        await self._session.refresh(index)
        return index

    async def mark_ready(
        self,
        index: VectorIndex,
        *,
        chunk_count: int,
        embedding_count: int,
        total_tokens: int,
        source_hash: str | None,
    ) -> VectorIndex:
        index.status = VectorIndexStatus.READY.value
        index.chunk_count = chunk_count
        index.embedding_count = embedding_count
        index.total_tokens = total_tokens
        index.source_hash = source_hash
        index.completed_at = datetime.now(UTC)
        index.error_message = None
        index.retry_state = EmbeddingRetryState.NONE.value
        await self._session.flush()
        await self._session.refresh(index)
        return index

    async def mark_failed(
        self, index: VectorIndex, error_message: str
    ) -> VectorIndex:
        index.status = VectorIndexStatus.FAILED.value
        index.completed_at = datetime.now(UTC)
        index.error_message = error_message
        await self._session.flush()
        await self._session.refresh(index)
        return index

    async def mark_rebuilding(self, index: VectorIndex) -> VectorIndex:
        index.status = VectorIndexStatus.REBUILDING.value
        index.started_at = datetime.now(UTC)
        index.error_message = None
        await self._session.flush()
        await self._session.refresh(index)
        return index

    async def bump_latest_version(self, index: VectorIndex) -> VectorIndex:
        index.latest_version += 1
        await self._session.flush()
        await self._session.refresh(index)
        return index


class VectorIndexVersionRepository(BaseRepository[VectorIndexVersion]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, VectorIndexVersion)

    async def create_version(
        self,
        index: VectorIndex,
        *,
        source_hash: str | None,
        chunk_count: int,
        embedding_count: int,
        total_tokens: int,
        config: dict[str, object] | None,
        changelog: dict[str, object] | None,
        meta: dict[str, object] | None = None,
    ) -> VectorIndexVersion:
        return await self.create(
            index_id=index.id,
            version=index.latest_version,
            source_hash=source_hash,
            chunk_count=chunk_count,
            embedding_count=embedding_count,
            total_tokens=total_tokens,
            config=config,
            changelog=changelog,
            meta=meta,
        )


class EmbeddingStatisticsRepository(BaseRepository[EmbeddingStatistics]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, EmbeddingStatistics)

    async def get_total(self, index_id: uuid.UUID) -> EmbeddingStatistics | None:
        return await self.find_one(
            index_id=index_id,
            period=EmbeddingStatisticsPeriod.TOTAL.value,
            stats_date=None,
        )

    async def get_daily(
        self, index_id: uuid.UUID, stats_date: date
    ) -> EmbeddingStatistics | None:
        return await self.find_one(
            index_id=index_id,
            period=EmbeddingStatisticsPeriod.DAILY.value,
            stats_date=stats_date,
        )

    async def upsert_total(
        self, index_id: uuid.UUID, values: dict[str, object]
    ) -> EmbeddingStatistics:
        row = await self.get_total(index_id)
        if row is None:
            row = await self.create(
                index_id=index_id,
                period=EmbeddingStatisticsPeriod.TOTAL.value,
                stats_date=None,
            )
        for key, value in values.items():
            if hasattr(row, key):
                setattr(row, key, value)
        await self._session.flush()
        await self._session.refresh(row)
        return row

    async def upsert_daily(
        self,
        index_id: uuid.UUID,
        stats_date: date,
        values: dict[str, object],
    ) -> EmbeddingStatistics:
        row = await self.get_daily(index_id, stats_date)
        if row is None:
            row = await self.create(
                index_id=index_id,
                period=EmbeddingStatisticsPeriod.DAILY.value,
                stats_date=stats_date,
            )
        for key, value in values.items():
            if hasattr(row, key):
                setattr(row, key, value)
        await self._session.flush()
        await self._session.refresh(row)
        return row

    async def list_for_index(
        self, index_id: uuid.UUID, period: str, limit: int = 30
    ) -> list[EmbeddingStatistics]:
        stmt = (
            select(EmbeddingStatistics)
            .where(
                EmbeddingStatistics.index_id == index_id,
                EmbeddingStatistics.period == period,
            )
            .order_by(EmbeddingStatistics.stats_date.desc(), EmbeddingStatistics.id)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class EmbeddingMetadataRepository(BaseRepository[EmbeddingMetadata]):
    """Lifecycle of ``EmbeddingMetadata`` rows (provider/model fingerprints)."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, EmbeddingMetadata)

    async def list_for_deleted_indexes(self, limit: int = 50) -> list[EmbeddingMetadata]:
        """Metadata rows whose owning index has been soft-deleted."""
        stmt = (
            select(EmbeddingMetadata)
            .join(VectorIndex, EmbeddingMetadata.index_id == VectorIndex.id)
            .where(
                EmbeddingMetadata.index_id.isnot(None),
                VectorIndex.deleted_at.isnot(None),
                EmbeddingMetadata.status == "active",
            )
            .order_by(EmbeddingMetadata.updated_at.asc(), EmbeddingMetadata.id)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def mark_obsolete(self, row: EmbeddingMetadata) -> EmbeddingMetadata:
        """Soft-invalidate a metadata row (cleanup worker)."""
        row.status = "obsolete"
        await self._session.flush()
        await self._session.refresh(row)
        return row
