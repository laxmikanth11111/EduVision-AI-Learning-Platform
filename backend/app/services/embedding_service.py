"""Embedding pipeline services (Phase 4E.2).

``EmbeddingVersionService`` owns the versioning rules for stored embedding
rows; ``EmbeddingService`` drives provider calls and persists results. Both are
deliberately side-effect-safe to run inside a worker transaction.
"""

from __future__ import annotations

import asyncio
import hashlib
import uuid
from dataclasses import dataclass, field
from functools import partial

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings import create_embedding_provider
from app.ai.embeddings.base import EmbeddingProvider
from app.ai.embeddings.models import EmbeddingProviderInfo, EmbeddingResponse
from app.ai.errors import AIError, AIInvalidConfigurationError, AIInvalidResponseError
from app.ai.retry import RetryPolicy, run_with_retry
from app.core.config import settings
from app.core.logging import get_logger
from app.database.unit_of_work import UnitOfWork
from app.models.chunk_embedding import ChunkEmbedding
from app.models.document_chunk import DocumentChunk
from app.repositories.rag_repository import (
    DocumentChunkRepository,
    EmbeddingRepository,
)

logger = get_logger(__name__)


def hash_vector(vector: list[float]) -> str:
    """Deterministic content hash of an embedding vector.

    Values are quantized to 8 decimal places so float representation noise
    across providers never changes the hash.
    """
    payload = ",".join(f"{value:.8f}" for value in vector)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def embedding_checksum(
    chunk_hash: str,
    embedding_hash: str,
    model: str,
    dimension: int,
) -> str:
    """Composite integrity checksum binding an embedding to its chunk."""
    anchor = "|".join([chunk_hash, embedding_hash, model, str(dimension)])
    return hashlib.sha256(anchor.encode("utf-8")).hexdigest()


@dataclass
class EmbeddingRunResult:
    """Summary of a single embedding run over a group of chunks."""

    processed: int
    failed: int
    tokens_used: int
    latency_ms: float
    failures: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.processed + self.failed


class EmbeddingVersionService:
    """Versioning rules for per-chunk embedding rows.

    One active embedding per ``(chunk, provider, model)``; publishing a new
    version supersedes the previous one (kept for audit), and version numbers
    increment deterministically.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._embeddings = EmbeddingRepository(session)

    async def next_version(self, chunk_id: uuid.UUID, provider: str, model: str) -> int:
        active = await self._embeddings.get_active(chunk_id, provider, model)
        if active is not None:
            return active.version + 1
        versions = await self._embeddings.list_for_chunk(chunk_id, limit=200)
        matching = [
            embedding.version
            for embedding in versions
            if embedding.provider == provider and embedding.model == model
        ]
        return max(matching, default=0) + 1

    async def publish(
        self,
        *,
        chunk_id: uuid.UUID,
        provider: str,
        model: str,
        dimension: int,
        vector: list[float],
        token_count: int,
        embedding_hash: str,
        checksum: str,
        meta: dict[str, object] | None = None,
    ) -> ChunkEmbedding:
        """Supersede the previous active embedding and persist a new version."""
        await self._embeddings.supersede_for_chunk(chunk_id, provider, model)
        version = await self.next_version(chunk_id, provider, model)
        return await self._embeddings.create_for_chunk(
            chunk_id=chunk_id,
            provider=provider,
            model=model,
            dimension=dimension,
            vector=vector,
            token_count=token_count,
            embedding_hash=embedding_hash,
            checksum=checksum,
            meta=meta,
            version=version,
        )


class EmbeddingService:
    """Embeds chunk content through the configured provider and persists rows."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow
        session: AsyncSession = uow.session
        self._chunks = DocumentChunkRepository(session)
        self._versions = EmbeddingVersionService(session)

    async def embed_chunks(
        self,
        chunks: list[DocumentChunk],
        *,
        provider: EmbeddingProvider | None = None,
        batch_size: int | None = None,
    ) -> EmbeddingRunResult:
        """Embed a batch of chunks, persisting an active embedding per chunk."""
        if not chunks:
            return EmbeddingRunResult(processed=0, failed=0, tokens_used=0, latency_ms=0.0)

        provider = provider or create_embedding_provider()
        info = provider.info()
        self._validate_provider(info, provider)

        resolved_batch = batch_size or info.max_batch_size
        texts = [chunk.content or "" for chunk in chunks]

        processed = 0
        failed = 0
        tokens_used = 0
        latency_ms = 0.0
        failures: list[str] = []

        for start in range(0, len(texts), resolved_batch):
            group = chunks[start : start + resolved_batch]
            group_texts = texts[start : start + resolved_batch]
            try:
                # partial() binds the batch without a closure, so the callable
                # is unambiguously typed and cannot capture a stale loop value.
                response, _ = await run_with_retry(
                    self._embedding_retry_policy(provider),
                    partial(provider.embed, group_texts),
                    on_retry=self._on_embedding_retry,
                )
            except Exception as exc:  # noqa: BLE001 - boundary is intentional
                failed += len(group)
                failures.append(str(exc))
                for chunk in group:
                    await self._chunks.mark_failed(chunk)
                logger.warning(
                    "embedding_batch_failed",
                    provider=provider.name,
                    model=info.model,
                    batch_items=len(group),
                    error=str(exc),
                )
                continue

            latency_ms += response.latency_ms
            tokens_used += response.tokens_used
            for chunk, vector in zip(group, response.vectors, strict=False):
                try:
                    await self._persist(chunk, provider, info, response, vector)
                except Exception as exc:  # noqa: BLE001 - per-chunk persistence
                    failed += 1
                    failures.append(str(exc))
                    await self._chunks.mark_failed(chunk)
                    continue
            processed += min(len(group), len(response.vectors))

        return EmbeddingRunResult(
            processed=processed,
            failed=failed,
            tokens_used=tokens_used,
            latency_ms=latency_ms,
            failures=failures,
        )

    async def embed_chunks_parallel(
        self,
        groups: list[list[DocumentChunk]],
        *,
        provider: EmbeddingProvider | None = None,
        parallelism: int | None = None,
    ) -> EmbeddingRunResult:
        """Embed chunk groups with bounded-concurrent provider calls.

        Provider calls run concurrently (bounded by ``parallelism``), while all
        persistence stays sequential on the calling session so a shared
        ``AsyncSession`` is never used concurrently. A failed provider call in
        one group never blocks the others (partial failure recovery).
        """
        non_empty = [group for group in groups if group]
        if not non_empty:
            return EmbeddingRunResult(processed=0, failed=0, tokens_used=0, latency_ms=0.0)

        provider = provider or create_embedding_provider()
        info = provider.info()
        self._validate_provider(info, provider)

        resolved_parallelism = max(1, parallelism or settings.EMBEDDING_WORKER_CONCURRENCY)
        semaphore = asyncio.Semaphore(resolved_parallelism)

        async def _bounded(group: list[DocumentChunk]) -> EmbeddingResponse:
            async with semaphore:
                response, _ = await run_with_retry(
                    self._embedding_retry_policy(provider),
                    lambda: provider.embed([chunk.content or "" for chunk in group]),
                    on_retry=self._on_embedding_retry,
                )
                return response

        responses = await asyncio.gather(
            *(_bounded(group) for group in non_empty),
            return_exceptions=True,
        )

        processed = 0
        failed = 0
        tokens_used = 0
        latency_ms = 0.0
        failures: list[str] = []

        for group, response in zip(non_empty, responses, strict=False):
            if isinstance(response, BaseException):
                failed += len(group)
                failures.append(str(response))
                for chunk in group:
                    await self._chunks.mark_failed(chunk)
                logger.warning(
                    "embedding_batch_failed",
                    provider=provider.name,
                    model=info.model,
                    batch_items=len(group),
                    error=str(response),
                )
                continue
            latency_ms += response.latency_ms
            tokens_used += response.tokens_used
            for chunk, vector in zip(group, response.vectors, strict=False):
                try:
                    await self._persist(chunk, provider, info, response, vector)
                except Exception as exc:  # noqa: BLE001 - per-chunk persistence
                    failed += 1
                    failures.append(str(exc))
                    await self._chunks.mark_failed(chunk)
                    continue
            processed += min(len(group), len(response.vectors))

        return EmbeddingRunResult(
            processed=processed,
            failed=failed,
            tokens_used=tokens_used,
            latency_ms=latency_ms,
            failures=failures,
        )

    def _embedding_retry_policy(self, provider: EmbeddingProvider) -> RetryPolicy:
        cfg = provider.config
        return RetryPolicy(
            max_attempts=max(1, settings.EMBEDDING_MAX_RETRIES + 1),
            min_delay=cfg.retry_min_delay,
            max_delay=cfg.retry_max_delay,
            jitter=cfg.retry_jitter,
        )

    def _on_embedding_retry(self, attempt: int, exc: AIError, delay: float) -> None:
        logger.warning(
            "embedding_retry_attempt",
            attempt=attempt,
            delay=delay,
            provider=exc.provider,
            model=exc.model,
            error_type=type(exc).__name__,
        )

    def _validate_provider(
        self,
        info: EmbeddingProviderInfo,
        provider: EmbeddingProvider,
    ) -> None:
        if not info.dimension:
            raise AIInvalidConfigurationError(
                message="Embedding provider reports no vector dimension",
                details={"provider": provider.name, "model": info.model},
            )
        if info.dimension > settings.EMBEDDING_MAX_DIMENSION:
            raise AIInvalidConfigurationError(
                message="Embedding dimension exceeds EMBEDDING_MAX_DIMENSION",
                details={
                    "provider": provider.name,
                    "dimension": info.dimension,
                    "max_dimension": settings.EMBEDDING_MAX_DIMENSION,
                },
            )

    async def _persist(
        self,
        chunk: DocumentChunk,
        provider: EmbeddingProvider,
        info: EmbeddingProviderInfo,
        response: EmbeddingResponse,
        vector: list[float],
    ) -> ChunkEmbedding:
        if len(vector) != info.dimension:
            raise AIInvalidResponseError(
                message="Provider returned a vector with an unexpected dimension",
                details={
                    "expected": info.dimension,
                    "actual": len(vector),
                    "provider": provider.name,
                },
            )

        embedding_hash = hash_vector(vector)
        checksum = embedding_checksum(
            chunk.chunk_hash or "",
            embedding_hash,
            response.model,
            info.dimension,
        )
        meta: dict[str, object] = {
            "chunk_hash": chunk.chunk_hash,
            "chunk_version": chunk.version,
            "request_id": response.request_id,
        }
        embedding = await self._versions.publish(
            chunk_id=chunk.id,
            provider=provider.name,
            model=response.model,
            dimension=info.dimension,
            vector=vector,
            token_count=chunk.token_count,
            embedding_hash=embedding_hash,
            checksum=checksum,
            meta=meta,
        )
        await self._chunks.mark_processed(chunk)
        return embedding
