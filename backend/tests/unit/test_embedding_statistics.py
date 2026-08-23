from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.unit_of_work import UnitOfWork
from app.models.document_chunk import DocumentChunk
from app.models.vector_index import VectorIndex
from app.repositories.rag_repository import (
    DocumentChunkRepository,
    EmbeddingBatchRepository,
    EmbeddingJobRepository,
    EmbeddingRepository,
    VectorIndexRepository,
)
from app.services.embedding_statistics_service import EmbeddingStatisticsService
from shared.constants import EmbeddingJobStatus

PROVIDER = "local"
MODEL = "local-embedding-test"
DIMENSION = 8


@pytest.fixture(autouse=True)
def _embedding_provider_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "EMBEDDING_PROVIDER", PROVIDER)


async def _make_index(
    db_session: AsyncSession, presentation_id: uuid.UUID
) -> VectorIndex:
    repo = VectorIndexRepository(db_session)
    return await repo.create_for_scope(
        presentation_id=presentation_id,
        lesson_id=None,
        index_type="presentation",
        strategy="heading",
        chunk_size=1500,
        chunk_overlap=150,
        max_chunk_tokens=1000,
        provider=PROVIDER,
        model=MODEL,
        dimension=DIMENSION,
        source_hash="src-hash",
    )


async def _make_chunk(
    db_session: AsyncSession,
    presentation_id: uuid.UUID,
    *,
    position: int = 0,
    status: str = "processed",
) -> DocumentChunk:
    chunk = DocumentChunk(
        presentation_id=presentation_id,
        position=position,
        level=0,
        source="presentation",
        chunk_type="paragraph",
        content=f"content-{position}",
        token_count=5,
        character_count=10,
        status=status,
        chunk_hash=f"hash-{position}",
        meta={},
    )
    db_session.add(chunk)
    await db_session.flush()
    return chunk


class TestEmbeddingStatisticsService:
    async def test_build_with_no_data_returns_empty_stats(
        self, db_session
    ) -> None:
        service = EmbeddingStatisticsService(UnitOfWork(session=db_session))

        stats = await service.build()

        assert stats.provider == PROVIDER
        assert stats.total_chunks == 0
        assert stats.pending_chunks == 0
        assert stats.processed_chunks == 0
        assert stats.failed_chunks == 0
        assert stats.active_embeddings == 0
        assert stats.superseded_embeddings == 0
        assert stats.failed_embeddings == 0
        assert stats.avg_dimension == 0.0
        assert stats.storage_bytes == 0.0
        assert stats.queue_backlog == 0
        assert stats.indexes_updated == 0
        assert stats.average_latency_ms == 0.0
        assert stats.provider_usage == []

    async def test_build_aggregates_chunks_and_embeddings(
        self, make_user, make_presentation, db_session
    ) -> None:
        user = await make_user()
        presentation = await make_presentation(user.id)
        await _make_index(db_session, presentation.id)
        await _make_chunk(
            db_session, presentation.id, position=0, status="pending"
        )
        processed = await _make_chunk(
            db_session, presentation.id, position=1, status="processed"
        )
        await _make_chunk(
            db_session, presentation.id, position=2, status="failed"
        )
        embeddings = EmbeddingRepository(db_session)
        await embeddings.create_for_chunk(
            chunk_id=processed.id,
            provider=PROVIDER,
            model=MODEL,
            dimension=DIMENSION,
            vector=[0.1] * DIMENSION,
            token_count=5,
            embedding_hash="hash1",
            checksum="checksum1",
            version=1,
        )
        superseded = await embeddings.create_for_chunk(
            chunk_id=processed.id,
            provider=PROVIDER,
            model=MODEL,
            dimension=DIMENSION,
            vector=[0.2] * DIMENSION,
            token_count=5,
            embedding_hash="hash2",
            checksum="checksum2",
            version=2,
        )
        superseded.status = "superseded"
        superseded.updated_at = datetime.now(UTC) - timedelta(days=40)
        await db_session.flush()

        service = EmbeddingStatisticsService(UnitOfWork(session=db_session))
        stats = await service.build()

        assert stats.total_chunks == 3
        assert stats.pending_chunks == 1
        assert stats.processed_chunks == 1
        assert stats.failed_chunks == 1
        assert stats.active_embeddings == 1
        assert stats.superseded_embeddings == 1
        assert stats.failed_embeddings == 0
        assert stats.avg_dimension == float(DIMENSION)
        assert stats.storage_bytes == round(1 * DIMENSION * 8.0, 2)
        assert stats.indexes_updated == 1
        assert (PROVIDER, MODEL, 1) in stats.provider_usage

    async def test_build_counts_queue_backlog(
        self, make_user, make_presentation, db_session
    ) -> None:
        user = await make_user()
        presentation = await make_presentation(user.id)
        index = await _make_index(db_session, presentation.id)
        jobs = EmbeddingJobRepository(db_session)
        queued = await jobs.create_job(
            job_type="index",
            user_id=user.id,
            presentation_id=presentation.id,
            lesson_id=None,
            index_id=index.id,
            total_items=1,
            payload=None,
            idempotency_key="queued-job",
            priority=5,
            max_attempts=3,
        )
        done = await jobs.create_job(
            job_type="index",
            user_id=user.id,
            presentation_id=presentation.id,
            lesson_id=None,
            index_id=index.id,
            total_items=1,
            payload=None,
            idempotency_key="done-job",
            priority=5,
            max_attempts=3,
        )
        await jobs.mark_completed(done)
        assert queued.status == EmbeddingJobStatus.QUEUED.value

        service = EmbeddingStatisticsService(UnitOfWork(session=db_session))
        stats = await service.build()

        assert stats.queue_backlog == 1

    async def test_build_averages_batch_latency(
        self, make_user, make_presentation, db_session
    ) -> None:
        user = await make_user()
        presentation = await make_presentation(user.id)
        index = await _make_index(db_session, presentation.id)
        jobs = EmbeddingJobRepository(db_session)
        job = await jobs.create_job(
            job_type="index",
            user_id=user.id,
            presentation_id=presentation.id,
            lesson_id=None,
            index_id=index.id,
            total_items=2,
            payload=None,
            idempotency_key="latency-job",
            priority=5,
            max_attempts=3,
        )
        batches = EmbeddingBatchRepository(db_session)
        first = await batches.create_batch(job.id, sequence=0, total_items=1)
        await batches.mark_completed(first, result={"latency_ms": 120})
        second = await batches.create_batch(job.id, sequence=1, total_items=1)
        await batches.mark_completed(second, result={"latency_ms": 80})
        third = await batches.create_batch(job.id, sequence=2, total_items=1)
        await batches.mark_completed(third, result={"latency_ms": 0})

        service = EmbeddingStatisticsService(UnitOfWork(session=db_session))
        stats = await service.build()

        assert stats.average_latency_ms == 100.0

    async def test_build_continues_when_integrity_fails(
        self, make_user, make_presentation, db_session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        user = await make_user()
        presentation = await make_presentation(user.id)
        await _make_index(db_session, presentation.id)
        service = EmbeddingStatisticsService(UnitOfWork(session=db_session))
        monkeypatch.setattr(
            service._integrity, "record_statistics", _raise_record_statistics
        )

        stats = await service.build()

        assert stats.indexes_updated == 0
        assert stats.total_chunks == 0

    async def test_build_emits_metrics(
        self, make_user, make_presentation, db_session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        user = await make_user()
        presentation = await make_presentation(user.id)
        await _make_index(db_session, presentation.id)

        class _FakeMetrics:
            def __init__(self) -> None:
                self.gauges: list[tuple[str, float, dict[str, str]]] = []

            def set_gauge(
                self, name: str, value: float, **labels: str
            ) -> None:
                self.gauges.append((name, value, dict(labels)))

        fake = _FakeMetrics()
        monkeypatch.setattr(
            "app.services.embedding_statistics_service.metrics", fake
        )
        service = EmbeddingStatisticsService(UnitOfWork(session=db_session))

        await service.build()

        names = {name for name, _value, _labels in fake.gauges}
        assert "embedding_versions_total" in names
        assert "embedding_storage_bytes" in names
        assert "embedding_dimension" in names
        assert "embedding_queue_backlog" in names


async def _raise_record_statistics(*args, **kwargs) -> None:
    raise RuntimeError("integrity failure")
