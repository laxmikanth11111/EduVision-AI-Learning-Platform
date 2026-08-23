"""Embedding worker tasks (Phase 4E.1 + 4E.2, Checkpoint 5).

Production background workers for the RAG embedding pipeline:

* ``embedding_generation_task``      — drives an embedding job: marks it
  processing, prepares its batch set (checkpoint resume) and dispatches one
  ``embedding_batch_task`` per batch.
* ``embedding_batch_task``           — embeds one batch with bounded-concurrent
  provider calls, then finalizes the owning job when it is the last batch.
* ``embedding_refresh_task``         — re-embeds drifted chunks (hash mismatch).
* ``embedding_cleanup_task``         — orphans/obsolete versions/expired jobs/
  failed-batch recovery/metadata housekeeping.
* ``embedding_statistics_task``      — per-index totals + daily rows and the
  global embedding snapshot (Prometheus gauges).

Every task: ``bind=True``, ``base=TaskWithDLQ``, ``acks_late=True``,
``max_retries=2`` with exponential backoff, a fresh ``UnitOfWork``, structured
logging and metrics, and best-effort dispatch via ``safe_dispatch``.
"""

from __future__ import annotations

import time
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger
from app.database.unit_of_work import UnitOfWork
from app.observability.metrics import metrics
from app.workers.celery_app import celery_app
from app.workers.tasks import TaskWithDLQ, _run_async, retry_backoff, safe_dispatch
from shared.constants import EmbeddingBatchStatus, EmbeddingJobStatus

logger = get_logger(__name__)


def _task_started(task_name: str) -> None:
    metrics.increment("embedding_tasks_started_total", task_name=task_name)


def _task_completed(task_name: str) -> None:
    metrics.increment("embedding_tasks_completed_total", task_name=task_name)


def _task_failed(task_name: str) -> None:
    metrics.increment("embedding_tasks_failed_total", task_name=task_name)


def _task_seconds(task_name: str, elapsed: float) -> None:
    metrics.increment(
        "embedding_processing_seconds_total",
        value=max(0.0, elapsed),
        task_name=task_name,
    )


def _task_retried(task_name: str) -> None:
    metrics.increment("embedding_retries_total", task_name=task_name)


# ── RAG indexing trigger (F2-13 Phase 1) ─────────────────────────────────────


async def _rag_indexing_async(scope: str, public_id: str) -> dict[str, object]:
    from app.services.rag_indexing_service import RagIndexingService

    async with UnitOfWork() as uow:
        service = RagIndexingService(uow)
        if scope == "presentation":
            return await service.index_presentation(public_id)
        if scope == "lesson":
            return await service.index_lesson(public_id)
        raise ValueError(f"Unknown RAG indexing scope: {scope}")


@celery_app.task(  # type: ignore[untyped-decorator]
    bind=True,
    base=TaskWithDLQ,
    name="eduvision.rag.index",
    max_retries=2,
    default_retry_delay=settings.CELERY_TASK_RETRY_DELAY,
    acks_late=True,
)
def rag_indexing_task(self: Any, scope: str, public_id: str) -> dict[str, object]:
    """Chunk a scope and enqueue its embedding job after content landed.

    Triggered by source extraction (presentation scope) and AI lesson
    generation (lesson scope). Deterministic guard failures (scope missing or
    not ready) are logged and acknowledged — retrying cannot fix them — while
    unexpected failures retry and fall through to the dead-letter queue.
    """
    from app.services.rag_indexing_service import RagIndexingError

    task_name = "eduvision.rag.index"
    _task_started(task_name)
    started = time.monotonic()
    logger.info("rag_indexing_task_started", scope=scope, entity_id=public_id)
    try:
        result = _run_async(_rag_indexing_async(scope, public_id))
        _task_completed(task_name)
        _task_seconds(task_name, time.monotonic() - started)
        logger.info(
            "rag_indexing_task_completed",
            scope=scope,
            entity_id=public_id,
            skipped=result.get("skipped", False),
            chunks=result.get("chunks", 0),
            job_id=result.get("job_id"),
            index_id=result.get("index_id"),
        )
        return result
    except RagIndexingError as exc:
        _task_failed(task_name)
        logger.error(
            "rag_indexing_task_guard_failed",
            scope=scope,
            entity_id=public_id,
            reason=str(exc),
        )
        return {
            "scope": scope,
            "public_id": public_id,
            "skipped": True,
            "error": str(exc),
        }
    except Exception as exc:
        _task_failed(task_name)
        logger.exception("rag_indexing_task_failed", scope=scope, entity_id=public_id)
        _task_retried(task_name)
        raise self.retry(exc=exc, countdown=retry_backoff(self)) from exc


# ── Generation ────────────────────────────────────────────────────────────────


async def _embedding_generation_async(public_id: str) -> dict[str, Any]:
    from app.services.embedding_pipeline_service import EmbeddingPipelineService

    async with UnitOfWork() as uow:
        pipeline = EmbeddingPipelineService(uow)
        job = await pipeline.get_job(public_id)
        if job is None:
            raise RuntimeError(f"Embedding job not found: {public_id}")
        if job.status != EmbeddingJobStatus.QUEUED.value:
            return {"status": "skipped", "reason": f"job_status={job.status}"}

        await pipeline.start_job(job)
        batches = await pipeline.prepare_batches(job)
        dispatched = 0
        for batch in batches:
            if batch.status == EmbeddingBatchStatus.QUEUED.value:
                safe_dispatch(embedding_batch_task, job.public_id, batch.public_id)
                dispatched += 1
        if dispatched:
            metrics.increment(
                "embedding_generation_batches_dispatched_total", value=dispatched
            )

        if not batches:
            result = await pipeline.maybe_finalize(job)
            metrics.increment(
                "embedding_generation_jobs_total", status=result.job_status
            )
            return {
                "status": result.job_status,
                "batches_dispatched": 0,
                "processed": result.processed,
                "failed": result.failed,
            }
        return {"status": "processing", "batches_dispatched": dispatched}


@celery_app.task(  # type: ignore[untyped-decorator]
    bind=True,
    base=TaskWithDLQ,
    name="eduvision.embedding.generate",
    max_retries=2,
    default_retry_delay=settings.CELERY_TASK_RETRY_DELAY,
    acks_late=True,
)
def embedding_generation_task(self: Any, public_id: str) -> dict[str, Any]:
    task_name = "eduvision.embedding.generate"
    _task_started(task_name)
    started = time.monotonic()
    logger.info("embedding_generation_task_started", job_id=public_id)
    try:
        result = _run_async(_embedding_generation_async(public_id))
        _task_completed(task_name)
        _task_seconds(task_name, time.monotonic() - started)
        logger.info(
            "embedding_generation_task_completed",
            job_id=public_id,
            status=result.get("status"),
            batches=result.get("batches_dispatched", 0),
        )
        return result
    except Exception as e:
        _task_failed(task_name)
        logger.exception("embedding_generation_task_failed", job_id=public_id)
        _task_retried(task_name)
        raise self.retry(exc=e, countdown=retry_backoff(self)) from e


# ── Batch processing ──────────────────────────────────────────────────────────


async def _embedding_batch_async(job_public_id: str, batch_public_id: str) -> dict[str, Any]:
    from app.services.embedding_pipeline_service import EmbeddingPipelineService

    async with UnitOfWork() as uow:
        pipeline = EmbeddingPipelineService(uow)
        job = await pipeline.get_job(job_public_id)
        if job is None:
            raise RuntimeError(f"Embedding job not found: {job_public_id}")
        batch = await pipeline.get_batch(batch_public_id)
        if batch is None:
            raise RuntimeError(f"Embedding batch not found: {batch_public_id}")
        if batch.job_id != job.id:
            raise RuntimeError("Embedding batch does not belong to the embedding job")
        if batch.status != EmbeddingBatchStatus.QUEUED.value:
            return {"status": "skipped", "reason": f"batch_status={batch.status}"}

        result = await pipeline.process_batch(job, batch)
        if result.failed and result.processed == 0:
            metrics.increment("embedding_batches_failed_total", job_id=str(job.id))
        else:
            metrics.increment("embedding_batches_processed_total", job_id=str(job.id))

        finalize = await pipeline.maybe_finalize(job)
        if finalize.job_status in {
            EmbeddingJobStatus.COMPLETED.value,
            EmbeddingJobStatus.FAILED.value,
            EmbeddingJobStatus.CANCELLED.value,
        }:
            metrics.increment(
                "embedding_generation_jobs_total", status=finalize.job_status
            )
            logger.info(
                "embedding_job_finalized",
                job_id=str(job.id),
                status=finalize.job_status,
                processed=finalize.processed,
                failed=finalize.failed,
            )
        return {
            "status": "processed",
            "batch_id": batch_public_id,
            "processed": result.processed,
            "failed": result.failed,
            "tokens_used": result.tokens_used,
        }


@celery_app.task(  # type: ignore[untyped-decorator]
    bind=True,
    base=TaskWithDLQ,
    name="eduvision.embedding.batch",
    max_retries=2,
    default_retry_delay=settings.CELERY_TASK_RETRY_DELAY,
    acks_late=True,
)
def embedding_batch_task(self: Any, job_public_id: str, batch_public_id: str) -> dict[str, Any]:
    task_name = "eduvision.embedding.batch"
    _task_started(task_name)
    started = time.monotonic()
    logger.info(
        "embedding_batch_task_started",
        job_id=job_public_id,
        batch_id=batch_public_id,
    )
    try:
        result = _run_async(_embedding_batch_async(job_public_id, batch_public_id))
        _task_completed(task_name)
        _task_seconds(task_name, time.monotonic() - started)
        logger.info(
            "embedding_batch_task_completed",
            job_id=job_public_id,
            batch_id=batch_public_id,
            status=result.get("status"),
        )
        return result
    except Exception as e:
        _task_failed(task_name)
        logger.exception(
            "embedding_batch_task_failed",
            job_id=job_public_id,
            batch_id=batch_public_id,
        )
        _task_retried(task_name)
        raise self.retry(exc=e, countdown=retry_backoff(self)) from e


# ── Refresh ───────────────────────────────────────────────────────────────────


async def _embedding_refresh_async(limit: int | None) -> int:
    from app.services.embedding_refresh_service import EmbeddingRefreshService

    async with UnitOfWork() as uow:
        reports = await EmbeddingRefreshService(uow).run(limit=limit)
    return len(reports)


@celery_app.task(  # type: ignore[untyped-decorator]
    bind=True,
    base=TaskWithDLQ,
    name="eduvision.embedding.refresh",
    max_retries=2,
    default_retry_delay=settings.CELERY_TASK_RETRY_DELAY,
    acks_late=True,
)
def embedding_refresh_task(self: Any, limit: int | None = None) -> int:
    task_name = "eduvision.embedding.refresh"
    _task_started(task_name)
    started = time.monotonic()
    logger.info("embedding_refresh_task_started")
    try:
        count = _run_async(_embedding_refresh_async(limit))
        _task_completed(task_name)
        _task_seconds(task_name, time.monotonic() - started)
        logger.info("embedding_refresh_task_completed", indexes=count)
        return count
    except Exception as e:
        _task_failed(task_name)
        logger.exception("embedding_refresh_task_failed")
        _task_retried(task_name)
        raise self.retry(exc=e, countdown=retry_backoff(self)) from e


# ── Cleanup ───────────────────────────────────────────────────────────────────


async def _embedding_cleanup_async(limit: int | None) -> dict[str, int]:
    from app.services.embedding_cleanup_service import EmbeddingCleanupService

    async with UnitOfWork() as uow:
        report = await EmbeddingCleanupService(uow).run(limit=limit)
    return {
        "orphan_embeddings": report.orphan_embeddings,
        "obsolete_versions": report.obsolete_versions,
        "batches_recovered": report.batches_recovered,
        "jobs_expired": report.jobs_expired,
        "metadata_obsolete": report.metadata_obsolete,
    }


@celery_app.task(  # type: ignore[untyped-decorator]
    bind=True,
    base=TaskWithDLQ,
    name="eduvision.embedding.cleanup",
    max_retries=2,
    default_retry_delay=settings.CELERY_TASK_RETRY_DELAY,
    acks_late=True,
)
def embedding_cleanup_task(self: Any, limit: int | None = None) -> dict[str, int]:
    task_name = "eduvision.embedding.cleanup"
    _task_started(task_name)
    started = time.monotonic()
    logger.info("embedding_cleanup_task_started")
    try:
        result = _run_async(_embedding_cleanup_async(limit))
        _task_completed(task_name)
        _task_seconds(task_name, time.monotonic() - started)
        logger.info("embedding_cleanup_task_completed", **result)
        return result
    except Exception as e:
        _task_failed(task_name)
        logger.exception("embedding_cleanup_task_failed")
        _task_retried(task_name)
        raise self.retry(exc=e, countdown=retry_backoff(self)) from e


# ── Statistics ────────────────────────────────────────────────────────────────


async def _embedding_statistics_async(limit: int | None) -> int:
    from app.services.embedding_statistics_service import EmbeddingStatisticsService

    async with UnitOfWork() as uow:
        stats = await EmbeddingStatisticsService(uow).build(limit=limit)
    return stats.indexes_updated


@celery_app.task(  # type: ignore[untyped-decorator]
    bind=True,
    base=TaskWithDLQ,
    name="eduvision.embedding.statistics",
    max_retries=2,
    default_retry_delay=settings.CELERY_TASK_RETRY_DELAY,
    acks_late=True,
)
def embedding_statistics_task(self: Any, limit: int | None = None) -> int:
    task_name = "eduvision.embedding.statistics"
    _task_started(task_name)
    started = time.monotonic()
    logger.info("embedding_statistics_task_started")
    try:
        count = _run_async(_embedding_statistics_async(limit))
        _task_completed(task_name)
        _task_seconds(task_name, time.monotonic() - started)
        logger.info("embedding_statistics_task_completed", indexes=count)
        return count
    except Exception as e:
        _task_failed(task_name)
        logger.exception("embedding_statistics_task_failed")
        _task_retried(task_name)
        raise self.retry(exc=e, countdown=retry_backoff(self)) from e
