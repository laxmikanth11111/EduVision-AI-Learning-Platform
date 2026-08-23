"""Embedding statistics worker service (Phase 4E.1 + 4E.2, Checkpoint 5).

``EmbeddingStatisticsService`` produces the global embedding health snapshot:
per-index totals + daily rows (via ``EmbeddingIntegrityService``) and global
aggregates (chunk counts, version counts, provider/model usage, average
dimension, storage estimate, queue backlog, average batch latency) that are
exposed as Prometheus gauges for the monitoring dashboard.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings import create_embedding_provider
from app.core.config import settings
from app.core.logging import get_logger
from app.database.unit_of_work import UnitOfWork
from app.observability.metrics import metrics
from app.repositories.rag_repository import (
    DocumentChunkRepository,
    EmbeddingBatchRepository,
    EmbeddingJobRepository,
    EmbeddingRepository,
    VectorIndexRepository,
)
from app.services.embedding_integrity_service import EmbeddingIntegrityService

logger = get_logger(__name__)


@dataclass
class GlobalEmbeddingStats:
    total_chunks: int = 0
    pending_chunks: int = 0
    processed_chunks: int = 0
    failed_chunks: int = 0
    active_embeddings: int = 0
    superseded_embeddings: int = 0
    failed_embeddings: int = 0
    avg_dimension: float = 0.0
    storage_bytes: float = 0.0
    retry_sum: int = 0
    queue_backlog: int = 0
    indexes_updated: int = 0
    average_latency_ms: float = 0.0
    provider_usage: list[tuple[str, str, int]] = field(default_factory=list)
    provider: str = ""
    model: str = ""


class EmbeddingStatisticsService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow
        session: AsyncSession = uow.session
        self._chunks = DocumentChunkRepository(session)
        self._embeddings = EmbeddingRepository(session)
        self._jobs = EmbeddingJobRepository(session)
        self._batches = EmbeddingBatchRepository(session)
        self._indexes = VectorIndexRepository(session)
        self._integrity = EmbeddingIntegrityService(uow)

    async def build(self, *, limit: int | None = None) -> GlobalEmbeddingStats:
        """Compute per-index statistics and the global embedding snapshot."""
        indexes = await self._indexes.list_all(limit=limit or settings.EMBEDDING_MAINTENANCE_LIMIT)
        provider = create_embedding_provider()
        info = provider.info()

        stats = GlobalEmbeddingStats(
            provider=provider.name,
            model=info.model,
        )
        for index in indexes:
            if index.presentation_id is not None:
                try:
                    await self._integrity.record_statistics(
                        index,
                        provider=index.provider,
                        model=index.model,
                    )
                    stats.indexes_updated += 1
                except Exception as exc:  # noqa: BLE001 - one index must not fail the run
                    logger.warning(
                        "embedding_statistics_index_failed",
                        index_id=str(index.id),
                        error=str(exc),
                    )

        chunk_counts = await self._chunks.count_all_by_status()
        version_counts = await self._embeddings.count_all_by_status()
        stats.total_chunks = int(sum(chunk_counts.values()))
        stats.pending_chunks = int(chunk_counts.get("pending", 0))
        stats.processed_chunks = int(chunk_counts.get("processed", 0))
        stats.failed_chunks = int(chunk_counts.get("failed", 0))
        stats.active_embeddings = await self._embeddings.count_active_total()
        stats.superseded_embeddings = int(version_counts.get("superseded", 0))
        stats.failed_embeddings = int(version_counts.get("failed", 0))
        stats.avg_dimension = await self._embeddings.average_dimension()
        stats.storage_bytes = (
            round(stats.active_embeddings * stats.avg_dimension * 8.0, 2)
            if stats.avg_dimension
            else 0.0
        )
        stats.retry_sum = await self._chunks.sum_retries()
        stats.queue_backlog = await self._jobs.count(
            status="queued",
            deleted_at=None,
        )
        stats.provider_usage = await self._embeddings.count_by_provider_model()
        stats.average_latency_ms = await self._average_latency()

        self._emit_metrics(stats)
        await self._uow.flush()
        return stats

    async def _average_latency(self) -> float:
        batches = await self._batches.list_completed(
            limit=settings.EMBEDDING_MAINTENANCE_LIMIT
        )
        latencies: list[float] = []
        for batch in batches:
            raw = (batch.result or {}).get("latency_ms", 0.0)
            if isinstance(raw, (int, float)) and float(raw) > 0:
                latencies.append(float(raw))
        if not latencies:
            return 0.0
        return round(sum(latencies) / len(latencies), 2)

    def _emit_metrics(self, stats: GlobalEmbeddingStats) -> None:
        for provider, model, count in stats.provider_usage:
            metrics.set_gauge(
                "embedding_provider_usage_total",
                value=count,
                provider=provider,
                model=model,
            )
        metrics.set_gauge(
            "embedding_versions_total",
            value=stats.active_embeddings,
            status="active",
        )
        metrics.set_gauge(
            "embedding_versions_total",
            value=stats.superseded_embeddings,
            status="superseded",
        )
        metrics.set_gauge(
            "embedding_versions_total",
            value=stats.failed_embeddings,
            status="failed",
        )
        metrics.set_gauge("embedding_storage_bytes", value=stats.storage_bytes)
        metrics.set_gauge("embedding_dimension", value=stats.avg_dimension)
        metrics.set_gauge("embedding_queue_backlog", value=stats.queue_backlog)
        logger.info(
            "embedding_statistics_complete",
            indexes=stats.indexes_updated,
            active_embeddings=stats.active_embeddings,
            total_chunks=stats.total_chunks,
            storage_bytes=stats.storage_bytes,
            queue_backlog=stats.queue_backlog,
        )
