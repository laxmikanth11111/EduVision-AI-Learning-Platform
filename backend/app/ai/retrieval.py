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
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings.base import EmbeddingProvider
from app.core.config import settings
from app.repositories.rag_repository import DocumentChunkRepository


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
    """
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

        scored: list[tuple[float, int, uuid.UUID, str]] = []
        for chunk, embedding in pairs:
            chunk_vector: Any = embedding.vector
            similarity = cosine_similarity(query_vector, chunk_vector)
            if similarity is None:
                continue
            if similarity < settings.TUTOR_RETRIEVAL_SIMILARITY_THRESHOLD:
                continue
            content = (chunk.content or "")[:500]
            if not content:
                continue
            scored.append((similarity, chunk.position or 0, chunk.id, content))

        # Deterministic: similarity desc, then position asc, then chunk id.
        scored.sort(key=lambda item: (-item[0], item[1], item[2]))
        return [content for _, _, _, content in scored[:limit]]
    except Exception:
        return []
