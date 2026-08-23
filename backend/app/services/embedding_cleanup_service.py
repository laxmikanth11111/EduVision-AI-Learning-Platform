"""Embedding cleanup worker service (Phase 4E.1 + 4E.2, Checkpoint 5).

``EmbeddingCleanupService`` is the scheduled housekeeping pass for the
embedding subsystem:

* orphan embeddings (active rows whose chunk was soft-deleted),
* obsolete embedding versions (superseded past the retention window),
* failed batches past their max requeue attempts (bounded recovery),
* expired queued/processing jobs (stale beyond the job deadline),
* stale metadata rows whose owning index was soft-deleted.

Everything is a soft delete / status transition; nothing is hard-removed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings import create_embedding_provider
from app.core.config import settings
from app.core.logging import get_logger
from app.database.unit_of_work import UnitOfWork
from app.models.embedding_batch import EmbeddingBatch
from app.observability.metrics import metrics
from app.repositories.rag_repository import (
    EmbeddingBatchRepository,
    EmbeddingJobRepository,
    EmbeddingMetadataRepository,
    EmbeddingRepository,
    VectorIndexRepository,
)
from shared.constants import EmbeddingJobStatus

logger = get_logger(__name__)


@dataclass
class CleanupReport:
    orphan_embeddings: int = 0
    obsolete_versions: int = 0
    batches_recovered: int = 0
    jobs_expired: int = 0
    metadata_obsolete: int = 0
    errors: list[str] = field(default_factory=list)


class EmbeddingCleanupService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow
        session: AsyncSession = uow.session
        self._embeddings = EmbeddingRepository(session)
        self._jobs = EmbeddingJobRepository(session)
        self._batches = EmbeddingBatchRepository(session)
        self._indexes = VectorIndexRepository(session)
        self._metadata = EmbeddingMetadataRepository(session)

    async def run(
        self,
        *,
        limit: int | None = None,
        obsolete_days: int | None = None,
    ) -> CleanupReport:
        """Execute one full cleanup pass, bounded by ``limit`` per concern."""
        report = CleanupReport()
        resolved_limit = limit or settings.EMBEDDING_MAINTENANCE_LIMIT

        report.orphan_embeddings += await self._cleanup_orphans(resolved_limit)
        report.obsolete_versions += await self._cleanup_obsolete(
            obsolete_days or settings.EMBEDDING_OBSOLETE_VERSION_DAYS, resolved_limit
        )
        report.batches_recovered += await self._recover_failed_batches(resolved_limit)
        report.jobs_expired += await self._reclaim_expired_jobs(resolved_limit)
        report.metadata_obsolete += await self._cleanup_metadata(resolved_limit)

        self._emit_metrics(report)
        await self._uow.flush()
        return report

    async def _cleanup_orphans(self, limit: int) -> int:
        provider = create_embedding_provider()
        info = provider.info()
        removed = 0
        for index in await self._indexes.list_all(limit=limit):
            if index.presentation_id is None:
                continue
            resolved_provider = index.provider or provider.name
            resolved_model = index.model or info.model
            if not (resolved_provider and resolved_model):
                continue
            orphans = await self._embeddings.list_orphans(
                index.presentation_id,
                resolved_provider,
                resolved_model,
                limit=limit,
            )
            if orphans:
                removed += await self._embeddings.soft_delete_many(orphans)
        return removed

    async def _cleanup_obsolete(self, obsolete_days: int, limit: int) -> int:
        older_than = datetime.now(UTC) - timedelta(days=obsolete_days)
        superseded = await self._embeddings.list_superseded(older_than, limit=limit)
        if not superseded:
            return 0
        return await self._embeddings.soft_delete_many(superseded)

    async def _recover_failed_batches(self, limit: int) -> int:
        recovered = 0
        for batch in await self._batches.list_failed(limit=limit):
            if not self._can_recover(batch):
                continue
            job = await self._jobs.get(batch.job_id)
            if job is None or job.status not in {
                EmbeddingJobStatus.QUEUED.value,
                EmbeddingJobStatus.PROCESSING.value,
                EmbeddingJobStatus.PARTIAL.value,
            }:
                continue
            retries = self._batch_retries(batch)
            if retries >= settings.EMBEDDING_BATCH_MAX_RETRIES:
                continue
            await self._batches.reset_to_queued(
                batch,
                retries=retries + 1,
                max_retries=settings.EMBEDDING_BATCH_MAX_RETRIES,
            )
            recovered += 1
        return recovered

    def _can_recover(self, batch: EmbeddingBatch) -> bool:
        return batch.error_code not in {"VALIDATION_ERROR", "JOB_TERMINATED"}

    @staticmethod
    def _batch_retries(batch: EmbeddingBatch) -> int:
        raw = (batch.result or {}).get("retries", 0)
        return int(raw) if isinstance(raw, (int, float, str)) else 0

    async def _reclaim_expired_jobs(self, limit: int) -> int:
        older_than = datetime.now(UTC) - timedelta(seconds=settings.EMBEDDING_JOB_STALE_SECONDS)
        expired = 0
        for job in await self._jobs.list_stale(older_than, limit=limit):
            await self._jobs.mark_failed(
                job,
                error_code="JOB_EXPIRED",
                error_message="Job exceeded its processing deadline and was reclaimed",
            )
            expired += 1
        return expired

    async def _cleanup_metadata(self, limit: int) -> int:
        marked = 0
        for row in await self._metadata.list_for_deleted_indexes(limit=limit):
            await self._metadata.mark_obsolete(row)
            marked += 1
        return marked

    def _emit_metrics(self, report: CleanupReport) -> None:
        metrics.increment(
            "embedding_cleanup_orphans_total", value=report.orphan_embeddings
        )
        metrics.increment(
            "embedding_cleanup_obsolete_total", value=report.obsolete_versions
        )
        metrics.increment(
            "embedding_cleanup_batches_recovered_total", value=report.batches_recovered
        )
        metrics.increment(
            "embedding_cleanup_jobs_expired_total", value=report.jobs_expired
        )
        metrics.increment(
            "embedding_cleanup_metadata_total", value=report.metadata_obsolete
        )
        logger.info(
            "embedding_cleanup_complete",
            orphans=report.orphan_embeddings,
            obsolete=report.obsolete_versions,
            recovered=report.batches_recovered,
            expired=report.jobs_expired,
            metadata=report.metadata_obsolete,
        )
