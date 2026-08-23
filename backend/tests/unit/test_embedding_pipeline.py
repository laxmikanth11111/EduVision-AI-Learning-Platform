from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings import create_embedding_provider
from app.ai.embeddings.config import EmbeddingProviderConfig
from app.ai.embeddings.models import EmbeddingResponse
from app.ai.embeddings.providers.local import LocalEmbeddingProvider
from app.database.unit_of_work import UnitOfWork
from app.models.document_chunk import DocumentChunk
from app.models.embedding_job import EmbeddingJob
from app.repositories.rag_repository import (
    EmbeddingBatchRepository,
    EmbeddingJobRepository,
    EmbeddingStatisticsRepository,
    VectorIndexRepository,
    VectorIndexVersionRepository,
)
from app.services.embedding_pipeline_service import EmbeddingPipelineService
from app.services.embedding_service import EmbeddingService
from shared.constants import EmbeddingJobStatus, EmbeddingJobType

PROVIDER = "local"
MODEL = "local-embedding-test"
DIMENSION = 8


def _provider() -> LocalEmbeddingProvider:
    return create_embedding_provider(
        config=EmbeddingProviderConfig(provider=PROVIDER, model=MODEL, dimension=DIMENSION)
    )


async def _make_chunk(
    db_session: AsyncSession,
    presentation_id: uuid.UUID,
    position: int = 0,
    **overrides: object,
) -> DocumentChunk:
    chunk = DocumentChunk(
        presentation_id=presentation_id,
        position=position,
        level=0,
        source="presentation",
        chunk_type="paragraph",
        content=overrides.pop("content", f"content-{position}"),
        token_count=overrides.pop("token_count", 5),
        character_count=10,
        status="pending",
        chunk_hash=overrides.pop("chunk_hash", None),
        meta={"key": "value"},
        **overrides,
    )
    db_session.add(chunk)
    await db_session.flush()
    return chunk


async def _make_job(
    db_session: AsyncSession,
    user_id: uuid.UUID,
    presentation_id: uuid.UUID,
    index_id: uuid.UUID | None,
    total_items: int = 0,
    **overrides: object,
) -> EmbeddingJob:
    repo = EmbeddingJobRepository(db_session)
    return await repo.create_job(
        job_type=overrides.pop("job_type", EmbeddingJobType.INDEX.value),
        user_id=user_id,
        presentation_id=presentation_id,
        lesson_id=None,
        index_id=index_id,
        total_items=total_items,
        payload=None,
        idempotency_key=overrides.pop("idempotency_key", f"job-{uuid.uuid4().hex}"),
        priority=5,
        max_attempts=3,
    )


async def _make_index(
    db_session: AsyncSession, presentation_id: uuid.UUID
):
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


class TestEmbeddingPipelineService:
    async def test_start_job_transitions_queued_to_processing(
        self, make_user, make_presentation, db_session
    ) -> None:
        user = await make_user()
        presentation = await make_presentation(user.id)
        job = await _make_job(db_session, user.id, presentation.id, index_id=None)
        service = EmbeddingPipelineService(UnitOfWork(session=db_session))

        result = await service.start_job(job)
        assert result.status == EmbeddingJobStatus.PROCESSING.value
        assert result.started_at is not None

    async def test_start_job_idempotent_for_processing(
        self, make_user, make_presentation, db_session
    ) -> None:
        user = await make_user()
        presentation = await make_presentation(user.id)
        job = await _make_job(db_session, user.id, presentation.id, index_id=None)
        service = EmbeddingPipelineService(UnitOfWork(session=db_session))
        await service.start_job(job)
        started_at = job.started_at

        result = await service.start_job(job)
        assert result.status == EmbeddingJobStatus.PROCESSING.value
        assert result.started_at == started_at

    async def test_prepare_batches_creates_batches_from_unembedded_chunks(
        self, make_user, make_presentation, db_session
    ) -> None:
        user = await make_user()
        presentation = await make_presentation(user.id)
        index = await _make_index(db_session, presentation.id)
        job = await _make_job(db_session, user.id, presentation.id, index_id=index.id)
        for position in range(5):
            await _make_chunk(db_session, presentation.id, position=position)
        service = EmbeddingPipelineService(UnitOfWork(session=db_session))

        batches = await service.prepare_batches(job, batch_size=2)
        assert len(batches) == 3
        assert [batch.sequence for batch in batches] == [0, 1, 2]
        assert [batch.total_items for batch in batches] == [2, 2, 1]
        assert job.total_items == 5

    async def test_prepare_batches_idempotent_returns_existing_batches(
        self, make_user, make_presentation, db_session
    ) -> None:
        user = await make_user()
        presentation = await make_presentation(user.id)
        index = await _make_index(db_session, presentation.id)
        job = await _make_job(db_session, user.id, presentation.id, index_id=index.id)
        for position in range(3):
            await _make_chunk(db_session, presentation.id, position=position)
        service = EmbeddingPipelineService(UnitOfWork(session=db_session))
        first = await service.prepare_batches(job, batch_size=2)
        second = await service.prepare_batches(job, batch_size=2)

        assert second == first
        assert len(await EmbeddingBatchRepository(db_session).list_for_job(job.id)) == 2

    async def test_prepare_batches_only_selects_unembedded_chunks(
        self, make_user, make_presentation, db_session
    ) -> None:
        user = await make_user()
        presentation = await make_presentation(user.id)
        index = await _make_index(db_session, presentation.id)
        job = await _make_job(db_session, user.id, presentation.id, index_id=index.id)
        embedded = await _make_chunk(db_session, presentation.id, position=0)
        await _make_chunk(db_session, presentation.id, position=1)
        await EmbeddingService(UnitOfWork(session=db_session)).embed_chunks(
            [embedded], provider=_provider()
        )
        service = EmbeddingPipelineService(UnitOfWork(session=db_session))

        batches = await service.prepare_batches(job, batch_size=10)
        assert len(batches) == 1
        assert batches[0].total_items == 1

    async def test_prepare_batches_empty_when_all_embedded(
        self, make_user, make_presentation, db_session
    ) -> None:
        user = await make_user()
        presentation = await make_presentation(user.id)
        index = await _make_index(db_session, presentation.id)
        job = await _make_job(db_session, user.id, presentation.id, index_id=index.id)
        chunk = await _make_chunk(db_session, presentation.id, position=0)
        await EmbeddingService(UnitOfWork(session=db_session)).embed_chunks(
            [chunk], provider=_provider()
        )
        service = EmbeddingPipelineService(UnitOfWork(session=db_session))

        assert await service.prepare_batches(job) == []

    async def test_get_job_and_batch_by_public_id(
        self, make_user, make_presentation, db_session
    ) -> None:
        user = await make_user()
        presentation = await make_presentation(user.id)
        index = await _make_index(db_session, presentation.id)
        job = await _make_job(db_session, user.id, presentation.id, index_id=index.id)
        service = EmbeddingPipelineService(UnitOfWork(session=db_session))

        assert (await service.get_job(job.public_id)).id == job.id
        assert await service.get_job("missing") is None
        assert await service.get_batch("missing") is None

    async def test_has_pending_batches(self, make_user, make_presentation, db_session) -> None:
        user = await make_user()
        presentation = await make_presentation(user.id)
        index = await _make_index(db_session, presentation.id)
        job = await _make_job(db_session, user.id, presentation.id, index_id=index.id)
        await _make_chunk(db_session, presentation.id, position=0)
        service = EmbeddingPipelineService(UnitOfWork(session=db_session))
        assert await service.has_pending_batches(job) is False
        await service.prepare_batches(job, batch_size=10)
        assert await service.has_pending_batches(job) is True

    async def test_maybe_finalize_skips_terminal_job(
        self, make_user, make_presentation, db_session
    ) -> None:
        user = await make_user()
        presentation = await make_presentation(user.id)
        job = await _make_job(db_session, user.id, presentation.id, index_id=None)
        await EmbeddingJobRepository(db_session).mark_completed(job)
        service = EmbeddingPipelineService(UnitOfWork(session=db_session))

        result = await service.maybe_finalize(job)
        assert result.job_status == EmbeddingJobStatus.COMPLETED.value

    async def test_maybe_finalize_skips_while_pending_batches_exist(
        self, make_user, make_presentation, db_session
    ) -> None:
        user = await make_user()
        presentation = await make_presentation(user.id)
        index = await _make_index(db_session, presentation.id)
        job = await _make_job(db_session, user.id, presentation.id, index_id=index.id)
        await _make_chunk(db_session, presentation.id, position=0)
        service = EmbeddingPipelineService(UnitOfWork(session=db_session))
        await service.start_job(job)
        await service.prepare_batches(job, batch_size=10)

        result = await service.maybe_finalize(job)
        assert result.job_status == EmbeddingJobStatus.PROCESSING.value
        assert await EmbeddingJobRepository(db_session).get(job.id) is not None

    async def test_maybe_finalize_completes_job_and_index(
        self, make_user, make_presentation, db_session
    ) -> None:
        user = await make_user()
        presentation = await make_presentation(user.id)
        index = await _make_index(db_session, presentation.id)
        job = await _make_job(db_session, user.id, presentation.id, index_id=index.id)
        for position in range(3):
            await _make_chunk(db_session, presentation.id, position=position)
        service = EmbeddingPipelineService(UnitOfWork(session=db_session))
        batches = await service.prepare_batches(job, batch_size=2)
        for batch in batches:
            await service.process_batch(job, batch, provider=_provider())

        result = await service.maybe_finalize(job)
        assert result.job_status == EmbeddingJobStatus.COMPLETED.value
        assert result.index_status == "ready"
        assert result.version == 1
        assert result.processed == 3
        assert result.failed == 0
        assert result.tokens_used >= 1

        refreshed = await EmbeddingJobRepository(db_session).get(job.id)
        assert refreshed.status == EmbeddingJobStatus.COMPLETED.value
        assert refreshed.processed_items == 3

        index_row = await VectorIndexRepository(db_session).get(index.id)
        assert index_row.status == "ready"
        assert index_row.latest_version == 1

        versions = await VectorIndexVersionRepository(db_session).find(index_id=index.id)
        assert len(versions) == 1
        assert versions[0].version == 1
        assert versions[0].chunk_count == 3

        stats = EmbeddingStatisticsRepository(db_session)
        assert (await stats.get_total(index.id)).embedded_chunks == 3

    async def test_maybe_finalize_marks_index_failed_when_all_batches_fail(
        self, make_user, make_presentation, db_session
    ) -> None:
        user = await make_user()
        presentation = await make_presentation(user.id)
        index = await _make_index(db_session, presentation.id)
        job = await _make_job(db_session, user.id, presentation.id, index_id=index.id)
        await _make_chunk(db_session, presentation.id, position=0)
        service = EmbeddingPipelineService(UnitOfWork(session=db_session))
        batches = await service.prepare_batches(job, batch_size=10)

        class _FailingProvider(LocalEmbeddingProvider):
            async def embed(self, texts, *, request_id=None, correlation_id=None):
                raise RuntimeError("provider down")

        for batch in batches:
            await service.process_batch(job, batch, provider=_FailingProvider(_provider()._config))

        result = await service.maybe_finalize(job)
        assert result.job_status == EmbeddingJobStatus.FAILED.value
        assert result.index_status == "failed"

        index_row = await VectorIndexRepository(db_session).get(index.id)
        assert index_row.status == "failed"
        assert "failed" in (index_row.error_message or "")

    async def test_maybe_finalize_empty_job_completes_without_batches(
        self, make_user, make_presentation, db_session
    ) -> None:
        user = await make_user()
        presentation = await make_presentation(user.id)
        index = await _make_index(db_session, presentation.id)
        job = await _make_job(db_session, user.id, presentation.id, index_id=index.id)
        service = EmbeddingPipelineService(UnitOfWork(session=db_session))

        result = await service.maybe_finalize(job)
        assert result.job_status == EmbeddingJobStatus.COMPLETED.value
        index_row = await VectorIndexRepository(db_session).get(index.id)
        assert index_row.status == "ready"

    async def test_maybe_finalize_no_batches_with_items_marks_failed(
        self, make_user, make_presentation, db_session
    ) -> None:
        user = await make_user()
        presentation = await make_presentation(user.id)
        index = await _make_index(db_session, presentation.id)
        job = await _make_job(db_session, user.id, presentation.id, index_id=index.id, total_items=5)
        service = EmbeddingPipelineService(UnitOfWork(session=db_session))

        result = await service.maybe_finalize(job)
        assert result.job_status == EmbeddingJobStatus.FAILED.value
        assert (await EmbeddingJobRepository(db_session).get(job.id)).error_code == "NO_BATCHES"
