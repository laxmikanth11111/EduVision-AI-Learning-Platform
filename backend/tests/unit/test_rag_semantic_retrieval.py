from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings.base import EmbeddingProvider
from app.ai.embeddings.config import EmbeddingProviderConfig
from app.ai.embeddings.models import (
    EmbeddingHealthStatus,
    EmbeddingProviderInfo,
    EmbeddingResponse,
)
from app.database.unit_of_work import UnitOfWork
from app.models.chunk_embedding import ChunkEmbedding
from app.models.content_unit import ContentUnit
from app.models.document_chunk import DocumentChunk
from app.models.generated_lesson import GeneratedLesson
from app.ai.retrieval import cosine_similarity as _cosine_similarity
from app.services.learning_assistant_service import LearningAssistantService
from shared.constants import ContentUnitType, EmbeddingVersionStatus, LessonStatus

FAKE_PROVIDER = "fake"
FAKE_MODEL = "fake-model"


class _FakeEmbeddingProvider(EmbeddingProvider):
    """Deterministic in-memory provider with controllable query embeddings."""

    name = FAKE_PROVIDER
    requires_api_key = False
    default_model = FAKE_MODEL

    def __init__(
        self,
        *,
        vector: list[float] | None = None,
        fail: bool = False,
        empty: bool = False,
    ) -> None:
        super().__init__(
            EmbeddingProviderConfig(
                provider=FAKE_PROVIDER,
                model=FAKE_MODEL,
                dimension=2,
            )
        )
        self._vector = [1.0, 0.0] if vector is None else vector
        self._fail = fail
        self._empty = empty

    def info(self) -> EmbeddingProviderInfo:
        return EmbeddingProviderInfo(
            provider=self.name,
            model=self.model,
            dimension=2,
        )

    async def health_check(self) -> EmbeddingHealthStatus:
        return EmbeddingHealthStatus(healthy=True, provider=self.name, model=self.model)

    async def embed(self, texts: list[str], **kwargs: object) -> EmbeddingResponse:
        if self._fail:
            raise RuntimeError("embedding provider unavailable")
        if self._empty:
            return EmbeddingResponse(vectors=[], dimension=2, provider=self.name, model=self.model)
        vectors = [self._vector] * len(texts)
        return EmbeddingResponse(
            vectors=vectors,
            dimension=len(self._vector or []),
            provider=self.name,
            model=self.model,
        )


async def _seed_content_unit(
    db_session: AsyncSession,
    presentation_id: uuid.UUID,
    position: int = 0,
) -> ContentUnit:
    unit = ContentUnit(
        presentation_id=presentation_id,
        unit_type=ContentUnitType.DOCUMENT.value,
        position=position,
        title=f"Unit {position}",
    )
    db_session.add(unit)
    await db_session.flush()
    return unit


async def _seed_lesson(
    db_session: AsyncSession,
    user_id: uuid.UUID,
    presentation_id: uuid.UUID,
) -> GeneratedLesson:
    lesson = GeneratedLesson(
        presentation_id=presentation_id,
        user_id=user_id,
        mode="ai_generated",
        status=LessonStatus.READY.value,
        latest_version=1,
    )
    db_session.add(lesson)
    await db_session.flush()
    return lesson


async def _seed_chunk(
    db_session: AsyncSession,
    *,
    content_unit_id: uuid.UUID,
    position: int,
    content: str,
    vector: list[float],
    deleted: bool = False,
) -> DocumentChunk:
    chunk = DocumentChunk(
        content_unit_id=content_unit_id,
        content=content,
        position=position,
        level=0,
        source="presentation",
        chunk_type="paragraph",
        token_count=5,
        character_count=len(content),
        status="ready",
        deleted_at=datetime.now(UTC) if deleted else None,
    )
    db_session.add(chunk)
    await db_session.flush()
    embedding = ChunkEmbedding(
        chunk_id=chunk.id,
        provider=FAKE_PROVIDER,
        model=FAKE_MODEL,
        dimension=len(vector),
        vector=vector,
        status=EmbeddingVersionStatus.ACTIVE.value,
        version=1,
        deleted_at=datetime.now(UTC) if deleted else None,
    )
    db_session.add(embedding)
    await db_session.flush()
    return chunk


async def _make_service(db_session: AsyncSession) -> LearningAssistantService:
    uow = UnitOfWork(session=db_session)
    return LearningAssistantService(uow)


# ── Module-level numerical safety (pure function) ──────────────────────────


def test_cosine_identical_vectors() -> None:
    assert _cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)


def test_cosine_zero_norm_returns_none() -> None:
    assert _cosine_similarity([0.0, 0.0], [1.0, 0.0]) is None
    assert _cosine_similarity([1.0, 0.0], [0.0, 0.0]) is None


def test_cosine_empty_vectors_returns_none() -> None:
    assert _cosine_similarity([], [1.0]) is None
    assert _cosine_similarity([1.0], []) is None


def test_cosine_dimension_mismatch_returns_none() -> None:
    assert _cosine_similarity([1.0, 0.0], [1.0]) is None


def test_cosine_malformed_returns_none() -> None:
    assert _cosine_similarity(["a", 0.0], [1.0, 0.0]) is None


def test_cosine_none_vectors_returns_none() -> None:
    assert _cosine_similarity(None, [1.0, 0.0]) is None
    assert _cosine_similarity([1.0, 0.0], None) is None


def test_cosine_orthogonal_returns_zero() -> None:
    assert _cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_cosine_returns_finite_clamped_value() -> None:
    sim = _cosine_similarity([1.0, 0.0], [0.7071, 0.7071])
    assert sim is not None
    assert sim == pytest.approx(0.7071, abs=1e-3)
    assert -1.0 <= sim <= 1.0


# ── End-to-end semantic retrieval ──────────────────────────────────────────


async def _seed_scenario(db_session: AsyncSession, user_id: uuid.UUID) -> GeneratedLesson:
    """One presentation with a content unit + a query-aligning chunk.

    Returns the lesson so tests can scope retrieval to it.
    """
    from app.models.presentation import Presentation

    presentation = Presentation(
        title="Sci Presentation",
        owner_id=user_id,
        status="draft",
        visibility="private",
    )
    db_session.add(presentation)
    await db_session.flush()

    unit = await _seed_content_unit(db_session, presentation.id, position=0)
    await _seed_chunk(
        db_session,
        content_unit_id=unit.id,
        position=0,
        content="First chunk about photosynthesis and light energy.",
        vector=[1.0, 0.0],
    )
    await _seed_chunk(
        db_session,
        content_unit_id=unit.id,
        position=1,
        content="Unrelated chunk about medieval history.",
        vector=[0.0, 1.0],
    )
    return await _seed_lesson(db_session, user_id, presentation.id)


@pytest.mark.asyncio
async def test_semantic_high_similarity_ranks_first(db_session: AsyncSession) -> None:
    lesson = await _seed_scenario(db_session, uuid.uuid4())
    service = await _make_service(db_session)
    provider = _FakeEmbeddingProvider(vector=[1.0, 0.0])
    result = await service._retrieve_relevant_chunks(
        "photosynthesis light energy", lesson.id, limit=2, provider=provider
    )
    assert result
    assert "photosynthesis" in result[0]


@pytest.mark.asyncio
async def test_lower_similarity_ranks_below_higher(db_session: AsyncSession) -> None:
    presentation = app_presentation()
    db_session.add(presentation)
    await db_session.flush()
    unit = await _seed_content_unit(db_session, presentation.id, position=0)
    await _seed_chunk(
        db_session, content_unit_id=unit.id, position=0, content="high-sim", vector=[1.0, 0.0]
    )
    await _seed_chunk(
        db_session, content_unit_id=unit.id, position=1, content="lower-sim", vector=[0.8, 0.6]
    )
    lesson = await _seed_lesson(db_session, uuid.uuid4(), presentation.id)
    service = await _make_service(db_session)
    provider = _FakeEmbeddingProvider(vector=[1.0, 0.0])
    result = await service._retrieve_relevant_chunks(
        "photosynthesis light energy", lesson.id, limit=2, provider=provider
    )
    # [1,0] (sim 1.0) must rank before [0.8,0.6] (sim 0.8); both pass the floor.
    assert "high-sim" in result[0]
    assert "lower-sim" in result[1]


@pytest.mark.asyncio
async def test_top_k_limit_is_respected(db_session: AsyncSession) -> None:
    lesson = await _seed_scenario(db_session, uuid.uuid4())
    service = await _make_service(db_session)
    provider = _FakeEmbeddingProvider(vector=[1.0, 0.0])
    result = await service._retrieve_relevant_chunks(
        "photosynthesis light energy", lesson.id, limit=1, provider=provider
    )
    assert len(result) == 1
    assert "photosynthesis" in result[0]


@pytest.mark.asyncio
async def test_deterministic_ordering_for_equal_similarity(db_session: AsyncSession) -> None:
    # Two chunks identical-aligned with the query -> tie resolved by position.
    presentation = app_presentation()
    db_session.add(presentation)
    await db_session.flush()
    unit = await _seed_content_unit(db_session, presentation.id, position=0)
    await _seed_chunk(
        db_session, content_unit_id=unit.id, position=0, content="alpha", vector=[1.0, 0.0]
    )
    await _seed_chunk(
        db_session, content_unit_id=unit.id, position=1, content="beta", vector=[1.0, 0.0]
    )
    lesson = await _seed_lesson(db_session, uuid.uuid4(), presentation.id)
    service = await _make_service(db_session)
    provider = _FakeEmbeddingProvider(vector=[1.0, 0.0])
    result = await service._retrieve_relevant_chunks(
        "q", lesson.id, limit=2, provider=provider
    )
    assert result == ["alpha", "beta"]


@pytest.mark.asyncio
async def test_zero_norm_vector_skipped_not_crash(db_session: AsyncSession) -> None:
    presentation = app_presentation()
    db_session.add(presentation)
    await db_session.flush()
    unit = await _seed_content_unit(db_session, presentation.id, position=0)
    await _seed_chunk(
        db_session, content_unit_id=unit.id, position=0, content="zero", vector=[0.0, 0.0]
    )
    await _seed_chunk(
        db_session, content_unit_id=unit.id, position=1, content="good", vector=[1.0, 0.0]
    )
    lesson = await _seed_lesson(db_session, uuid.uuid4(), presentation.id)
    service = await _make_service(db_session)
    provider = _FakeEmbeddingProvider(vector=[1.0, 0.0])
    result = await service._retrieve_relevant_chunks("q", lesson.id, limit=2, provider=provider)
    assert "good" in result
    assert "zero" not in result


@pytest.mark.asyncio
async def test_dimension_mismatch_skipped_not_crash(db_session: AsyncSession) -> None:
    presentation = app_presentation()
    db_session.add(presentation)
    await db_session.flush()
    unit = await _seed_content_unit(db_session, presentation.id, position=0)
    await _seed_chunk(
        db_session, content_unit_id=unit.id, position=0, content="wrong-dim", vector=[1.0, 0.0, 1.0]
    )
    await _seed_chunk(
        db_session, content_unit_id=unit.id, position=1, content="good", vector=[1.0, 0.0]
    )
    lesson = await _seed_lesson(db_session, uuid.uuid4(), presentation.id)
    service = await _make_service(db_session)
    provider = _FakeEmbeddingProvider(vector=[1.0, 0.0])
    result = await service._retrieve_relevant_chunks("q", lesson.id, limit=2, provider=provider)
    assert "good" in result
    assert "wrong-dim" not in result


@pytest.mark.asyncio
async def test_malformed_vector_skipped_not_crash(db_session: AsyncSession) -> None:
    presentation = app_presentation()
    db_session.add(presentation)
    await db_session.flush()
    unit = await _seed_content_unit(db_session, presentation.id, position=0)
    await _seed_chunk(
        db_session,
        content_unit_id=unit.id,
        position=0,
        content="malformed",
        vector=["nope", 0.0],
    )
    await _seed_chunk(
        db_session, content_unit_id=unit.id, position=1, content="good", vector=[1.0, 0.0]
    )
    lesson = await _seed_lesson(db_session, uuid.uuid4(), presentation.id)
    service = await _make_service(db_session)
    provider = _FakeEmbeddingProvider(vector=[1.0, 0.0])
    result = await service._retrieve_relevant_chunks("q", lesson.id, limit=2, provider=provider)
    assert "good" in result
    assert "malformed" not in result


@pytest.mark.asyncio
async def test_missing_vector_handled_safely(db_session: AsyncSession) -> None:
    presentation = app_presentation()
    db_session.add(presentation)
    await db_session.flush()
    unit = await _seed_content_unit(db_session, presentation.id, position=0)
    chunk = DocumentChunk(
        content_unit_id=unit.id,
        content="no vector",
        position=0,
        level=0,
        source="presentation",
        chunk_type="paragraph",
    )
    db_session.add(chunk)
    await db_session.flush()
    db_session.add(
        ChunkEmbedding(
            chunk_id=chunk.id,
            provider=FAKE_PROVIDER,
            model=FAKE_MODEL,
            dimension=0,
            vector=None,
            status=EmbeddingVersionStatus.ACTIVE.value,
            version=1,
        )
    )
    await _seed_chunk(
        db_session, content_unit_id=unit.id, position=1, content="good", vector=[1.0, 0.0]
    )
    lesson = await _seed_lesson(db_session, uuid.uuid4(), presentation.id)
    service = await _make_service(db_session)
    provider = _FakeEmbeddingProvider(vector=[1.0, 0.0])
    result = await service._retrieve_relevant_chunks("q", lesson.id, limit=2, provider=provider)
    assert "no vector" not in result
    assert "good" in result


@pytest.mark.asyncio
async def test_no_valid_semantic_vectors_triggers_fallback(db_session: AsyncSession) -> None:
    presentation = app_presentation()
    db_session.add(presentation)
    await db_session.flush()
    unit = await _seed_content_unit(db_session, presentation.id, position=0)
    await _seed_chunk(
        db_session, content_unit_id=unit.id, position=1, content="first", vector=[1.0, 0.0]
    )
    await _seed_chunk(
        db_session, content_unit_id=unit.id, position=0, content="zeroth", vector=[1.0, 0.0]
    )
    lesson = await _seed_lesson(db_session, uuid.uuid4(), presentation.id)
    service = await _make_service(db_session)
    # Embedding provider returns an empty vector list -> nothing to rank.
    provider = _FakeEmbeddingProvider(empty=True)
    result = await service._retrieve_relevant_chunks("q", lesson.id, limit=2, provider=provider)
    # Fallback is positional: position 0 first, then position 1.
    assert result == ["zeroth", "first"]


@pytest.mark.asyncio
async def test_embedding_failure_triggers_fallback(db_session: AsyncSession) -> None:
    presentation = app_presentation()
    db_session.add(presentation)
    await db_session.flush()
    unit = await _seed_content_unit(db_session, presentation.id, position=0)
    await _seed_chunk(
        db_session, content_unit_id=unit.id, position=0, content="zeroth", vector=[1.0, 0.0]
    )
    lesson = await _seed_lesson(db_session, uuid.uuid4(), presentation.id)
    service = await _make_service(db_session)
    provider = _FakeEmbeddingProvider(fail=True)
    result = await service._retrieve_relevant_chunks("q", lesson.id, limit=2, provider=provider)
    assert result == ["zeroth"]


@pytest.mark.asyncio
async def test_no_lesson_returns_empty(db_session: AsyncSession) -> None:
    service = await _make_service(db_session)
    result = await service._retrieve_relevant_chunks("q", uuid.uuid4(), limit=2)
    assert result == []


@pytest.mark.asyncio
async def test_query_without_provider_uses_positional_fallback(db_session: AsyncSession) -> None:
    presentation = app_presentation()
    db_session.add(presentation)
    await db_session.flush()
    unit = await _seed_content_unit(db_session, presentation.id, position=0)
    await _seed_chunk(
        db_session, content_unit_id=unit.id, position=0, content="zeroth", vector=[1.0, 0.0]
    )
    lesson = await _seed_lesson(db_session, uuid.uuid4(), presentation.id)
    service = await _make_service(db_session)
    # provider=None means no embedding generation attempt -> positional fallback.
    result = await service._retrieve_relevant_chunks("q", lesson.id, limit=2, provider=None)
    assert result == ["zeroth"]


async def _seed_user_lesson_with_chunk(
    db_session: AsyncSession,
    *,
    owner_id: uuid.UUID,
    content: str,
    vector: list[float],
    deleted: bool = False,
) -> GeneratedLesson:
    """Create one user-owned presentation/lesson/content-unit/chunk chain."""
    presentation = app_presentation()
    presentation.owner_id = owner_id
    db_session.add(presentation)
    await db_session.flush()
    unit = await _seed_content_unit(db_session, presentation.id, position=0)
    await _seed_chunk(
        db_session,
        content_unit_id=unit.id,
        position=0,
        content=content,
        vector=vector,
        deleted=deleted,
    )
    return await _seed_lesson(db_session, owner_id, presentation.id)


@pytest.mark.asyncio
async def test_retrieval_scoped_to_authorized_lesson_excludes_other_user(
    db_session: AsyncSession,
) -> None:
    # User A owns a lesson; user B owns a separate presentation with a
    # highly-similar chunk. Retrieval is scoped by the caller's lesson, so
    # user B's chunk must never surface even though it lives in the same DB.
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()
    lesson_a = await _seed_user_lesson_with_chunk(
        db_session, owner_id=user_a, content="user-a-only", vector=[1.0, 0.0]
    )
    await _seed_user_lesson_with_chunk(
        db_session, owner_id=user_b, content="user-b-secret", vector=[1.0, 0.0]
    )
    service = await _make_service(db_session)
    provider = _FakeEmbeddingProvider(vector=[1.0, 0.0])
    result = await service._retrieve_relevant_chunks(
        "shared topic", lesson_a.id, limit=2, provider=provider
    )
    assert "user-a-only" in result
    assert "user-b-secret" not in result


@pytest.mark.asyncio
async def test_soft_deleted_chunk_is_excluded_from_semantic_retrieval(
    db_session: AsyncSession,
) -> None:
    # An active and a highly-relevant soft-deleted chunk share the SAME
    # presentation/content unit. The soft-deleted chunk (DocumentChunk.deleted_at
    # set) must be excluded by the retrieval repository predicate, not ranked
    # as a hit — even though it would otherwise out-rank nothing.
    user = uuid.uuid4()
    presentation = app_presentation()
    presentation.owner_id = user
    db_session.add(presentation)
    await db_session.flush()
    unit = await _seed_content_unit(db_session, presentation.id, position=0)
    await _seed_chunk(
        db_session,
        content_unit_id=unit.id,
        position=0,
        content="active-chunk",
        vector=[1.0, 0.0],
    )
    await _seed_chunk(
        db_session,
        content_unit_id=unit.id,
        position=1,
        content="soft-deleted-chunk",
        vector=[1.0, 0.0],
        deleted=True,
    )
    lesson = await _seed_lesson(db_session, user, presentation.id)
    service = await _make_service(db_session)
    provider = _FakeEmbeddingProvider(vector=[1.0, 0.0])
    result = await service._retrieve_relevant_chunks(
        "relevant", lesson.id, limit=2, provider=provider
    )
    assert "active-chunk" in result
    assert "soft-deleted-chunk" not in result


def app_presentation():
    import app.models.presentation as presentation_mod

    return presentation_mod.Presentation(
        title="P", owner_id=uuid.uuid4(), status="draft", visibility="private"
    )
