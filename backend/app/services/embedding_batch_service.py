"""Embedding batch orchestration (Phase 4E.2).

Splits an embedding job's chunk scope into ordered batches, processes each batch
through ``EmbeddingService``, and aggregates per-batch progress into the owning
job so workers can resume cleanly after a failure.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings import create_embedding_provider
from app.ai.embeddings.base import EmbeddingProvider
from app.core.config import settings
from app.core.logging import get_logger
from app.database.unit_of_work import UnitOfWork
from app.models.embedding_batch import EmbeddingBatch
from app.models.embedding_job import EmbeddingJob
from app.repositories.rag_repository import (
    DocumentChunkRepository,
    EmbeddingBatchRepository,
    EmbeddingJobRepository,
)
from app.services.embedding_service import EmbeddingRunResult, EmbeddingService

logger = get_logger(__name__)


@dataclass
class BatchProcessingResult:
    """Outcome of processing a single batch."""

    batch_id: uuid.UUID
    sequence: int
    processed: int
    failed: int
    tokens_used: int
    latency_ms: float
    failures: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.processed + self.failed


class EmbeddingBatchService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow
        session: AsyncSession = uow.session
        self._jobs = EmbeddingJobRepository(session)
        self._batches = EmbeddingBatchRepository(session)
        self._chunks = DocumentChunkRepository(session)
        self._embeddings = EmbeddingService(uow)

    async def create_batches(
        self,
        job: EmbeddingJob,
        chunk_ids: list[uuid.UUID],
        *,
        batch_size: int | None = None,
    ) -> list[EmbeddingBatch]:
        """Slice chunk ids into ordered batches owned by ``job``."""
        resolved = batch_size or settings.EMBEDDING_BATCH_SIZE
        resolved = max(1, resolved)
        existing = await self._batches.list_for_job(job.id)
        sequence = max([batch.sequence for batch in existing], default=-1) + 1

        created: list[EmbeddingBatch] = []
        for start in range(0, len(chunk_ids), resolved):
            group = chunk_ids[start : start + resolved]
            created.append(
                await self._batches.create_batch(
                    job.id,
                    sequence=sequence,
                    total_items=len(group),
                    chunk_ids=group,
                )
            )
            sequence += 1
        return created

    async def process_batch(
        self,
        job: EmbeddingJob,
        batch: EmbeddingBatch,
        *,
        provider: EmbeddingProvider | None = None,
    ) -> BatchProcessingResult:
        """Embed a single batch and reflect its progress on the job."""
        await self._batches.mark_processing(batch)
        chunk_ids = self._batches.chunk_ids_for(batch)
        if not chunk_ids:
            await self._batches.mark_failed(
                batch, error_code="EMPTY_BATCH", error_message="Batch has no chunk ids"
            )
            return BatchProcessingResult(
                batch_id=batch.id,
                sequence=batch.sequence,
                processed=0,
                failed=0,
                tokens_used=0,
                latency_ms=0.0,
            )

        chunks = await self._chunks.list_by_ids(chunk_ids)
        result = await self._embeddings.embed_chunks(
            chunks,
            provider=provider or create_embedding_provider(),
        )
        summary = await self._finalize_batch(batch, result)
        await self._sync_job_progress(job)
        return summary

    async def process_batch_parallel(
        self,
        job: EmbeddingJob,
        batch: EmbeddingBatch,
        *,
        provider: EmbeddingProvider | None = None,
        parallelism: int | None = None,
    ) -> BatchProcessingResult:
        """Embed a batch with bounded-concurrent provider calls.

        The batch's chunks are split into provider ``max_batch_size`` groups
        which are embedded concurrently (bounded by ``parallelism``). Partial
        failures are aggregated, so a failed provider call in one group never
        blocks the others. Persistence stays sequential on the calling session.
        """
        await self._batches.mark_processing(batch)
        chunk_ids = self._batches.chunk_ids_for(batch)
        if not chunk_ids:
            await self._batches.mark_failed(
                batch, error_code="EMPTY_BATCH", error_message="Batch has no chunk ids"
            )
            return BatchProcessingResult(
                batch_id=batch.id,
                sequence=batch.sequence,
                processed=0,
                failed=0,
                tokens_used=0,
                latency_ms=0.0,
            )

        chunks = await self._chunks.list_by_ids(chunk_ids)
        resolved_provider = provider or create_embedding_provider()
        max_batch = resolved_provider.info().max_batch_size
        groups = [
            chunks[index : index + max_batch]
            for index in range(0, len(chunks), max_batch)
        ]
        result = await self._embeddings.embed_chunks_parallel(
            groups,
            provider=resolved_provider,
            parallelism=parallelism,
        )
        summary = await self._finalize_batch(batch, result)
        await self._sync_job_progress(job)
        return summary

    async def _finalize_batch(
        self, batch: EmbeddingBatch, result: EmbeddingRunResult
    ) -> BatchProcessingResult:
        batch.processed_items = result.processed
        batch.failed_items = result.failed
        if result.failed and result.processed == 0:
            batch = await self._batches.mark_failed(
                batch,
                error_code="EMBEDDING_FAILED",
                error_message="; ".join(result.failures) or "All items failed",
            )
        else:
            batch = await self._batches.mark_completed(
                batch,
                result={"tokens_used": result.tokens_used, "latency_ms": result.latency_ms},
            )
        return BatchProcessingResult(
            batch_id=batch.id,
            sequence=batch.sequence,
            processed=result.processed,
            failed=result.failed,
            tokens_used=result.tokens_used,
            latency_ms=result.latency_ms,
            failures=list(result.failures),
        )

    async def _sync_job_progress(self, job: EmbeddingJob) -> EmbeddingJob:
        batches = await self._batches.list_for_job(job.id)
        processed = sum(b.processed_items for b in batches)
        failed = sum(b.failed_items for b in batches)
        return await self._jobs.increment_progress(job, processed, failed)

    async def finalize_job(self, job: EmbeddingJob) -> EmbeddingJob:
        """Aggregate batch outcomes into the terminal job status."""
        batches = await self._batches.list_for_job(job.id)
        if not batches:
            return await self._jobs.mark_failed(
                job,
                error_code="NO_BATCHES",
                error_message="Job completed with no batches recorded",
            )

        processed = sum(b.processed_items for b in batches)
        failed = sum(b.failed_items for b in batches)
        all_completed = all(b.status == "completed" for b in batches)
        all_failed = all(b.status == "failed" for b in batches)

        if all_completed and failed == 0:
            return await self._jobs.mark_completed(
                job,
                result={"processed": processed, "failed": failed, "total": processed + failed},
            )
        if all_failed:
            return await self._jobs.mark_failed(
                job,
                error_code="EMBEDDING_FAILED",
                error_message="All batches failed; see batch rows for details",
            )
        return await self._jobs.mark_partial(
            job,
            processed,
            failed,
            result={"processed": processed, "failed": failed, "total": processed + failed},
        )

    async def resume_job(
        self,
        job: EmbeddingJob,
        *,
        provider: EmbeddingProvider | None = None,
    ) -> int:
        """Process all pending batches of a job (worker entry point)."""
        await self._jobs.mark_processing(job)
        pending = await self._batches.get_pending_for_job(job.id)
        for batch in pending:
            await self.process_batch(job, batch, provider=provider)
        await self.finalize_job(job)
        return len(pending)
