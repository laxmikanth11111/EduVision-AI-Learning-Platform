from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.unit_of_work import UnitOfWork
from app.models.chunk_embedding import ChunkEmbedding
from app.models.document_chunk import DocumentChunk
from app.models.embedding_batch import EmbeddingBatch
from app.models.embedding_job import EmbeddingJob
from app.models.embedding_metadata import EmbeddingMetadata
from app.models.vector_index import VectorIndex
from app.repositories.rag_repository import (
    EmbeddingBatchRepository,
    EmbeddingJobRepository,
    EmbeddingMetadataRepository,
    EmbeddingRepository,
    VectorIndexRepository,
)
from app.services.embedding_cleanup_service import EmbeddingCleanupService
from app.services.embedding_integrity_service import EmbeddingIntegrityService
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
    db_session: AsyncSession, presentation_id: uuid.UUID, position: int = 0
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
        status="pending",
        chunk_hash="h1",
        meta={},
    )
    db_session.add(chunk)
    await db_session.flush()
    return chunk


async def _make_job(
    db_session: AsyncSession,
    user_id: uuid.UUID,
    presentation_id: uuid.UUID,
    index_id: uuid.UUID,
    status: str = EmbeddingJobStatus.QUEUED.value,
) -> EmbeddingJob:
    repo = EmbeddingJobRepository(db_session)
    job = await repo.create_job(
        job_type="index",
        user_id=user_id,
        presentation_id=presentation_id,
        lesson_id=None,
        index_id=index_id,
        total_items=1,
        payload=None,
        idempotency_key=f"job-{uuid.uuid4().hex}",
        priority=5,
        max_attempts=3,
    )
    if status == EmbeddingJobStatus.PROCESSING.value:
        await repo.mark_processing(job)
    elif status == EmbeddingJobStatus.COMPLETED.value:
        await repo.mark_completed(job)
    return job


class TestEmbeddingCleanupService:
    async def test_cleanup_orphan_embeddings(
        self, make_user, make_presentation, db_session
    ) -> None:
        user = await make_user()
        presentation = await make_presentation(user.id)
        index = await _make_index(db_session, presentation.id)
        chunk = await _make_chunk(db_session, presentation.id)
        repo = EmbeddingRepository(db_session)
        embedding = await repo.create_for_chunk(
            chunk_id=chunk.id,
            provider=PROVIDER,
            model=MODEL,
            dimension=DIMENSION,
            vector=[0.1] * DIMENSION,
            token_count=5,
            embedding_hash="hash1",
            checksum="checksum1",
            version=1,
        )
        chunk.deleted_at = datetime.now(UTC)
        await db_session.flush()
        service = EmbeddingCleanupService(UnitOfWork(session=db_session))

        report = await service.run()
        assert report.orphan_embeddings == 1
        assert embedding.deleted_at is not None
        assert report.obsolete_versions == 0
        assert index.status == "building"

    async def test_cleanup_obsolete_versions(
        self, make_user, make_presentation, db_session
    ) -> None:
        user = await make_user()
        presentation = await make_presentation(user.id)
        await _make_index(db_session, presentation.id)
        chunk = await _make_chunk(db_session, presentation.id)
        repo = EmbeddingRepository(db_session)
        embedding = await repo.create_for_chunk(
            chunk_id=chunk.id,
            provider=PROVIDER,
            model=MODEL,
            dimension=DIMENSION,
            vector=[0.1] * DIMENSION,
            token_count=5,
            embedding_hash="hash1",
            checksum="checksum1",
            version=1,
        )
        embedding.status = "superseded"
        embedding.updated_at = datetime.now(UTC) - timedelta(days=40)
        await db_session.flush()
        service = EmbeddingCleanupService(UnitOfWork(session=db_session))

        report = await service.run(obsolete_days=30)
        assert report.obsolete_versions == 1
        assert embedding.deleted_at is not None

    async def test_cleanup_leaves_recent_superseded_versions(
        self, make_user, make_presentation, db_session
    ) -> None:
        user = await make_user()
        presentation = await make_presentation(user.id)
        await _make_index(db_session, presentation.id)
        chunk = await _make_chunk(db_session, presentation.id)
        repo = EmbeddingRepository(db_session)
        embedding = await repo.create_for_chunk(
            chunk_id=chunk.id,
            provider=PROVIDER,
            model=MODEL,
            dimension=DIMENSION,
            vector=[0.1] * DIMENSION,
            token_count=5,
            embedding_hash="hash1",
            checksum="checksum1",
            version=1,
        )
        embedding.status = "superseded"
        await db_session.flush()
        service = EmbeddingCleanupService(UnitOfWork(session=db_session))

        report = await service.run(obsolete_days=30)
        assert report.obsolete_versions == 0
        assert embedding.deleted_at is None

    async def test_recover_failed_batches(
        self, make_user, make_presentation, db_session
    ) -> None:
        user = await make_user()
        presentation = await make_presentation(user.id)
        index = await _make_index(db_session, presentation.id)
        job = await _make_job(
            db_session, user.id, presentation.id, index.id,
            status=EmbeddingJobStatus.PROCESSING.value,
        )
        batches = EmbeddingBatchRepository(db_session)
        batch = await batches.create_batch(job.id, sequence=0, total_items=1)
        await batches.mark_failed(batch, "EMBEDDING_FAILED", "provider down")
        service = EmbeddingCleanupService(UnitOfWork(session=db_session))

        report = await service.run()
        assert report.batches_recovered == 1
        refreshed = await batches.get(batch.id)
        assert refreshed.status == "queued"
        assert (refreshed.result or {}).get("retries") == 1
        assert refreshed.error_code is None

    async def test_recover_skips_batches_at_retry_budget(
        self, make_user, make_presentation, db_session
    ) -> None:
        user = await make_user()
        presentation = await make_presentation(user.id)
        index = await _make_index(db_session, presentation.id)
        job = await _make_job(
            db_session, user.id, presentation.id, index.id,
            status=EmbeddingJobStatus.PROCESSING.value,
        )
        batches = EmbeddingBatchRepository(db_session)
        batch = await batches.create_batch(job.id, sequence=0, total_items=1)
        batch.result = {"retries": 1}
        await batches.mark_failed(batch, "EMBEDDING_FAILED", "provider down")
        service = EmbeddingCleanupService(UnitOfWork(session=db_session))

        report = await service.run()
        assert report.batches_recovered == 0
        refreshed = await batches.get(batch.id)
        assert refreshed.status == "failed"

    async def test_recover_skips_unrecoverable_error_codes(
        self, make_user, make_presentation, db_session
    ) -> None:
        user = await make_user()
        presentation = await make_presentation(user.id)
        index = await _make_index(db_session, presentation.id)
        job = await _make_job(
            db_session, user.id, presentation.id, index.id,
            status=EmbeddingJobStatus.PROCESSING.value,
        )
        batches = EmbeddingBatchRepository(db_session)
        batch = await batches.create_batch(job.id, sequence=0, total_items=1)
        await batches.mark_failed(batch, "VALIDATION_ERROR", "bad payload")
        service = EmbeddingCleanupService(UnitOfWork(session=db_session))

        report = await service.run()
        assert report.batches_recovered == 0

    async def test_recover_skips_when_job_is_terminal(
        self, make_user, make_presentation, db_session
    ) -> None:
        user = await make_user()
        presentation = await make_presentation(user.id)
        index = await _make_index(db_session, presentation.id)
        job = await _make_job(
            db_session, user.id, presentation.id, index.id,
            status=EmbeddingJobStatus.COMPLETED.value,
        )
        batches = EmbeddingBatchRepository(db_session)
        batch = await batches.create_batch(job.id, sequence=0, total_items=1)
        await batches.mark_failed(batch, "EMBEDDING_FAILED", "provider down")
        service = EmbeddingCleanupService(UnitOfWork(session=db_session))

        report = await service.run()
        assert report.batches_recovered == 0

    async def test_reclaim_expired_jobs(
        self, make_user, make_presentation, db_session
    ) -> None:
        user = await make_user()
        presentation = await make_presentation(user.id)
        index = await _make_index(db_session, presentation.id)
        job = await _make_job(db_session, user.id, presentation.id, index.id)
        job.updated_at = datetime.now(UTC) - timedelta(days=2)
        await db_session.flush()
        service = EmbeddingCleanupService(UnitOfWork(session=db_session))

        report = await service.run()
        assert report.jobs_expired == 1
        refreshed = await EmbeddingJobRepository(db_session).get(job.id)
        assert refreshed.status == EmbeddingJobStatus.FAILED.value
        assert refreshed.error_code == "JOB_EXPIRED"

    async def test_cleanup_metadata_for_deleted_indexes(
        self, make_user, make_presentation, db_session
    ) -> None:
        user = await make_user()
        presentation = await make_presentation(user.id)
        index = await _make_index(db_session, presentation.id)
        metadata = await EmbeddingMetadataRepository(db_session).create(
            index_id=index.id,
            provider="meta-provider",
            model="meta-model",
            dimension=8,
            status="active",
        )
        index.deleted_at = datetime.now(UTC)
        await db_session.flush()
        service = EmbeddingCleanupService(UnitOfWork(session=db_session))

        report = await service.run()
        assert report.metadata_obsolete == 1
        refreshed = await EmbeddingMetadataRepository(db_session).get(metadata.id)
        assert refreshed.status == "obsolete"

    async def test_run_returns_empty_report_when_nothing_to_clean(
        self, make_user, make_presentation, db_session
    ) -> None:
        user = await make_user()
        presentation = await make_presentation(user.id)
        await _make_index(db_session, presentation.id)
        service = EmbeddingCleanupService(UnitOfWork(session=db_session))

        report = await service.run()
        assert report.orphan_embeddings == 0
        assert report.obsolete_versions == 0
        assert report.batches_recovered == 0
        assert report.jobs_expired == 0
        assert report.metadata_obsolete == 0
        assert report.errors == []

    async def test_run_emits_metrics(
        self, make_user, make_presentation, db_session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        user = await make_user()
        presentation = await make_presentation(user.id)
        await _make_index(db_session, presentation.id)

        class _FakeMetrics:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def increment(self, name: str, value: float = 1.0, **labels: str) -> None:
                self.calls.append(name)

            def set_gauge(self, name: str, value: float, **labels: str) -> None:
                self.calls.append(name)

        fake = _FakeMetrics()
        monkeypatch.setattr(
            "app.services.embedding_cleanup_service.metrics", fake
        )
        service = EmbeddingCleanupService(UnitOfWork(session=db_session))

        await service.run()
        assert "embedding_cleanup_orphans_total" in fake.calls
        assert "embedding_cleanup_obsolete_total" in fake.calls
        assert "embedding_cleanup_batches_recovered_total" in fake.calls
        assert "embedding_cleanup_jobs_expired_total" in fake.calls
        assert "embedding_cleanup_metadata_total" in fake.calls
