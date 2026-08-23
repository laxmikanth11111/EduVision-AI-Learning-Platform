"""Tests for the RAG indexing trigger service (F2-13 Phase 1)."""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.database.unit_of_work import UnitOfWork
from app.models.content_block import ContentBlock
from app.models.content_unit import ContentUnit
from app.models.document_chunk import DocumentChunk
from app.models.embedding_job import EmbeddingJob
from app.models.generated_block import GeneratedBlock
from app.models.generated_lesson import GeneratedLesson
from app.models.generated_lesson_version import GeneratedLessonVersion
from app.models.vector_index import VectorIndex
from app.services.rag_indexing_service import RagIndexingError, RagIndexingService
from shared.constants import (
    ChunkSource,
    ContentBlockType,
    ContentUnitType,
    EmbeddingJobStatus,
    EmbeddingJobType,
    GeneratedBlockType,
    LessonStatus,
    LessonVersionStatus,
    VectorIndexStatus,
    VectorIndexType,
)

pytestmark = pytest.mark.asyncio


def _service(db_session: object) -> RagIndexingService:
    return RagIndexingService(UnitOfWork(session=db_session))


async def _count(db_session: object, model: type, **filters: object) -> int:
    stmt = select(model).where(*[getattr(model, key) == value for key, value in filters.items()])
    rows = (await db_session.execute(stmt)).scalars().all()
    return len(rows)


async def _seed_extracted_presentation(
    db_session: object,
    user: object,
    presentation: object,
    *,
    extraction_status: str = "ready",
    units: int = 2,
) -> None:
    presentation.extraction_status = extraction_status
    for unit_index in range(units):
        unit = ContentUnit(
            presentation_id=presentation.id,
            unit_type=ContentUnitType.DOCUMENT.value,
            position=unit_index,
            title=f"Unit {unit_index}",
        )
        db_session.add(unit)
        await db_session.flush()
        for block_index in range(2):
            db_session.add(
                ContentBlock(
                    content_unit_id=unit.id,
                    block_type=ContentBlockType.PARAGRAPH.value,
                    position=block_index,
                    content=f"Unit {unit_index} block {block_index} content text.",
                )
            )
    await db_session.flush()


async def _seed_lesson(
    db_session: object,
    user: object,
    presentation: object,
    *,
    version_status: str = LessonVersionStatus.SUCCEEDED.value,
    blocks: int = 2,
) -> GeneratedLesson:
    lesson = GeneratedLesson(
        presentation_id=presentation.id,
        user_id=user.id,
        mode="ai_generated",
        status=LessonStatus.READY.value,
        latest_version=1,
    )
    db_session.add(lesson)
    await db_session.flush()
    version = GeneratedLessonVersion(
        lesson_id=lesson.id,
        version=1,
        status=version_status,
        title="Lesson",
    )
    db_session.add(version)
    await db_session.flush()
    for block_index in range(blocks):
        db_session.add(
            GeneratedBlock(
                lesson_version_id=version.id,
                block_type=GeneratedBlockType.PARAGRAPH.value,
                position=block_index,
                content=f"Lesson block {block_index} content text.",
            )
        )
    await db_session.flush()
    return lesson


class TestIndexPresentation:
    async def test_creates_chunks_index_and_job_and_dispatches(
        self, make_user, make_presentation, db_session
    ) -> None:
        user = await make_user()
        presentation = await make_presentation(user.id)
        await _seed_extracted_presentation(db_session, user, presentation)

        with patch("app.workers.tasks.safe_dispatch") as dispatch:
            result = await _service(db_session).index_presentation(presentation.public_id)

        assert result["skipped"] is False
        assert result["scope"] == "presentation"
        assert result["chunks"] > 0

        chunks = (await db_session.execute(select(DocumentChunk))).scalars().all()
        assert len(chunks) == result["chunks"]
        assert all(chunk.source == ChunkSource.PRESENTATION.value for chunk in chunks)
        assert all(chunk.status == "pending" for chunk in chunks)
        assert all(chunk.presentation_id == presentation.id for chunk in chunks)

        index = (
            await db_session.execute(select(VectorIndex))
        ).scalar_one()
        assert index.index_type == VectorIndexType.PRESENTATION.value
        assert index.status == VectorIndexStatus.BUILDING.value
        assert index.presentation_id == presentation.id
        assert len(index.source_hash or "") == 64

        job = (await db_session.execute(select(EmbeddingJob))).scalar_one()
        assert job.job_type == EmbeddingJobType.INDEX.value
        assert job.status == EmbeddingJobStatus.QUEUED.value
        assert job.index_id == index.id
        assert job.idempotency_key is not None
        assert job.idempotency_key.startswith("index:pres:")

        dispatch.assert_called_once()
        assert dispatch.call_args.args[0].name == "eduvision.embedding.generate"
        assert dispatch.call_args.args[1] == job.public_id

    async def test_skips_when_index_already_ready(
        self, make_user, make_presentation, db_session
    ) -> None:
        user = await make_user()
        presentation = await make_presentation(user.id)
        await _seed_extracted_presentation(db_session, user, presentation)

        with patch("app.workers.tasks.safe_dispatch") as dispatch:
            first = await _service(db_session).index_presentation(presentation.public_id)

        index = (
            await db_session.execute(select(VectorIndex))
        ).scalar_one()
        index.status = VectorIndexStatus.READY.value

        with patch("app.workers.tasks.safe_dispatch") as dispatch:
            second = await _service(db_session).index_presentation(presentation.public_id)

        assert first["chunks"] > 0
        assert second["skipped"] is True
        assert second["chunks"] == 0
        assert second["job_id"] is None
        dispatch.assert_not_called()
        assert await _count(db_session, EmbeddingJob) == 1

    async def test_rebuild_bumps_chunk_version_and_reuses_queued_job(
        self, make_user, make_presentation, db_session
    ) -> None:
        user = await make_user()
        presentation = await make_presentation(user.id)
        await _seed_extracted_presentation(db_session, user, presentation)

        with patch("app.workers.tasks.safe_dispatch"):
            await _service(db_session).index_presentation(presentation.public_id)
            second = await _service(db_session).index_presentation(presentation.public_id)

        chunks = (await db_session.execute(select(DocumentChunk))).scalars().all()
        live = [chunk for chunk in chunks if chunk.deleted_at is None]
        assert len(live) == second["chunks"] > 0
        assert all(chunk.version == 2 for chunk in live)
        assert await _count(db_session, EmbeddingJob) == 1
        assert await _count(db_session, DocumentChunk, deleted_at=None) == second["chunks"]

    async def test_rejects_not_ready(
        self, make_user, make_presentation, db_session
    ) -> None:
        user = await make_user()
        presentation = await make_presentation(user.id)
        await _seed_extracted_presentation(
            db_session, user, presentation, extraction_status="none"
        )

        with pytest.raises(RagIndexingError):
            await _service(db_session).index_presentation(presentation.public_id)

        assert await _count(db_session, DocumentChunk) == 0
        assert await _count(db_session, EmbeddingJob) == 0
        assert await _count(db_session, VectorIndex) == 0

    async def test_rejects_missing_presentation(self, db_session) -> None:
        with pytest.raises(RagIndexingError):
            await _service(db_session).index_presentation(f"pres_{uuid.uuid4().hex[:16]}")


class TestIndexLesson:
    async def test_creates_lesson_scoped_chunks_index_and_job(
        self, make_user, make_presentation, db_session
    ) -> None:
        user = await make_user()
        presentation = await make_presentation(user.id)
        lesson = await _seed_lesson(db_session, user, presentation)

        with patch("app.workers.tasks.safe_dispatch") as dispatch:
            result = await _service(db_session).index_lesson(lesson.public_id)

        assert result["skipped"] is False
        assert result["scope"] == "lesson"
        assert result["chunks"] > 0

        chunks = (await db_session.execute(select(DocumentChunk))).scalars().all()
        assert len(chunks) == result["chunks"]
        assert all(chunk.source == ChunkSource.LESSON.value for chunk in chunks)
        assert all(chunk.lesson_id == lesson.id for chunk in chunks)
        assert all(chunk.lesson_version_id is not None for chunk in chunks)
        assert all(chunk.presentation_id is None for chunk in chunks)

        index = (
            await db_session.execute(select(VectorIndex))
        ).scalar_one()
        assert index.index_type == VectorIndexType.LESSON.value
        assert index.lesson_id == lesson.id
        assert index.presentation_id is None

        job = (await db_session.execute(select(EmbeddingJob))).scalar_one()
        assert job.job_type == EmbeddingJobType.INDEX.value
        assert job.lesson_id == lesson.id
        assert job.presentation_id is None
        assert job.idempotency_key is not None
        assert job.idempotency_key.startswith("index:lesson:")

        dispatch.assert_called_once()

    async def test_rejects_without_succeeded_version(
        self, make_user, make_presentation, db_session
    ) -> None:
        user = await make_user()
        presentation = await make_presentation(user.id)
        lesson = await _seed_lesson(
            db_session,
            user,
            presentation,
            version_status=LessonVersionStatus.FAILED.value,
        )

        with pytest.raises(RagIndexingError):
            await _service(db_session).index_lesson(lesson.public_id)

        assert await _count(db_session, DocumentChunk) == 0
        assert await _count(db_session, EmbeddingJob) == 0
        assert await _count(db_session, VectorIndex) == 0
