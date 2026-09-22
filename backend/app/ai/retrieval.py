"""Bounded, learner-scoped semantic retrieval (shared RAG ranking).

This is the single semantic-retrieval implementation used across the tutoring
and learning-assistant services. It avoids a second embedding architecture by
building entirely on the existing ``EmbeddingProvider`` abstraction and the
persisted ``ChunkEmbedding`` rows produced by the chunk pipeline.

Design notes
------------
* Primary path: the user query is embedded, then candidate chunk/embedding
  pairs (already filtered to soft-deleted-safe rows by the repository) are
  ranked by application-side cosine similarity. This is symmetric with the
  chunk pipeline's provider/model, so values written at indexing time are
  directly comparable at retrieval time.
* A single malformed pair (null, empty, non-numeric, dimension-mismatched, or
  zero-norm vector) is skipped, never allowed to abort the whole operation.
* Deterministic tie-breakers: ``similarity DESC -> position ASC -> chunk id``.
* When no query can be embedded, no embeddings exist for the content units,
  nothing passes the similarity floor, or an error occurs, the caller falls
  back to the deterministic positional path (which is kept in the services).

Scaling boundary (documented decision, D6)
------------------------------------------
Retrieval is deliberately application-side cosine over the persisted
``ChunkEmbedding`` rows (candidate cap ``TUTOR_EMBEDDING_SEARCH_LIMIT`` per
content unit). This is the correct choice at the current scale: per-learner
lesson corpora, ≤200 candidate vectors per query, SQLite-test-compatible, and
no external vector database dependency in the deployment contract.

When the corpus grows beyond what an in-memory linear scan can serve (tens of
thousands of embeddings per query at sub-second latency), migrate to a
database-native approximate/indexed search WITHOUT changing the retrieval
contract: implement the same ``Session``-shaped candidate source used here
(normalized float vectors + similarity) behind a new repository method backed
by ``pgvector`` (``pgvector.sqlalchemy``) and select it via a setting such as
``TUTOR_VECTOR_SEARCH_BACKEND="pgvector"``. The ranking math, tie-breakers and
fallback path in this module must remain the single source of truth.

NOTE: PostgreSQL/pgvector behavior has NOT been verified in this environment
(no PostgreSQL instance is available); the app-side path is the only verified
execution path.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings.base import EmbeddingProvider
from app.core.config import settings
from app.repositories.rag_repository import DocumentChunkRepository

_CONTENT_CAP = 500
_SNIPPET_CAP = 200


def cosine_similarity(
    query: list[float] | None,
    candidate: list[float] | None,
) -> float | None:
    """Numerically safe cosine similarity between two vectors.

    Returns ``None`` (rather than raising) when either vector is missing,
    empty, non-numeric, dimension-mismatched, or zero-norm, so a single
    malformed vector can never crash the surrounding retrieval operation.
    The returned value is always finite and lies in ``[-1, 1]``.
    """
    if not query or not candidate:
        return None
    if len(query) != len(candidate):
        return None
    dot: float = 0.0
    norm_q: float = 0.0
    norm_c: float = 0.0
    try:
        for q, c in zip(query, candidate, strict=False):
            q = float(q)
            c = float(c)
            dot += q * c
            norm_q += q * q
            norm_c += c * c
    except (TypeError, ValueError):
        return None
    if norm_q == 0.0 or norm_c == 0.0:
        return None
    denom = (norm_q * norm_c) ** 0.5
    if not denom or denom != denom:
        return None
    sim = dot / denom
    if sim != sim or sim in (float("inf"), float("-inf")):
        return None
    if sim > 1.0:
        return 1.0
    if sim < -1.0:
        return -1.0
    return float(sim)


async def semantic_retrieve_chunks(
    session: AsyncSession,
    *,
    user_query: str,
    content_unit_ids: list[uuid.UUID],
    limit: int,
    provider: EmbeddingProvider | None = None,
) -> list[str]:
    """Rank the learner's own chunk/embedding pairs by cosine similarity.

    Returns the content of the top ``limit`` chunks (each capped at 500 chars)
    that match the query's embedding above ``TUTOR_RETRIEVAL_SIMILARITY_THRESHOLD``,
    ordered ``similarity DESC -> position ASC -> chunk id ASC``. Returns ``[]``
    when the query cannot be embedded, no embeddings exist, nothing clears the
    floor, or an error occurs — signalling the caller to use its positional
    fallback.

    Backed by :func:`semantic_retrieve_chunks_with_meta`; convenience wrapper
    for the conversational services that only need the raw chunk text.
    """
    ranked = await semantic_retrieve_chunks_with_meta(
        session,
        user_query=user_query,
        content_unit_ids=content_unit_ids,
        limit=limit,
        provider=provider,
    )
    return [chunk.content for chunk in ranked]


@dataclass(frozen=True)
class RetrievedChunk:
    """A ranked retrieval hit with enough provenance to verify grounding.

    ``similarity`` is the app-side cosine score used for ranking; ``snippet``
    is a short excerpt for attribution UIs; ``position`` is the chunk's order
    within the source content unit (its slide/section position).
    """

    chunk_id: uuid.UUID
    content_unit_id: uuid.UUID | None
    position: int
    similarity: float
    content: str
    snippet: str


async def semantic_retrieve_chunks_with_meta(
    session: AsyncSession,
    *,
    user_query: str,
    content_unit_ids: list[uuid.UUID],
    limit: int,
    provider: EmbeddingProvider | None = None,
) -> list[RetrievedChunk]:
    """Ranked retrieval that exposes per-hit provenance metadata.

    Same ranking contract as :func:`semantic_retrieve_chunks`
    (``similarity DESC -> position ASC -> chunk id ASC``, similarity floor
    ``TUTOR_RETRIEVAL_SIMILARITY_THRESHOLD``, content capped at 500 chars,
    deterministic) but returns structured hits carrying the chunk id, owning
    content-unit id, source position, similarity score, and a short snippet so
    callers can surface exact source references.
    """
    pairs = await _ranked_pairs(
        session,
        user_query=user_query,
        content_unit_ids=content_unit_ids,
        provider=provider,
    )
    return [
        RetrievedChunk(
            chunk_id=chunk.id,
            content_unit_id=chunk.content_unit_id,
            position=chunk.position or 0,
            similarity=similarity,
            content=content,
            snippet=content[:_SNIPPET_CAP],
        )
        for similarity, _, chunk, content in pairs[:limit]
    ]


async def _ranked_pairs(
    session: AsyncSession,
    *,
    user_query: str,
    content_unit_ids: list[uuid.UUID],
    provider: EmbeddingProvider | None,
) -> list[tuple[float, int, Any, str]]:
    """Shared ranking core: returns ``(similarity, position, chunk, content)``."""
    try:
        if provider is None:
            from app.ai.embeddings.factory import get_embedding_provider

            provider = get_embedding_provider()

        if provider is None or not user_query or not user_query.strip():
            return []

        response = await provider.embed([user_query])
        if not response.vectors:
            return []
        query_vector = response.vectors[0]

        pairs = await DocumentChunkRepository(session).list_embedded_pairs_for_content_units(
            content_unit_ids=content_unit_ids,
            provider=provider.name or provider.config.provider,
            model=provider.model,
            limit=settings.TUTOR_EMBEDDING_SEARCH_LIMIT,
        )

        scored: list[tuple[float, int, Any, str]] = []
        for chunk, embedding in pairs:
            chunk_vector: Any = embedding.vector
            similarity = cosine_similarity(query_vector, chunk_vector)
            if similarity is None:
                continue
            if similarity < settings.TUTOR_RETRIEVAL_SIMILARITY_THRESHOLD:
                continue
            content = (chunk.content or "")[:_CONTENT_CAP]
            if not content:
                continue
            scored.append((similarity, chunk.position or 0, chunk, content))

        # Deterministic: similarity desc, then position asc, then chunk id.
        scored.sort(key=lambda item: (-item[0], item[1], item[2].id))
        return scored
    except Exception:
        return []
