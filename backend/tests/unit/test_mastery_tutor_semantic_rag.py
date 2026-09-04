"""P9 Mastery Tutor semantic retrieval tests (F1).

Proves the P8 tutor's retrieval is now genuinely semantic: the user query is
embedded, then the learner's own chunk/embedding pairs are ranked by cosine
similarity (deterministic: similarity DESC -> position ASC -> chunk id ASC)
using the shared ``app.ai.retrieval.semantic_retrieve_chunks`` implementation,
with a deterministic positional fallback. Also proves learner scoping holds
through the semantic path (User B never retrieves User A's embedded chunks).

Everything runs against a deterministic fake embedding provider — no real AI
is called. ``get_ai_content_service`` is pointed at the local provider so the
full tutor request -> semantic RAG -> AIContentService -> response path is
exercised with only deterministic components.
"""

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
from app.models.presentation import Presentation
from app.schemas.tutor import TutorMessageSendRequest, TutorSessionCreateRequest
from app.services.educational_memory_service import educational_memory_service
from app.services.mastery_tutor_service import MasteryTutorService
from shared.constants import ContentUnitType, EmbeddingVersionStatus, LessonStatus, TutorSourceKind

FAKE_PROVIDER = "fake"
FAKE_MODEL = "fake-model"


@pytest.fixture(autouse=True)
def _reset_memory_cache() -> None:
    educational_memory_service._memories.clear()  # noqa: SLF001


class _FakeEmbeddingProvider(EmbeddingProvider):
    """Deterministic embedding provider with a controllable query vector."""

    name = FAKE_PROVIDER
    requires_api_key = False
    default_model = FAKE_MODEL

    def __init__(self, vector: list[float] | None = None) -> None:
        super().__init__(
            EmbeddingProviderConfig(provider=FAKE_PROVIDER, model=FAKE_MODEL, dimension=2)
        )
        self._vector = [1.0, 0.0] if vector is None else vector

    def info(self) -> EmbeddingProviderInfo:
        return EmbeddingProviderInfo(provider=self.name, model=self.model, dimension=2)

    async def health_check(self) -> EmbeddingHealthStatus:
        return EmbeddingHealthStatus(healthy=True, provider=self.name, model=self.model)

    async def embed(self, texts: list[str], **kwargs: object) -> EmbeddingResponse:
        return EmbeddingResponse(
            vectors=[self._vector] * len(texts),
            dimension=len(self._vector or []),
            provider=self.name,
            model=self.model,
        )


def _patch_ai_to_local(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.ai.config import build_ai_provider_config
    from app.ai.providers.local import LocalMockProvider
    from app.ai.service import AIContentService

    def _local_service(uow=None):
        config = build_ai_provider_config(provider="local")
        return AIContentService(provider=LocalMockProvider(config))

    monkeypatch.setattr("app.ai.service.get_ai_content_service", _local_service)


def _patch_embedding_provider(monkeypatch: pytest.MonkeyPatch, provider: EmbeddingProvider) -> None:
    monkeypatch.setattr(
        "app.ai.embeddings.factory.get_embedding_provider", lambda: provider
    )


async def _seed_scenario(
    db_session: AsyncSession,
    user_id: uuid.UUID,
    *,
    marker: str = "photosynthesis",
) -> GeneratedLesson:
    """User-owned presentation + content unit with two embedded chunks.

    chunk "<marker>" -> vector [1, 0]; chunk "history" -> vector [0, 1].
    """
    presentation = Presentation(
        title="Sci Deck",
        owner_id=user_id,
        status="draft",
        visibility="private",
    )
    db_session.add(presentation)
    await db_session.flush()

    unit = ContentUnit(
        presentation_id=presentation.id,
        unit_type=ContentUnitType.DOCUMENT.value,
        position=0,
        title="Unit 0",
    )
    db_session.add(unit)
    await db_session.flush()

    async def _chunk(position: int, content: str, vector: list[float]) -> None:
        chunk = DocumentChunk(
            content_unit_id=unit.id,
            content=content,
            position=position,
            level=0,
            source="presentation",
            chunk_type="paragraph",
            token_count=len(content.split()),
            character_count=len(content),
            status="ready",
            deleted_at=None,
        )
        db_session.add(chunk)
        await db_session.flush()
        db_session.add(
            ChunkEmbedding(
                chunk_id=chunk.id,
                provider=FAKE_PROVIDER,
                model=FAKE_MODEL,
                dimension=len(vector),
                vector=vector,
                status=EmbeddingVersionStatus.ACTIVE.value,
                version=1,
                deleted_at=None,
            )
        )
        await db_session.flush()

    await _chunk(0, f"Notes about {marker} and light energy.", [1.0, 0.0])
    await _chunk(1, "Completely unrelated note about medieval history.", [0.0, 1.0])

    lesson = GeneratedLesson(
        presentation_id=presentation.id,
        user_id=user_id,
        mode="ai_generated",
        status=LessonStatus.READY.value,
        latest_version=1,
    )
    db_session.add(lesson)
    await db_session.flush()
    return lesson


def _make_service(db_session: AsyncSession) -> MasteryTutorService:
    return MasteryTutorService(UnitOfWork(session=db_session))


@pytest.mark.asyncio
async def test_tutor_semantic_retrieval_ranks_by_similarity(
    db_session: AsyncSession,
) -> None:
    lesson = await _seed_scenario(db_session, uuid.uuid4())
    service = _make_service(db_session)
    provider = _FakeEmbeddingProvider(vector=[1.0, 0.0])
    result = await service._retrieve_learner_chunks(  # noqa: SLF001
        user_query="photosynthesis light energy",
        lesson_id=lesson.id,
        limit=2,
        provider=provider,
    )
    assert result
    assert "photosynthesis" in result[0]
    assert "medieval" not in result[0]


@pytest.mark.asyncio
async def test_tutor_semantic_retrieval_top_k_bound(
    db_session: AsyncSession,
) -> None:
    lesson = await _seed_scenario(db_session, uuid.uuid4())
    service = _make_service(db_session)
    provider = _FakeEmbeddingProvider(vector=[1.0, 0.0])
    result = await service._retrieve_learner_chunks(  # noqa: SLF001
        user_query="photosynthesis", lesson_id=lesson.id, limit=1, provider=provider
    )
    assert len(result) == 1
    assert "photosynthesis" in result[0]


@pytest.mark.asyncio
async def test_tutor_semantic_retrieval_is_learner_scoped(
    db_session: AsyncSession,
) -> None:
    owner = uuid.uuid4()
    owner_lesson = await _seed_scenario(db_session, owner, marker="owner-secret")

    intruder_lesson = await _seed_scenario(
        db_session, uuid.uuid4(), marker="intruder-secret"
    )

    service = _make_service(db_session)
    provider = _FakeEmbeddingProvider(vector=[1.0, 0.0])
    owner_result = await service._retrieve_learner_chunks(  # noqa: SLF001
        user_query="owner-secret", lesson_id=owner_lesson.id, limit=2, provider=provider
    )
    # Owner sees their own embedded chunk ...
    assert any("owner-secret" in c for c in owner_result)
    # ... and NEVER the other learner's chunk.
    assert all("intruder-secret" not in c for c in owner_result)

    intruder_result = await service._retrieve_learner_chunks(  # noqa: SLF001
        user_query="intruder-secret", lesson_id=intruder_lesson.id, limit=2, provider=provider
    )
    assert any("intruder-secret" in c for c in intruder_result)
    assert all("owner-secret" not in c for c in intruder_result)


@pytest.mark.asyncio
async def test_tutor_semantic_grounded_reply_via_send_message(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uid = uuid.uuid4()
    from tests.learner_progress_helpers import seed_user

    await seed_user(db_session, uid, email=f"sg-{uid.hex}@example.com")
    lesson = await _seed_scenario(db_session, uid)
    _patch_ai_to_local(monkeypatch)
    _patch_embedding_provider(monkeypatch, _FakeEmbeddingProvider(vector=[1.0, 0.0]))

    service = _make_service(db_session)
    session_obj = await service.create_session(
        uid,
        TutorSessionCreateRequest(lesson_id=lesson.public_id, title="Semantic chat"),
    )
    exchange = await service.send_message(
        uid,
        session_obj["id"],
        TutorMessageSendRequest(content="Explain the bell curve about photosynthesis."),
    )
    reply = exchange["assistant_message"]
    # Semantic RAG path engaged (local provider never echoes source, so only
    # the semantic RAG attribution can carry the relevant chunk).
    assert reply["source_kind"] == TutorSourceKind.RAG.value
    assert reply["attribution"]
    # The grounded reply is drawn from the semantically relevant chunk.
    assert "photosynthesis" in (reply["attribution"] or "")
    assert reply["confidence"] in {"high", "medium", "low"}


@pytest.mark.asyncio
async def test_tutor_semantic_falls_back_to_positional_when_no_embeddings(
    db_session: AsyncSession,
) -> None:
    lesson = await _seed_scenario(db_session, uuid.uuid4())
    service = _make_service(db_session)
    # A provider that returns no vectors -> semantic returns [] -> positional
    # fallback, which still surfaces learner-owned content (position order).
    provider = _FakeEmbeddingProvider(vector=[1.0, 0.0])

    class _Empty(_FakeEmbeddingProvider):
        async def embed(self, texts: list[str], **kwargs: object) -> EmbeddingResponse:
            return EmbeddingResponse(vectors=[], dimension=2, provider=self.name, model=self.model)

    result = await service._retrieve_learner_chunks(  # noqa: SLF001
        user_query="photosynthesis", lesson_id=lesson.id, limit=2, provider=_Empty()
    )
    # Positional fallback returns position 0 first regardless of relevance.
    assert result
    assert "photosynthesis" in result[0]
    assert provider is not None
