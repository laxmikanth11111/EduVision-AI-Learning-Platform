"""Embedding worker pipeline orchestration (Phase 4E.1 + 4E.2, Checkpoint 5).

Thin orchestration layer on top of the Phase 4E.2 batch/version services used
by the generation and batch workers:

* ``prepare_batches`` slices a job's chunk scope into ordered batches
  (idempotent — existing batches are reused, enabling checkpoint resume).
* ``process_batch`` embeds a single batch with bounded-concurrent provider
  calls and reflects progress on the owning job.
* ``maybe_finalize`` aggregates batch outcomes into the terminal job status and
  finalizes the owning index (ready + version record + statistics) only once
  no pending batches remain.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings.base import EmbeddingProvider
from app.core.config import settings
from app.core.logging import get_logger
from app.database.unit_of_work import UnitOfWork
from app.models.embedding_batch import EmbeddingBatch
from app.models.embedding_job import EmbeddingJob
from app.models.vector_index import VectorIndex
from app.repositories.rag_repository import (
    DocumentChunkRepository,
    EmbeddingBatchRepository,
    EmbeddingJobRepository,
    VectorIndexRepository,
    VectorIndexVersionRepository,
)
from app.services.embedding_batch_service import (
    BatchProcessingResult,
    EmbeddingBatchService,
)
from app.services.embedding_integrity_service import EmbeddingIntegrityService
from shared.constants import EmbeddingJobStatus

logger = get_logger(__name__)


@dataclass
class JobFinalizeResult:
    """Outcome of a job finalization pass (job + index status, version)."""

    job_status: str
    index_status: str | None = None
    version: int | None = None
    processed: int = 0
    failed: int = 0
    tokens_used: int = 0


class EmbeddingPipelineService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow
        session: AsyncSession = uow.session
        self._jobs = EmbeddingJobRepository(session)
        self._batches = EmbeddingBatchRepository(session)
        self._chunks = DocumentChunkRepository(session)
        self._indexes = VectorIndexRepository(session)
        self._index_versions = VectorIndexVersionRepository(session)
        self._batch_service = EmbeddingBatchService(uow)
        self._integrity = EmbeddingIntegrityService(uow)

    async def get_job(self, public_id: str) -> EmbeddingJob | None:
        return await self._jobs.get_by_public_id(public_id)

    async def get_batch(self, public_id: str) -> EmbeddingBatch | None:
        return await self._batches.get_by_public_id(public_id)

    async def start_job(self, job: EmbeddingJob) -> EmbeddingJob:
        """Mark a queued job as processing (idempotent transition)."""
        if job.status != EmbeddingJobStatus.QUEUED.value:
            return job
        return await self._jobs.mark_processing(job)

    async def _resolve_provider_model(self, job: EmbeddingJob) -> tuple[str, str]:
        provider = ""
        model = ""
        if job.index_id is not None:
            index = await self._indexes.get(job.index_id)
            if index is not None:
                provider = index.provider or ""
                model = index.model or ""
        return (
            provider or settings.EMBEDDING_PROVIDER or settings.AI_PROVIDER or "",
            model or settings.EMBEDDING_MODEL or settings.AI_MODEL or "",
        )

    async def prepare_batches(
        self,
        job: EmbeddingJob,
        *,
        batch_size: int | None = None,
    ) -> list[EmbeddingBatch]:
        """Create the job's batch set from its chunk scope if none exist.

        Idempotent: returns the existing batches when present, so a restarted
        worker resumes exactly where the interrupted run stopped (checkpoint
        resume on the batch granularity).
        """
        existing = await self._batches.list_for_job(job.id)
        if existing:
            return existing

        provider, model = await self._resolve_provider_model(job)
        limit = settings.MAX_EMBEDDING_QUEUE
        if job.presentation_id is not None:
            chunks = await self._chunks.list_unembedded(
                job.presentation_id, provider, model, limit=limit
            )
        elif job.lesson_id is not None:
            chunks = await self._chunks.list_unembedded_for_lesson(
                job.lesson_id, provider, model, limit=limit
            )
        else:
            logger.warning("embedding_job_no_scope", job_id=str(job.id))
            return []

        chunk_ids = [chunk.id for chunk in chunks]
        if not chunk_ids:
            return []

        batches = await self._batch_service.create_batches(
            job, chunk_ids, batch_size=batch_size
        )
        if job.total_items == 0:
            job.total_items = sum(batch.total_items for batch in batches)
        logger.info(
            "embedding_job_batches_created",
            job_id=str(job.id),
            batches=len(batches),
            chunks=len(chunk_ids),
        )
        return batches

    async def process_batch(
        self,
        job: EmbeddingJob,
        batch: EmbeddingBatch,
        *,
        provider: EmbeddingProvider | None = None,
        parallelism: int | None = None,
    ) -> BatchProcessingResult:
        """Embed one batch with bounded-concurrent provider calls."""
        return await self._batch_service.process_batch_parallel(
            job,
            batch,
            provider=provider,
            parallelism=parallelism,
        )

    async def has_pending_batches(self, job: EmbeddingJob) -> bool:
        pending = await self._batches.get_pending_for_job(job.id, limit=1)
        return bool(pending)

    async def maybe_finalize(self, job: EmbeddingJob) -> JobFinalizeResult:
        """Aggregate batch outcomes and finalize the job + index when done.

        Returns ``None``-equivalent (empty finalize result) when the job still
        has pending batches or is already terminal.
        """
        if job.status in {
            EmbeddingJobStatus.COMPLETED.value,
            EmbeddingJobStatus.FAILED.value,
            EmbeddingJobStatus.CANCELLED.value,
        }:
            return JobFinalizeResult(job_status=job.status)
        if await self.has_pending_batches(job):
            return JobFinalizeResult(job_status=job.status)

        batches = await self._batches.list_for_job(job.id)
        processed = sum(batch.processed_items for batch in batches)
        failed = sum(batch.failed_items for batch in batches)

        if not batches:
            if job.total_items == 0:
                await self._jobs.mark_completed(
                    job, {"processed": 0, "failed": 0, "total": 0}
                )
            else:
                await self._jobs.mark_failed(
                    job,
                    error_code="NO_BATCHES",
                    error_message="Job completed with no batches recorded",
                )
        else:
            await self._batch_service.finalize_job(job)

        result = await self.finalize_index(job, processed=processed, failed=failed)
        await self._uow.flush()
        return result

    async def finalize_index(
        self,
        job: EmbeddingJob,
        *,
        processed: int,
        failed: int,
    ) -> JobFinalizeResult:
        """Reflect the job outcome on its index: status, version, statistics."""
        base = JobFinalizeResult(
            job_status=job.status,
            processed=processed,
            failed=failed,
            tokens_used=0,
        )
        if job.index_id is None:
            return base

        index = await self._indexes.get(job.index_id)
        if index is None:
            return base

        batches = await self._batches.list_for_job(job.id)
        tokens_used = self._sum_batch_tokens(batches)
        base.tokens_used = tokens_used

        if job.status == EmbeddingJobStatus.COMPLETED.value:
            index = await self._indexes.mark_ready(
                index,
                chunk_count=processed,
                embedding_count=processed,
                total_tokens=tokens_used,
                source_hash=index.source_hash,
            )
            await self._indexes.bump_latest_version(index)
            await self._index_versions.create_version(
                index,
                source_hash=index.source_hash,
                chunk_count=processed,
                embedding_count=processed,
                total_tokens=tokens_used,
                config=index.config,
                changelog={
                    "job_type": job.job_type,
                    "processed": processed,
                    "failed": failed,
                },
            )
            base.version = index.latest_version
            base.index_status = index.status
        elif job.status == EmbeddingJobStatus.FAILED.value:
            index = await self._indexes.mark_failed(
                index, job.error_message or "Embedding job failed"
            )
            base.index_status = index.status
        else:
            base.index_status = index.status

        await self._record_statistics(index)
        return base

    async def _record_statistics(self, index: VectorIndex) -> None:
        if index.presentation_id is None:
            return
        try:
            await self._integrity.record_statistics(
                index,
                provider=index.provider,
                model=index.model,
            )
        except Exception as exc:  # noqa: BLE001 - stats must never fail the job
            logger.warning(
                "embedding_statistics_record_failed",
                index_id=str(index.id),
                error=str(exc),
            )

    @staticmethod
    def _sum_batch_tokens(batches: list[EmbeddingBatch]) -> int:
        total = 0
        for batch in batches:
            result = batch.result or {}
            tokens = result.get("tokens_used")
            if isinstance(tokens, (int, float)):
                total += int(tokens)
        return total
