"""Embedding integrity and statistics (Phase 4E.2).

Snapshots pipeline health for a scope: how many chunks are embedded, pending,
failed, stale (content hash changed since embedding) or orphaned, plus a
composite checksum validator for individual embedding rows.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.database.unit_of_work import UnitOfWork
from app.models.chunk_embedding import ChunkEmbedding
from app.models.embedding_statistics import EmbeddingStatistics
from app.models.vector_index import VectorIndex
from app.repositories.rag_repository import (
    DocumentChunkRepository,
    EmbeddingRepository,
    EmbeddingStatisticsRepository,
)
from app.services.embedding_service import embedding_checksum

logger = get_logger(__name__)


@dataclass
class IntegrityReport:
    """Snapshot of embedding health for a single scope."""

    total_chunks: int
    embedded_chunks: int
    pending_chunks: int
    failed_chunks: int
    stale_chunks: int
    orphan_embeddings: int
    duplicate_embeddings: int

    @property
    def coverage(self) -> float:
        """Fraction of chunks currently embedded (0..1)."""
        if self.total_chunks == 0:
            return 0.0
        return round(self.embedded_chunks / self.total_chunks, 4)


class EmbeddingIntegrityService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow
        session: AsyncSession = uow.session
        self._chunks = DocumentChunkRepository(session)
        self._embeddings = EmbeddingRepository(session)
        self._stats = EmbeddingStatisticsRepository(session)

    def verify_embedding(
        self,
        embedding: ChunkEmbedding,
        *,
        chunk_hash: str | None = None,
    ) -> bool:
        """Recompute the checksum of an embedding and compare it to storage.

        ``chunk_hash`` defaults to the hash captured in the embedding's own
        metadata at publish time.
        """
        resolved = chunk_hash or str((embedding.meta or {}).get("chunk_hash") or "")
        recomputed = embedding_checksum(
            resolved,
            embedding.embedding_hash or "",
            embedding.model,
            embedding.dimension,
        )
        return bool(embedding.checksum) and recomputed == embedding.checksum

    async def collect(
        self,
        presentation_id: uuid.UUID,
        provider: str,
        model: str,
    ) -> IntegrityReport:
        """Gather the embedding health counters for a presentation scope."""
        counts = await self._chunks.count_by_status(presentation_id)
        embedded = await self._embeddings.count_active_for_scope(
            presentation_id, provider, model
        )
        orphans = await self._embeddings.count_orphans(presentation_id, provider, model)

        pairs = await self._chunks.list_embedded_pairs(
            presentation_id, provider, model, limit=200
        )
        stale = sum(
            1
            for chunk, embedding in pairs
            if (embedding.meta or {}).get("chunk_hash") != chunk.chunk_hash
        )
        hashes = [e.embedding_hash for _, e in pairs if e.embedding_hash]
        duplicates = len(hashes) - len(set(hashes))

        return IntegrityReport(
            total_chunks=sum(counts.values()),
            embedded_chunks=embedded,
            pending_chunks=counts.get("pending", 0),
            failed_chunks=counts.get("failed", 0),
            stale_chunks=stale,
            orphan_embeddings=orphans,
            duplicate_embeddings=max(0, duplicates),
        )

    async def record_statistics(
        self,
        index: VectorIndex,
        *,
        provider: str | None = None,
        model: str | None = None,
    ) -> EmbeddingStatistics:
        """Refresh the total and daily statistics rows for an index."""
        if index.presentation_id is None:
            raise ValueError("Index statistics require a presentation scope")

        resolved_provider = provider or index.provider or ""
        resolved_model = model or index.model or ""
        report = await self.collect(index.presentation_id, resolved_provider, resolved_model)

        pairs = await self._chunks.list_embedded_pairs(
            index.presentation_id, resolved_provider, resolved_model, limit=200
        )
        total_tokens = sum(chunk.token_count for chunk, _ in pairs)
        avg_tokens = (
            round(total_tokens / len(pairs), 2) if pairs else 0.0
        )
        values: dict[str, object] = {
            "total_chunks": report.total_chunks,
            "embedded_chunks": report.embedded_chunks,
            "pending_chunks": report.pending_chunks,
            "failed_chunks": report.failed_chunks,
            "stale_chunks": report.stale_chunks,
            "orphan_embeddings": report.orphan_embeddings,
            "duplicate_embeddings": report.duplicate_embeddings,
            "total_embeddings_generated": report.embedded_chunks,
            "total_embedding_failures": report.failed_chunks,
            "avg_dimension": index.dimension,
            "avg_tokens_per_chunk": avg_tokens,
            "status": "ready",
        }

        await self._stats.upsert_total(index.id, values)
        await self._stats.upsert_daily(index.id, _today(), values)
        row = await self._stats.get_total(index.id)
        if row is None:
            raise RuntimeError("Embedding statistics row was not persisted")
        return row


def _today() -> date:
    return datetime.now(UTC).date()
