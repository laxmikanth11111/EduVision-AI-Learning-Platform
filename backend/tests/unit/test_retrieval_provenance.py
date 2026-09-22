"""Provenance tests for ``app.ai.retrieval``.

Proves that ``semantic_retrieve_chunks_with_meta`` returns structured,
deterministic retrieval hits carrying source provenance (chunk id, owning
content-unit id, position, similarity, snippet) and that
``semantic_retrieve_chunks`` (the content-only wrapper) is unchanged in its
contract — query->embedding->cosine ranking->grounded context.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings.base import EmbeddingProvider
from app.ai.embeddings.config import EmbeddingProviderConfig
from app.ai.embeddings.models import (
    EmbeddingHealthStatus,
    EmbeddingProviderInfo,
    EmbeddingResponse,
)
from app.ai.retrieval import (
    RetrievedChunk,
    semantic_retrieve_chunks,
    semantic_retrieve_chunks_with_meta,
)
from app.models.chunk_embedding import ChunkEmbedding
from app.models.content_unit import ContentUnit
from app.models.document_chunk import DocumentChunk
from app.models.presentation import Presentation
from shared.constants import ContentUnitType, EmbeddingVersionStatus

FAKE_PROVIDER = "fake"
FAKE_MODEL = "fake-model"


class _FakeEmbeddingProvider(EmbeddingProvider):
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


async def _seed(db_session: AsyncSession, marker: str = "photosynthesis") -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    presentation = Presentation(
        title="Sci Deck", owner_id=uuid.uuid4(), status="draft", visibility="private"
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

    chunk = DocumentChunk(
        content_unit_id=unit.id,
        content=f"Notes about {marker} and light energy conversions.",
        position=1,
        level=0,
        source="presentation",
        chunk_type="paragraph",
        token_count=5,
        character_count=40,
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
            dimension=2,
            vector=[1.0, 0.0],
            status=EmbeddingVersionStatus.ACTIVE.value,
            version=1,
            deleted_at=None,
        )
    )
    await db_session.flush()
    return presentation.id, unit.id, chunk.id


@pytest.mark.asyncio
async def test_with_meta_returns_provenance_fields(db_session: AsyncSession) -> None:
    _, unit_id, chunk_id = await _seed(db_session)
    provider = _FakeEmbeddingProvider(vector=[1.0, 0.0])

    hits = await semantic_retrieve_chunks_with_meta(
        db_session,
        user_query="photosynthesis light energy",
        content_unit_ids=[unit_id],
        limit=5,
        provider=provider,
    )

    assert len(hits) == 1
    hit = hits[0]
    assert isinstance(hit, RetrievedChunk)
    assert hit.chunk_id == chunk_id
    assert hit.content_unit_id == unit_id
    assert hit.position == 1
    assert hit.similarity == pytest.approx(1.0)
    assert "photosynthesis" in hit.content
    assert hit.snippet
    assert len(hit.snippet) <= len(hit.content)


@pytest.mark.asyncio
async def test_with_meta_wrapper_matches_content_only_contract(
    db_session: AsyncSession,
) -> None:
    _, unit_id, _ = await _seed(db_session)
    provider = _FakeEmbeddingProvider(vector=[1.0, 0.0])

    contents = await semantic_retrieve_chunks(
        db_session,
        user_query="photosynthesis",
        content_unit_ids=[unit_id],
        limit=5,
        provider=provider,
    )
    meta = await semantic_retrieve_chunks_with_meta(
        db_session,
        user_query="photosynthesis",
        content_unit_ids=[unit_id],
        limit=5,
        provider=provider,
    )

    assert contents == [hit.content for hit in meta]
    assert contents
    assert "photosynthesis" in contents[0]


@pytest.mark.asyncio
async def test_deterministic_ordering_and_limit(db_session: AsyncSession) -> None:
    _, unit_id, _ = await _seed(db_session)
    provider = _FakeEmbeddingProvider(vector=[1.0, 0.0])

    a = await semantic_retrieve_chunks_with_meta(
        db_session,
        user_query="photosynthesis",
        content_unit_ids=[unit_id],
        limit=5,
        provider=provider,
    )
    b = await semantic_retrieve_chunks_with_meta(
        db_session,
        user_query="photosynthesis",
        content_unit_ids=[unit_id],
        limit=5,
        provider=provider,
    )
    assert [h.chunk_id for h in a] == [h.chunk_id for h in b]

    limited = await semantic_retrieve_chunks_with_meta(
        db_session,
        user_query="photosynthesis",
        content_unit_ids=[unit_id],
        limit=0,
        provider=provider,
    )
    assert limited == []


@pytest.mark.asyncio
async def test_with_meta_returns_empty_when_provider_has_no_vectors(
    db_session: AsyncSession,
) -> None:
    _, unit_id, _ = await _seed(db_session)

    class _Empty(_FakeEmbeddingProvider):
        async def embed(self, texts: list[str], **kwargs: object) -> EmbeddingResponse:
            return EmbeddingResponse(vectors=[], dimension=2, provider=self.name, model=self.model)

    hits = await semantic_retrieve_chunks_with_meta(
        db_session,
        user_query="photosynthesis",
        content_unit_ids=[unit_id],
        limit=5,
        provider=_Empty(),
    )
    assert hits == []


@pytest.mark.asyncio
async def test_with_meta_respects_similarity_floor(db_session: AsyncSession) -> None:
    _, unit_id, _ = await _seed(db_session)
    provider = _FakeEmbeddingProvider(vector=[0.0, 1.0])

    from app.core.config import settings

    assert settings.TUTOR_RETRIEVAL_SIMILARITY_THRESHOLD > 0.0
    hits = await semantic_retrieve_chunks_with_meta(
        db_session,
        user_query="unrelated query about history",
        content_unit_ids=[unit_id],
        limit=5,
        provider=provider,
    )
    # Query vector [0,1] vs chunk vector [1,0] is orthogonal (sim 0.0), which
    # sits below the retrieval floor, so nothing must be returned.
    assert hits == []
