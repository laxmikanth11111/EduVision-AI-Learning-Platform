from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest

from app.models.document_chunk import DocumentChunk
from app.repositories.rag_repository import (
    DocumentChunkRepository,
    EmbeddingBatchRepository,
    EmbeddingJobRepository,
    EmbeddingRepository,
    EmbeddingStatisticsRepository,
    VectorIndexRepository,
    VectorIndexVersionRepository,
)
from shared.constants import (
    ChunkStatus,
    EmbeddingBatchStatus,
    EmbeddingJobStatus,
    EmbeddingStatisticsPeriod,
    EmbeddingVersionStatus,
    VectorIndexStatus,
    VectorIndexType,
)

pytestmark = pytest.mark.asyncio

PROVIDER = "local"
MODEL = "eduvision-test-1"
DIMENSION = 32


async def _make_chunk(
    db_session,
    presentation_id: uuid.UUID,
    position: int = 0,
    **overrides,
) -> DocumentChunk:
    chunk = DocumentChunk(
        presentation_id=presentation_id,
        position=position,
        level=overrides.pop("level", 0),
        source=overrides.pop("source", "presentation"),
        chunk_type=overrides.pop("chunk_type", "paragraph"),
        content=overrides.pop("content", f"content-{position}"),
        token_count=overrides.pop("token_count", 5),
        character_count=overrides.pop("character_count", 10),
        status=overrides.pop("status", ChunkStatus.PENDING.value),
        chunk_hash=overrides.pop("chunk_hash", None),
        meta=overrides.pop("meta", {"key": "value"}),
        **overrides,
    )
    db_session.add(chunk)
    await db_session.flush()
    return chunk


class TestDocumentChunkRepository:
    async def test_create_and_list_for_presentation(self, make_user, make_presentation, db_session) -> None:
        user = await make_user()
        presentation = await make_presentation(user.id)
        repo = DocumentChunkRepository(db_session)

        await _make_chunk(db_session, presentation.id, position=1)
        await _make_chunk(db_session, presentation.id, position=0)

        listed = await repo.list_for_presentation(presentation.id)
        assert [c.position for c in listed] == [0, 1]

    async def test_get_for_scope_or_raise(self, make_user, make_presentation, db_session) -> None:
        user = await make_user()
        presentation = await make_presentation(user.id)
        repo = DocumentChunkRepository(db_session)
        chunk = await _make_chunk(db_session, presentation.id, position=0)

        fetched = await repo.get_for_scope_or_raise(presentation.id, chunk.public_id)
        assert fetched.id == chunk.id
        assert fetched.public_id.startswith("chunk_")

    async def test_count_by_status(self, make_user, make_presentation, db_session) -> None:
        user = await make_user()
        presentation = await make_presentation(user.id)
        repo = DocumentChunkRepository(db_session)

        await _make_chunk(db_session, presentation.id, position=0)
        await _make_chunk(db_session, presentation.id, position=1, status=ChunkStatus.FAILED.value)

        counts = await repo.count_by_status(presentation.id)
        assert counts[ChunkStatus.PENDING.value] == 1
        assert counts[ChunkStatus.FAILED.value] == 1

    async def test_mark_processed_and_failed(self, make_user, make_presentation, db_session) -> None:
        user = await make_user()
        presentation = await make_presentation(user.id)
        repo = DocumentChunkRepository(db_session)
        chunk = await _make_chunk(db_session, presentation.id, position=0)

        processed = await repo.mark_processed(chunk)
        assert processed.status == ChunkStatus.PROCESSED.value

        failed = await repo.mark_failed(processed)
        assert failed.status == ChunkStatus.FAILED.value

    async def test_soft_delete_many(self, make_user, make_presentation, db_session) -> None:
        user = await make_user()
        presentation = await make_presentation(user.id)
        repo = DocumentChunkRepository(db_session)
        first = await _make_chunk(db_session, presentation.id, position=0)
        second = await _make_chunk(db_session, presentation.id, position=1)

        deleted = await repo.soft_delete_many([first.id, second.id])
        assert deleted == 2
        remaining = await repo.list_for_presentation(presentation.id)
        assert remaining == []


class TestEmbeddingRepository:
    async def test_create_and_get_active(self, make_user, make_presentation, db_session) -> None:
        user = await make_user()
        presentation = await make_presentation(user.id)
        chunk = await _make_chunk(db_session, presentation.id, position=0)
        repo = EmbeddingRepository(db_session)

        embedding = await repo.create_for_chunk(
            chunk_id=chunk.id,
            provider=PROVIDER,
            model=MODEL,
            dimension=DIMENSION,
            vector=[0.5, 0.25],
            token_count=5,
            embedding_hash="abc",
            checksum="def",
            meta={"chunk_hash": "abc"},
        )
        assert embedding.public_id.startswith("emb_")

        active = await repo.get_active(chunk.id, PROVIDER, MODEL)
        assert active is not None
        assert active.id == embedding.id

    async def test_supersede_marks_old_version(self, make_user, make_presentation, db_session) -> None:
        user = await make_user()
        presentation = await make_presentation(user.id)
        chunk = await _make_chunk(db_session, presentation.id, position=0)
        repo = EmbeddingRepository(db_session)

        await repo.create_for_chunk(
            chunk_id=chunk.id, provider=PROVIDER, model=MODEL,
            dimension=DIMENSION, vector=[0.1], token_count=5,
            embedding_hash="v1", checksum="c1", version=1,
        )
        superseded = await repo.supersede_for_chunk(chunk.id, PROVIDER, MODEL)
        assert superseded == 1

        await repo.create_for_chunk(
            chunk_id=chunk.id, provider=PROVIDER, model=MODEL,
            dimension=DIMENSION, vector=[0.2], token_count=5,
            embedding_hash="v2", checksum="c2", version=2,
        )
        active = await repo.get_active(chunk.id, PROVIDER, MODEL)
        assert active is not None
        assert active.embedding_hash == "v2"

    async def test_orphans_track_soft_deleted_chunks(self, make_user, make_presentation, db_session) -> None:
        user = await make_user()
        presentation = await make_presentation(user.id)
        chunk_repo = DocumentChunkRepository(db_session)
        embedding_repo = EmbeddingRepository(db_session)

        chunk = await _make_chunk(db_session, presentation.id, position=0)
        await embedding_repo.create_for_chunk(
            chunk_id=chunk.id, provider=PROVIDER, model=MODEL,
            dimension=DIMENSION, vector=[0.3], token_count=5,
            embedding_hash="h", checksum="c",
        )
        assert await embedding_repo.count_orphans(presentation.id, PROVIDER, MODEL) == 0

        await chunk_repo.soft_delete_many([chunk.id])
        assert await embedding_repo.count_orphans(presentation.id, PROVIDER, MODEL) == 1
        orphans = await embedding_repo.list_orphans(presentation.id, PROVIDER, MODEL)
        assert len(orphans) == 1

    async def test_soft_delete_embedding(self, make_user, make_presentation, db_session) -> None:
        user = await make_user()
        presentation = await make_presentation(user.id)
        chunk = await _make_chunk(db_session, presentation.id, position=0)
        repo = EmbeddingRepository(db_session)
        embedding = await repo.create_for_chunk(
            chunk_id=chunk.id, provider=PROVIDER, model=MODEL,
            dimension=DIMENSION, vector=[0.4], token_count=5,
            embedding_hash="h", checksum="c",
        )

        await repo.soft_delete(embedding)
        assert await repo.get_active(chunk.id, PROVIDER, MODEL) is None


class TestEmbeddingJobRepository:
    async def test_create_job_and_list_queued(self, make_user, make_presentation, db_session) -> None:
        user = await make_user()
        presentation = await make_presentation(user.id)
        repo = EmbeddingJobRepository(db_session)

        job = await repo.create_job(
            job_type="index",
            user_id=user.id,
            presentation_id=presentation.id,
            lesson_id=None,
            index_id=None,
            total_items=3,
            payload={"scope": "presentation"},
            idempotency_key="job-1",
        )
        assert job.public_id.startswith("ejob_")
        assert job.status == EmbeddingJobStatus.QUEUED.value

        queued = await repo.list_queued()
        assert any(j.id == job.id for j in queued)

    async def test_idempotency_key_lookup(self, make_user, make_presentation, db_session) -> None:
        user = await make_user()
        presentation = await make_presentation(user.id)
        repo = EmbeddingJobRepository(db_session)
        job = await repo.create_job(
            job_type="refresh", user_id=user.id, presentation_id=presentation.id,
            lesson_id=None, index_id=None, total_items=1, payload=None,
            idempotency_key="refresh-1",
        )
        found = await repo.get_by_idempotency_key(user.id, "refresh-1")
        assert found is not None
        assert found.id == job.id

    async def test_job_lifecycle(self, make_user, make_presentation, db_session) -> None:
        user = await make_user()
        presentation = await make_presentation(user.id)
        repo = EmbeddingJobRepository(db_session)
        job = await repo.create_job(
            job_type="index", user_id=user.id, presentation_id=presentation.id,
            lesson_id=None, index_id=None, total_items=2, payload=None,
            idempotency_key="job-lifecycle",
        )

        await repo.mark_processing(job)
        assert job.status == EmbeddingJobStatus.PROCESSING.value
        assert job.started_at is not None

        await repo.increment_progress(job, processed=1, failed=0)
        assert job.processed_items == 1

        completed = await repo.mark_completed(job, {"ok": True})
        assert completed.status == EmbeddingJobStatus.COMPLETED.value
        assert completed.completed_at is not None

    async def test_retry_record(self, make_user, make_presentation, db_session) -> None:
        user = await make_user()
        presentation = await make_presentation(user.id)
        repo = EmbeddingJobRepository(db_session)
        job = await repo.create_job(
            job_type="index", user_id=user.id, presentation_id=presentation.id,
            lesson_id=None, index_id=None, total_items=1, payload=None,
            idempotency_key="job-retry", max_attempts=2,
        )
        await repo.record_retry(job, datetime.now(UTC) + timedelta(seconds=30))
        assert job.attempt_count == 1
        assert job.next_retry_at is not None
        assert job.retry_state == "scheduled"

        await repo.record_retry(job, datetime.now(UTC) + timedelta(seconds=30))
        assert job.attempt_count == 2
        assert job.retry_state == "exhausted"


class TestEmbeddingBatchRepository:
    async def test_batch_flow(self, make_user, make_presentation, db_session) -> None:
        user = await make_user()
        presentation = await make_presentation(user.id)
        job_repo = EmbeddingJobRepository(db_session)
        batch_repo = EmbeddingBatchRepository(db_session)

        job = await job_repo.create_job(
            job_type="batch", user_id=user.id, presentation_id=presentation.id,
            lesson_id=None, index_id=None, total_items=4, payload=None,
            idempotency_key="job-batch",
        )
        batch = await batch_repo.create_batch(job.id, sequence=0, total_items=4)
        assert batch.status == EmbeddingBatchStatus.QUEUED.value

        await batch_repo.mark_processing(batch)
        assert batch.status == EmbeddingBatchStatus.PROCESSING.value

        await batch_repo.update_progress(batch, processed=4, failed=0, request_ids=["r1"])
        completed = await batch_repo.mark_completed(batch, {"ok": True})
        assert completed.status == EmbeddingBatchStatus.COMPLETED.value

        pending = await batch_repo.get_pending_for_job(job.id)
        assert pending == []


class TestVectorIndexRepository:
    async def test_index_crud_and_version(self, make_user, make_presentation, db_session) -> None:
        user = await make_user()
        presentation = await make_presentation(user.id)
        repo = VectorIndexRepository(db_session)
        version_repo = VectorIndexVersionRepository(db_session)

        index = await repo.create_for_scope(
            presentation_id=presentation.id,
            lesson_id=None,
            index_type=VectorIndexType.PRESENTATION.value,
            strategy="heading",
            chunk_size=1500,
            chunk_overlap=150,
            max_chunk_tokens=1000,
            provider=PROVIDER,
            model=MODEL,
            dimension=DIMENSION,
            source_hash="source-1",
        )
        assert index.public_id.startswith("vindex_")

        fetched = await repo.get_for_presentation(presentation.id)
        assert fetched is not None
        assert fetched.id == index.id

        await repo.bump_latest_version(index)
        version = await version_repo.create_version(
            index,
            source_hash="source-1",
            chunk_count=2,
            embedding_count=2,
            total_tokens=10,
            config={"strategy": "heading"},
            changelog={"created": 2},
        )
        assert version.version == 1

        ready = await repo.mark_ready(
            index, chunk_count=2, embedding_count=2, total_tokens=10, source_hash="source-1"
        )
        assert ready.status == VectorIndexStatus.READY.value

    async def test_list_building_and_failed(self, make_user, make_presentation, db_session) -> None:
        user = await make_user()
        presentation = await make_presentation(user.id)
        repo = VectorIndexRepository(db_session)
        index = await repo.create_for_scope(
            presentation_id=presentation.id,
            lesson_id=None,
            index_type=VectorIndexType.PRESENTATION.value,
            strategy="heading",
            chunk_size=1500,
            chunk_overlap=150,
            max_chunk_tokens=1000,
            provider=PROVIDER,
            model=MODEL,
            dimension=DIMENSION,
            source_hash="s",
        )
        building = await repo.list_building()
        assert any(i.id == index.id for i in building)

        await repo.mark_failed(index, "boom")
        assert index.status == VectorIndexStatus.FAILED.value
        assert index.error_message == "boom"


class TestEmbeddingStatisticsRepository:
    async def test_upsert_total_and_daily(self, make_user, make_presentation, db_session) -> None:
        user = await make_user()
        presentation = await make_presentation(user.id)
        index = await VectorIndexRepository(db_session).create_for_scope(
            presentation_id=presentation.id,
            lesson_id=None,
            index_type=VectorIndexType.PRESENTATION.value,
            strategy="heading",
            chunk_size=1500,
            chunk_overlap=150,
            max_chunk_tokens=1000,
            provider=PROVIDER,
            model=MODEL,
            dimension=DIMENSION,
            source_hash="s",
        )
        repo = EmbeddingStatisticsRepository(db_session)

        await repo.upsert_total(index.id, {"total_chunks": 5, "embedded_chunks": 3})
        await repo.upsert_total(index.id, {"total_chunks": 6, "embedded_chunks": 4})

        total = await repo.get_total(index.id)
        assert total is not None
        assert total.total_chunks == 6
        assert total.embedded_chunks == 4

        today = datetime.now(UTC).date()
        await repo.upsert_daily(index.id, today, {"total_embeddings_generated": 2})
        daily = await repo.get_daily(index.id, today)
        assert daily is not None
        assert daily.total_embeddings_generated == 2

        rows = await repo.list_for_index(
            index.id, EmbeddingStatisticsPeriod.DAILY.value
        )
        assert len(rows) == 1
