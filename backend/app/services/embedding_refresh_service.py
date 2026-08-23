"""Embedding refresh worker service (Phase 4E.1 + 4E.2, Checkpoint 5).

``EmbeddingRefreshService`` detects chunks whose stored embedding no longer
matches the current chunk content (drift detection via ``chunk_hash`` vs the
embedding's recorded ``meta.chunk_hash``), re-embeds them with the provider,
and publishes a new index version + statistics snapshot for the run.

Refresh never rebuilds entire scopes — only drifted chunks — so a provider
model change or a small content edit stays cheap.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings import create_embedding_provider
from app.ai.embeddings.base import EmbeddingProvider
from app.core.config import settings
from app.core.logging import get_logger
from app.database.unit_of_work import UnitOfWork
from app.models.chunk_embedding import ChunkEmbedding
from app.models.document_chunk import DocumentChunk
from app.models.vector_index import VectorIndex
from app.observability.metrics import metrics
from app.repositories.rag_repository import (
    DocumentChunkRepository,
    VectorIndexRepository,
    VectorIndexVersionRepository,
)
from app.services.embedding_integrity_service import EmbeddingIntegrityService
from app.services.embedding_service import EmbeddingService

logger = get_logger(__name__)


@dataclass
class IndexRefreshReport:
    index_id: uuid.UUID | None
    checked: int = 0
    refreshed: int = 0
    failed: int = 0
    tokens_used: int = 0
    version: int | None = None


class EmbeddingRefreshService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow
        session: AsyncSession = uow.session
        self._chunks = DocumentChunkRepository(session)
        self._indexes = VectorIndexRepository(session)
        self._index_versions = VectorIndexVersionRepository(session)
        self._embeddings = EmbeddingService(uow)
        self._integrity = EmbeddingIntegrityService(uow)

    async def run(
        self,
        *,
        limit: int | None = None,
        provider: EmbeddingProvider | None = None,
    ) -> list[IndexRefreshReport]:
        """Refresh drifted chunks across indexes (bounded by ``limit``)."""
        indexes = await self._indexes.list_all(limit=limit or settings.EMBEDDING_MAINTENANCE_LIMIT)
        resolved_provider = provider or create_embedding_provider()
        info = resolved_provider.info()

        reports: list[IndexRefreshReport] = []
        for index in indexes:
            if index.presentation_id is None and index.lesson_id is None:
                continue
            if not (index.provider or index.model):
                continue
            report = await self._refresh_index(index, resolved_provider, info.model)
            if report.refreshed or report.checked:
                reports.append(report)
            await self._uow.flush()
        return reports

    async def _refresh_index(
        self,
        index: VectorIndex,
        provider: EmbeddingProvider,
        model: str,
    ) -> IndexRefreshReport:
        report = IndexRefreshReport(index_id=index.id)
        resolved_provider = index.provider or provider.name
        resolved_model = index.model or model

        pairs = await self._list_pairs(index, resolved_provider, resolved_model)
        report.checked = len(pairs)
        stale = [
            chunk
            for chunk, embedding in pairs
            if (embedding.meta or {}).get("chunk_hash") != chunk.chunk_hash
        ]
        if not stale:
            return report

        metrics.increment("embedding_refresh_stale_total", value=len(stale))
        result = await self._embeddings.embed_chunks(
            stale,
            provider=provider,
            batch_size=provider.info().max_batch_size,
        )
        report.refreshed = result.processed
        report.failed = result.failed
        report.tokens_used = result.tokens_used
        metrics.increment("embedding_refresh_embedded_total", value=result.processed)
        if result.failed:
            logger.warning(
                "embedding_refresh_partial_failure",
                index_id=str(index.id),
                refreshed=result.processed,
                failed=result.failed,
            )

        index = await self._indexes.mark_ready(
            index,
            chunk_count=len(pairs) + await self._pending_below(index),
            embedding_count=report.refreshed,
            total_tokens=result.tokens_used,
            source_hash=index.source_hash,
        )
        await self._indexes.bump_latest_version(index)
        await self._index_versions.create_version(
            index,
            source_hash=index.source_hash,
            chunk_count=len(pairs),
            embedding_count=report.refreshed,
            total_tokens=result.tokens_used,
            config=index.config,
            changelog={
                "action": "refresh",
                "checked": report.checked,
                "refreshed": report.refreshed,
                "failed": report.failed,
            },
        )
        report.version = index.latest_version

        if index.presentation_id is not None:
            try:
                await self._integrity.record_statistics(
                    index,
                    provider=resolved_provider,
                    model=resolved_model,
                )
            except Exception as exc:  # noqa: BLE001 - stats never fail refresh
                logger.warning(
                    "embedding_statistics_record_failed",
                    index_id=str(index.id),
                    error=str(exc),
                )

        logger.info(
            "embedding_index_refreshed",
            index_id=str(index.id),
            checked=report.checked,
            refreshed=report.refreshed,
            failed=report.failed,
            version=report.version,
        )
        return report

    async def _list_pairs(
        self, index: VectorIndex, provider: str, model: str
    ) -> list[tuple[DocumentChunk, ChunkEmbedding]]:
        if index.presentation_id is not None:
            return await self._chunks.list_embedded_pairs(
                index.presentation_id, provider, model, limit=200
            )
        if index.lesson_id is None:
            return []
        return await self._chunks.list_embedded_pairs_for_lesson(
            index.lesson_id, provider, model, limit=200
        )

    async def _pending_below(self, index: VectorIndex) -> int:
        if index.presentation_id is not None:
            counts = await self._chunks.count_by_status(index.presentation_id)
        else:
            counts = {"pending": 0}
        return int(counts.get("pending", 0))
