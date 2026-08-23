from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings import create_embedding_provider
from app.ai.embeddings.config import EmbeddingProviderConfig
from app.ai.embeddings.providers.local import LocalEmbeddingProvider
from app.database.unit_of_work import UnitOfWork
from app.models.document_chunk import DocumentChunk
from app.models.generated_lesson import GeneratedLesson
from app.models.vector_index import VectorIndex
from app.repositories.rag_repository import (
    EmbeddingRepository,
    EmbeddingStatisticsRepository,
    VectorIndexRepository,
    VectorIndexVersionRepository,
)
from app.services.embedding_refresh_service import EmbeddingRefreshService
from app.services.embedding_service import EmbeddingService
from shared.constants import LearningMode, LessonStatus

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
    chunk_hash: str = "h1",
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
        chunk_hash=chunk_hash,
        meta={},
    )
    db_session.add(chunk)
    await db_session.flush()
    return chunk


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


class TestEmbeddingRefreshService:
    async def test_run_is_noop_when_embeddings_fresh(
        self, make_user, make_presentation, db_session
    ) -> None:
        user = await make_user()
        presentation = await make_presentation(user.id)
        index = await _make_index(db_session, presentation.id)
        chunk = await _make_chunk(db_session, presentation.id, chunk_hash="h1")
        await EmbeddingService(UnitOfWork(session=db_session)).embed_chunks(
            [chunk], provider=_provider()
        )
        service = EmbeddingRefreshService(UnitOfWork(session=db_session))

        reports = await service.run(provider=_provider())
        ours = [report for report in reports if report.index_id == index.id]
        assert len(ours) == 1
        assert ours[0].checked == 1
        assert ours[0].refreshed == 0
        assert ours[0].failed == 0

        index_row = await VectorIndexRepository(db_session).get(index.id)
        assert index_row.latest_version == 0

    async def test_run_reembeds_stale_chunks_and_bumps_version(
        self, make_user, make_presentation, db_session
    ) -> None:
        user = await make_user()
        presentation = await make_presentation(user.id)
        index = await _make_index(db_session, presentation.id)
        chunk = await _make_chunk(db_session, presentation.id, chunk_hash="h1")
        await EmbeddingService(UnitOfWork(session=db_session)).embed_chunks(
            [chunk], provider=_provider()
        )
        chunk.chunk_hash = "h2"
        await db_session.flush()
        service = EmbeddingRefreshService(UnitOfWork(session=db_session))

        reports = await service.run(provider=_provider())
        ours = [report for report in reports if report.index_id == index.id]
        assert len(ours) == 1
        assert ours[0].refreshed == 1
        assert ours[0].failed == 0
        assert ours[0].version == 1

        index_row = await VectorIndexRepository(db_session).get(index.id)
        assert index_row.status == "ready"
        assert index_row.latest_version == 1

        versions = await VectorIndexVersionRepository(db_session).find(index_id=index.id)
        assert len(versions) == 1
        assert versions[0].version == 1
        assert versions[0].changelog["action"] == "refresh"

        embedding = await EmbeddingRepository(db_session).get_active(
            chunk.id, PROVIDER, MODEL
        )
        assert embedding is not None
        assert (embedding.meta or {}).get("chunk_hash") == "h2"

    async def test_run_records_statistics_for_presentation_scope(
        self, make_user, make_presentation, db_session
    ) -> None:
        user = await make_user()
        presentation = await make_presentation(user.id)
        index = await _make_index(db_session, presentation.id)
        chunk = await _make_chunk(db_session, presentation.id, chunk_hash="h1")
        await EmbeddingService(UnitOfWork(session=db_session)).embed_chunks(
            [chunk], provider=_provider()
        )
        chunk.chunk_hash = "h2"
        await db_session.flush()
        service = EmbeddingRefreshService(UnitOfWork(session=db_session))

        await service.run(provider=_provider())
        stats = EmbeddingStatisticsRepository(db_session)
        total = await stats.get_total(index.id)
        assert total is not None
        assert total.embedded_chunks == 1
        assert total.stale_chunks == 0

    async def test_run_skips_indexes_without_provider_or_model(
        self, make_user, make_presentation, db_session
    ) -> None:
        user = await make_user()
        presentation = await make_presentation(user.id)
        repo = VectorIndexRepository(db_session)
        await repo.create_for_scope(
            presentation_id=presentation.id,
            lesson_id=None,
            index_type="presentation",
            strategy="heading",
            chunk_size=1500,
            chunk_overlap=150,
            max_chunk_tokens=1000,
            provider=None,
            model=None,
            dimension=0,
            source_hash=None,
        )
        service = EmbeddingRefreshService(UnitOfWork(session=db_session))

        reports = await service.run(provider=_provider())
        assert reports == []

    async def test_run_refreshes_lesson_scope(
        self, make_user, make_presentation, db_session
    ) -> None:
        user = await make_user()
        presentation = await make_presentation(user.id)
        lesson = GeneratedLesson(
            presentation_id=presentation.id,
            user_id=user.id,
            mode=LearningMode.SLIDE.value,
            status=LessonStatus.READY.value,
            title="Lesson",
        )
        db_session.add(lesson)
        await db_session.flush()
        index = await VectorIndexRepository(db_session).create_for_scope(
            presentation_id=None,
            lesson_id=lesson.id,
            index_type="lesson",
            strategy="heading",
            chunk_size=1500,
            chunk_overlap=150,
            max_chunk_tokens=1000,
            provider=PROVIDER,
            model=MODEL,
            dimension=DIMENSION,
            source_hash="src-hash",
        )
        chunk = DocumentChunk(
            lesson_id=lesson.id,
            position=0,
            level=0,
            source="lesson",
            chunk_type="paragraph",
            content="lesson-content",
            token_count=5,
            character_count=13,
            status="pending",
            chunk_hash="h1",
            meta={},
        )
        db_session.add(chunk)
        await db_session.flush()
        await EmbeddingService(UnitOfWork(session=db_session)).embed_chunks(
            [chunk], provider=_provider()
        )
        chunk.chunk_hash = "h2"
        await db_session.flush()
        service = EmbeddingRefreshService(UnitOfWork(session=db_session))

        reports = await service.run(provider=_provider())
        ours = [report for report in reports if report.index_id == index.id]
        assert len(ours) == 1
        assert ours[0].refreshed == 1
        assert ours[0].version == 1
