from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings.base import EmbeddingProvider
from app.ai.embeddings.config import EmbeddingProviderConfig
from app.ai.embeddings.factory import (
    create_embedding_provider,
    get_embedding_provider,
    reset_embedding_provider,
    supported_embedding_providers,
)
from app.ai.embeddings.models import EmbeddingProviderInfo, EmbeddingResponse
from app.ai.embeddings.providers.gemini import GeminiEmbeddingProvider
from app.ai.embeddings.providers.local import LocalEmbeddingProvider
from app.ai.embeddings.providers.openai import OpenAIEmbeddingProvider
from app.ai.errors import (
    AIAuthenticationFailedError,
    AIInvalidConfigurationError,
    AIInvalidResponseError,
    AIProviderUnavailableError,
)
from app.core.config import settings
from app.database.unit_of_work import UnitOfWork
from app.models.chunk_embedding import ChunkEmbedding
from app.models.document_chunk import DocumentChunk
from app.repositories.rag_repository import (
    EmbeddingBatchRepository,
    EmbeddingJobRepository,
    EmbeddingRepository,
    EmbeddingStatisticsRepository,
    VectorIndexRepository,
)
from app.services.chunking_service import (
    units_from_content_unit,
    units_from_generated_lesson_version,
)
from app.services.embedding_batch_service import EmbeddingBatchService
from app.services.embedding_integrity_service import EmbeddingIntegrityService
from app.services.embedding_service import (
    EmbeddingRunResult,
    EmbeddingService,
    EmbeddingVersionService,
    embedding_checksum,
    hash_vector,
)
from shared.constants import ChunkStatus, EmbeddingJobType

PROVIDER = "local"
MODEL = "local-embedding-test"
DIMENSION = 8


def _local_config(**overrides) -> EmbeddingProviderConfig:
    return EmbeddingProviderConfig(
        provider=PROVIDER,
        model=MODEL,
        dimension=overrides.pop("dimension", DIMENSION),
        **overrides,
    )


def _provider() -> EmbeddingProvider:
    return create_embedding_provider(config=_local_config())


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


async def _make_job(
    db_session,
    user_id: uuid.UUID,
    presentation_id: uuid.UUID,
    total_items: int = 1,
    **overrides,
):
    repo = EmbeddingJobRepository(db_session)
    return await repo.create_job(
        job_type=overrides.pop("job_type", EmbeddingJobType.INDEX.value),
        user_id=user_id,
        presentation_id=presentation_id,
        lesson_id=None,
        index_id=None,
        total_items=total_items,
        payload=None,
        idempotency_key=overrides.pop("idempotency_key", f"job-{uuid.uuid4().hex}"),
        priority=overrides.pop("priority", 5),
        max_attempts=overrides.pop("max_attempts", 3),
    )


class _FailingProvider(LocalEmbeddingProvider):
    async def embed(
        self,
        texts: list[str],
        *,
        request_id: str | None = None,
        correlation_id: str | None = None,
    ) -> EmbeddingResponse:
        raise RuntimeError("provider down")


class _WrongDimensionProvider(LocalEmbeddingProvider):
    def __init__(self, config: EmbeddingProviderConfig) -> None:
        super().__init__(config)
        self._dimension = 2

    async def embed(
        self,
        texts: list[str],
        *,
        request_id: str | None = None,
        correlation_id: str | None = None,
    ) -> EmbeddingResponse:
        return EmbeddingResponse(
            vectors=[[0.5] * 4 for _ in texts],
            dimension=4,
            tokens_used=1,
            provider=self.name,
            model=self.model,
        )


class _NoDimensionProvider(LocalEmbeddingProvider):
    def info(self) -> EmbeddingProviderInfo:
        return EmbeddingProviderInfo(
            provider=self.name,
            model=self.model,
            dimension=0,
            max_batch_size=32,
            requires_api_key=False,
        )


class TestHashHelpers:
    def test_hash_vector_deterministic(self) -> None:
        assert hash_vector([0.1, 0.2, 0.3]) == hash_vector([0.1, 0.2, 0.3])

    def test_hash_vector_differs_for_different_vectors(self) -> None:
        assert hash_vector([0.1, 0.2, 0.3]) != hash_vector([0.3, 0.2, 0.1])

    def test_hash_vector_quantizes_precision_noise(self) -> None:
        assert hash_vector([0.100000001, 0.2]) == hash_vector([0.1, 0.2])

    def test_checksum_deterministic(self) -> None:
        first = embedding_checksum("a", "b", MODEL, DIMENSION)
        second = embedding_checksum("a", "b", MODEL, DIMENSION)
        assert first == second
        assert len(first) == 64

    def test_checksum_changes_with_model(self) -> None:
        assert embedding_checksum("a", "b", "m1", DIMENSION) != embedding_checksum(
            "a", "b", "m2", DIMENSION
        )

    def test_checksum_changes_with_dimension(self) -> None:
        assert embedding_checksum("a", "b", MODEL, 8) != embedding_checksum(
            "a", "b", MODEL, 16
        )


class TestLocalEmbeddingProvider:
    async def test_deterministic_vectors(self) -> None:
        provider = _provider()
        first = await provider.embed(["alpha"])
        second = await provider.embed(["alpha"])
        assert first.vectors == second.vectors

    async def test_different_texts_differ(self) -> None:
        provider = _provider()
        response = await provider.embed(["alpha", "beta"])
        assert response.vectors[0] != response.vectors[1]

    async def test_vector_dimension_from_config(self) -> None:
        provider = _provider()
        response = await provider.embed(["alpha"])
        assert len(response.vectors[0]) == DIMENSION
        assert response.dimension == DIMENSION

    async def test_default_dimension_when_unset(self) -> None:
        provider = create_embedding_provider(
            config=EmbeddingProviderConfig(provider=PROVIDER, model=MODEL)
        )
        response = await provider.embed(["alpha"])
        assert len(response.vectors[0]) == LocalEmbeddingProvider.default_dimension

    async def test_empty_text_yields_zero_vector(self) -> None:
        provider = _provider()
        response = await provider.embed([""])
        assert response.vectors[0] == [0.0] * DIMENSION

    async def test_batch_returns_one_vector_per_text(self) -> None:
        provider = _provider()
        texts = [f"text-{index}" for index in range(7)]
        response = await provider.embed(texts)
        assert len(response.vectors) == 7

    async def test_tokens_used_positive(self) -> None:
        provider = _provider()
        response = await provider.embed(["some real content here"])
        assert response.tokens_used >= 1

    async def test_health_check(self) -> None:
        status = await _provider().health_check()
        assert status.healthy is True
        assert status.provider == PROVIDER

    async def test_info_metadata(self) -> None:
        info = _provider().info()
        assert info.provider == PROVIDER
        assert info.model == MODEL
        assert info.dimension == DIMENSION
        assert info.requires_api_key is False


class TestEmbeddingFactory:
    def test_supported_providers(self) -> None:
        assert supported_embedding_providers() == ["gemini", "local", "openai"]

    def test_create_local_from_config(self) -> None:
        assert isinstance(_provider(), LocalEmbeddingProvider)

    def test_create_gemini_requires_key(self) -> None:
        with pytest.raises(AIInvalidConfigurationError):
            create_embedding_provider(
                config=EmbeddingProviderConfig(provider="gemini")
            )

    def test_create_openai_requires_key(self) -> None:
        with pytest.raises(AIInvalidConfigurationError):
            create_embedding_provider(
                config=EmbeddingProviderConfig(provider="openai")
            )

    def test_unknown_provider_raises(self) -> None:
        with pytest.raises(AIInvalidConfigurationError):
            create_embedding_provider(
                config=EmbeddingProviderConfig(provider="not-a-provider")
            )

    def test_empty_provider_raises(self) -> None:
        with pytest.raises(AIInvalidConfigurationError):
            create_embedding_provider(config=EmbeddingProviderConfig(provider=""))

    async def test_singleton_and_reset(self) -> None:
        reset_embedding_provider()
        with patch.object(settings, "EMBEDDING_PROVIDER", "local"):
            first = get_embedding_provider()
            second = get_embedding_provider()
            assert first is second
            reset_embedding_provider()
            third = get_embedding_provider()
            assert third is not first
        reset_embedding_provider()


class TestEmbeddingProviderRetry:
    """Retry wiring for the real HTTP embedding providers.

    Uses the actual ``OpenAIEmbeddingProvider`` / ``GeminiEmbeddingProvider``
    classes with a transport that fails transiently, so the tests exercise the
    ``RetryPolicy`` path in ``HttpEmbeddingProvider.embed`` (backed by
    ``EMBEDDING_MAX_RETRIES``) rather than a standalone mock.
    """

    def _openai_config(self, **overrides) -> EmbeddingProviderConfig:
        return EmbeddingProviderConfig(
            provider="openai",
            model="text-embedding-3-small",
            api_key="test-key",
            dimension=DIMENSION,
            retry_count=settings.EMBEDDING_MAX_RETRIES,
            retry_min_delay=0,
            retry_max_delay=0.01,
            retry_jitter=0,
            **overrides,
        )

    def _gemini_config(self, **overrides) -> EmbeddingProviderConfig:
        return EmbeddingProviderConfig(
            provider="gemini",
            model="text-embedding-004",
            api_key="test-key",
            dimension=DIMENSION,
            retry_count=settings.EMBEDDING_MAX_RETRIES,
            retry_min_delay=0,
            retry_max_delay=0.01,
            retry_jitter=0,
            **overrides,
        )

    def _openai_provider(self, handler) -> OpenAIEmbeddingProvider:
        provider = OpenAIEmbeddingProvider(self._openai_config())
        provider._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        return provider

    def _gemini_provider(self, handler) -> GeminiEmbeddingProvider:
        provider = GeminiEmbeddingProvider(self._gemini_config())
        provider._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        return provider

    @staticmethod
    def _openai_success() -> dict:
        return {
            "data": [{"index": 0, "embedding": [0.5] * DIMENSION}],
            "usage": {"total_tokens": 3},
            "model": "text-embedding-3-small",
        }

    @staticmethod
    def _gemini_success() -> dict:
        return {
            "embeddings": [{"values": [0.5] * DIMENSION}],
            "modelVersion": "text-embedding-004",
        }

    async def test_from_settings_feeds_embedding_max_retries(self) -> None:
        with patch.object(settings, "EMBEDDING_PROVIDER", "local"):
            config = EmbeddingProviderConfig.from_settings()
        assert config.retry_count == settings.EMBEDDING_MAX_RETRIES

    async def test_openai_embedding_retries_transient_failure(self) -> None:
        attempts = {"count": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            attempts["count"] += 1
            if attempts["count"] == 1:
                return httpx.Response(
                    503, json={"error": {"message": "temporarily down"}}
                )
            return httpx.Response(200, json=self._openai_success())

        provider = self._openai_provider(handler)
        with patch("app.ai.retry.asyncio_sleep", new=AsyncMock()):
            response = await provider.embed(["hello"])
        await provider.close()

        assert attempts["count"] == 2
        assert response.model == "text-embedding-3-small"
        assert len(response.vectors) == 1
        assert len(response.vectors[0]) == DIMENSION

    async def test_openai_embedding_exhausts_retry_budget(self) -> None:
        attempts = {"count": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            attempts["count"] += 1
            return httpx.Response(503, json={"error": {"message": "still down"}})

        provider = self._openai_provider(handler)
        with (
            patch("app.ai.retry.asyncio_sleep", new=AsyncMock()),
            pytest.raises(AIProviderUnavailableError),
        ):
            await provider.embed(["hello"])
        await provider.close()

        assert attempts["count"] == settings.EMBEDDING_MAX_RETRIES + 1

    async def test_openai_embedding_does_not_retry_hard_failures(self) -> None:
        attempts = {"count": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            attempts["count"] += 1
            return httpx.Response(401, json={"error": {"message": "bad key"}})

        provider = self._openai_provider(handler)
        with (
            patch("app.ai.retry.asyncio_sleep", new=AsyncMock()),
            pytest.raises(AIAuthenticationFailedError),
        ):
            await provider.embed(["hello"])
        await provider.close()

        assert attempts["count"] == 1

    async def test_gemini_embedding_retries_transient_failure(self) -> None:
        attempts = {"count": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            attempts["count"] += 1
            if attempts["count"] == 1:
                return httpx.Response(
                    503,
                    json={"error": {"status": "UNAVAILABLE", "message": "upstream down"}},
                )
            return httpx.Response(200, json=self._gemini_success())

        provider = self._gemini_provider(handler)
        with patch("app.ai.retry.asyncio_sleep", new=AsyncMock()):
            response = await provider.embed(["hello"])
        await provider.close()

        assert attempts["count"] == 2
        assert response.model == "text-embedding-004"
        assert len(response.vectors) == 1
        assert len(response.vectors[0]) == DIMENSION


class TestEmbeddingVersionService:
    async def test_publish_increments_version(
        self, make_user, make_presentation, db_session
    ) -> None:
        user = await make_user()
        presentation = await make_presentation(user.id)
        chunk = await _make_chunk(db_session, presentation.id, position=0)
        service = EmbeddingVersionService(db_session)

        first = await service.publish(
            chunk_id=chunk.id,
            provider=PROVIDER,
            model=MODEL,
            dimension=DIMENSION,
            vector=[0.1] * DIMENSION,
            token_count=5,
            embedding_hash="h1",
            checksum="c1",
        )
        second = await service.publish(
            chunk_id=chunk.id,
            provider=PROVIDER,
            model=MODEL,
            dimension=DIMENSION,
            vector=[0.2] * DIMENSION,
            token_count=5,
            embedding_hash="h2",
            checksum="c2",
        )
        assert first.version == 1
        assert second.version == 2

    async def test_publish_supersedes_previous(
        self, make_user, make_presentation, db_session
    ) -> None:
        user = await make_user()
        presentation = await make_presentation(user.id)
        chunk = await _make_chunk(db_session, presentation.id, position=0)
        service = EmbeddingVersionService(db_session)
        repo = EmbeddingRepository(db_session)

        await service.publish(
            chunk_id=chunk.id,
            provider=PROVIDER,
            model=MODEL,
            dimension=DIMENSION,
            vector=[0.1] * DIMENSION,
            token_count=5,
            embedding_hash="h1",
            checksum="c1",
        )
        await service.publish(
            chunk_id=chunk.id,
            provider=PROVIDER,
            model=MODEL,
            dimension=DIMENSION,
            vector=[0.2] * DIMENSION,
            token_count=5,
            embedding_hash="h2",
            checksum="c2",
        )

        active = await repo.get_active(chunk.id, PROVIDER, MODEL)
        assert active is not None
        assert active.version == 2
        assert active.embedding_hash == "h2"

        versions = await repo.list_for_chunk(chunk.id)
        superseded = [v for v in versions if v.status == "superseded"]
        assert len(superseded) == 1
        assert superseded[0].version == 1

    async def test_next_version_when_no_active(
        self, make_user, make_presentation, db_session
    ) -> None:
        user = await make_user()
        presentation = await make_presentation(user.id)
        chunk = await _make_chunk(db_session, presentation.id, position=0)
        service = EmbeddingVersionService(db_session)

        assert await service.next_version(chunk.id, PROVIDER, MODEL) == 1


class TestEmbeddingService:
    async def test_embed_chunks_persists_active_embedding(
        self, make_user, make_presentation, db_session
    ) -> None:
        user = await make_user()
        presentation = await make_presentation(user.id)
        chunk = await _make_chunk(db_session, presentation.id, position=0, chunk_hash="h")
        service = EmbeddingService(UnitOfWork(session=db_session))
        repo = EmbeddingRepository(db_session)

        result = await service.embed_chunks([chunk], provider=_provider())
        assert isinstance(result, EmbeddingRunResult)
        assert result.processed == 1
        assert result.failed == 0

        embedding = await repo.get_active(chunk.id, PROVIDER, MODEL)
        assert embedding is not None
        assert len(embedding.vector or []) == DIMENSION
        assert embedding.embedding_hash
        assert embedding.checksum
        assert (embedding.meta or {}).get("chunk_hash") == "h"

    async def test_embed_chunks_marks_chunks_processed(
        self, make_user, make_presentation, db_session
    ) -> None:
        user = await make_user()
        presentation = await make_presentation(user.id)
        chunk = await _make_chunk(db_session, presentation.id, position=0)
        service = EmbeddingService(UnitOfWork(session=db_session))

        await service.embed_chunks([chunk], provider=_provider())
        assert chunk.status == ChunkStatus.PROCESSED.value

    async def test_embed_chunks_returns_summary(
        self, make_user, make_presentation, db_session
    ) -> None:
        user = await make_user()
        presentation = await make_presentation(user.id)
        chunks = [
            await _make_chunk(db_session, presentation.id, position=index)
            for index in range(3)
        ]
        service = EmbeddingService(UnitOfWork(session=db_session))

        result = await service.embed_chunks(chunks, provider=_provider())
        assert result.processed == 3
        assert result.tokens_used >= 1
        assert result.latency_ms >= 0

    async def test_failing_provider_marks_chunk_failed(
        self, make_user, make_presentation, db_session
    ) -> None:
        user = await make_user()
        presentation = await make_presentation(user.id)
        chunk = await _make_chunk(db_session, presentation.id, position=0)
        service = EmbeddingService(UnitOfWork(session=db_session))

        result = await service.embed_chunks(
            [chunk], provider=_FailingProvider(_local_config())
        )
        assert result.processed == 0
        assert result.failed == 1
        assert result.failures
        assert chunk.status == ChunkStatus.FAILED.value

    async def test_dimension_mismatch_marks_chunk_failed(
        self, make_user, make_presentation, db_session
    ) -> None:
        user = await make_user()
        presentation = await make_presentation(user.id)
        chunk = await _make_chunk(db_session, presentation.id, position=0)
        service = EmbeddingService(UnitOfWork(session=db_session))

        result = await service.embed_chunks(
            [chunk], provider=_WrongDimensionProvider(_local_config())
        )
        assert result.failed == 1
        assert chunk.status == ChunkStatus.FAILED.value

    async def test_no_dimension_raises_config_error(
        self, make_user, make_presentation, db_session
    ) -> None:
        user = await make_user()
        presentation = await make_presentation(user.id)
        chunk = await _make_chunk(db_session, presentation.id, position=0)
        service = EmbeddingService(UnitOfWork(session=db_session))

        with pytest.raises(AIInvalidConfigurationError):
            await service.embed_chunks(
                [chunk], provider=_NoDimensionProvider(_local_config())
            )


class TestChunkAdapters:
    class _Block:
        def __init__(self, block_type, content, position=0, heading=None, slide_position=0):
            self.block_type = block_type
            self.content = content
            self.position = position
            self.heading = heading
            self.slide_position = slide_position

    class _Unit:
        def __init__(self, blocks, position=0, source_page=3):
            self.blocks = blocks
            self.position = position
            self.source_page = source_page

    def test_units_from_content_unit(self) -> None:
        unit = self._Unit(
            [
                self._Block("heading", "Intro", position=0),
                self._Block("paragraph", "Body.", position=1),
            ],
            position=2,
            source_page=4,
        )
        units = units_from_content_unit(unit)
        assert len(units) == 2
        assert units[0].block_type == "heading"
        assert units[0].heading == "Intro"
        assert units[1].content == "Body."
        assert units[1].source_page == 4
        assert units[1].source_slide == 3

    def test_units_from_content_unit_respects_position_offset(self) -> None:
        unit = self._Unit([self._Block("paragraph", "Body.", position=0)])
        units = units_from_content_unit(unit, position_offset=10)
        assert units[0].position == 10

    def test_units_from_generated_lesson_version(self) -> None:
        version = type("Version", (), {
            "blocks": [
                self._Block("heading", "Concepts", heading="Concepts", slide_position=0),
                self._Block("paragraph", "Explanation.", slide_position=0),
            ],
        })()
        units = units_from_generated_lesson_version(version)
        assert units[0].heading == "Concepts"
        assert units[1].content == "Explanation."
        assert units[1].source_slide == 1


class TestEmbeddingBatchService:
    async def test_create_batches_groups_by_size(
        self, make_user, make_presentation, db_session
    ) -> None:
        user = await make_user()
        presentation = await make_presentation(user.id)
        chunks = [
            await _make_chunk(db_session, presentation.id, position=index)
            for index in range(5)
        ]
        job = await _make_job(db_session, user.id, presentation.id, total_items=5)
        service = EmbeddingBatchService(UnitOfWork(session=db_session))

        batches = await service.create_batches(job, [c.id for c in chunks], batch_size=2)
        assert len(batches) == 3
        assert [b.total_items for b in batches] == [2, 2, 1]
        assert [b.sequence for b in batches] == [0, 1, 2]

    async def test_process_batch_completes_batch_and_syncs_job(
        self, make_user, make_presentation, db_session
    ) -> None:
        user = await make_user()
        presentation = await make_presentation(user.id)
        chunks = [
            await _make_chunk(db_session, presentation.id, position=index)
            for index in range(2)
        ]
        job = await _make_job(db_session, user.id, presentation.id, total_items=2)
        service = EmbeddingBatchService(UnitOfWork(session=db_session))
        batches = await service.create_batches(job, [c.id for c in chunks], batch_size=2)

        result = await service.process_batch(job, batches[0], provider=_provider())
        assert result.processed == 2
        assert result.failed == 0

        refreshed = await EmbeddingBatchRepository(db_session).list_for_job(job.id)
        assert refreshed[0].status == "completed"
        assert job.processed_items == 2

    async def test_resume_job_processes_all_and_completes(
        self, make_user, make_presentation, db_session
    ) -> None:
        user = await make_user()
        presentation = await make_presentation(user.id)
        chunks = [
            await _make_chunk(db_session, presentation.id, position=index)
            for index in range(4)
        ]
        job = await _make_job(db_session, user.id, presentation.id, total_items=4)
        service = EmbeddingBatchService(UnitOfWork(session=db_session))
        await service.create_batches(job, [c.id for c in chunks], batch_size=2)

        count = await service.resume_job(job, provider=_provider())
        assert count == 2
        assert job.status == "completed"
        assert job.processed_items == 4
        assert job.failed_items == 0

    async def test_finalize_job_partial_when_batch_fails(
        self, make_user, make_presentation, db_session
    ) -> None:
        user = await make_user()
        presentation = await make_presentation(user.id)
        chunk = await _make_chunk(db_session, presentation.id, position=0)
        job = await _make_job(db_session, user.id, presentation.id, total_items=1)
        service = EmbeddingBatchService(UnitOfWork(session=db_session))
        batch = (await service.create_batches(job, [chunk.id], batch_size=1))[0]

        await service.process_batch(
            job, batch, provider=_FailingProvider(_local_config())
        )
        finalized = await service.finalize_job(job)
        assert finalized.status == "failed"


class TestEmbeddingIntegrityService:
    async def test_verify_embedding_valid(
        self, make_user, make_presentation, db_session
    ) -> None:
        user = await make_user()
        presentation = await make_presentation(user.id)
        chunk = await _make_chunk(db_session, presentation.id, position=0, chunk_hash="h")
        service = EmbeddingService(UnitOfWork(session=db_session))
        await service.embed_chunks([chunk], provider=_provider())

        repo = EmbeddingRepository(db_session)
        embedding = await repo.get_active(chunk.id, PROVIDER, MODEL)
        assert embedding is not None
        assert EmbeddingIntegrityService(
            UnitOfWork(session=db_session)
        ).verify_embedding(embedding)

    async def test_verify_embedding_tampered(self, db_session) -> None:
        embedding = ChunkEmbedding(
            chunk_id=uuid.uuid4(),
            provider=PROVIDER,
            model=MODEL,
            dimension=DIMENSION,
            vector=[0.1] * DIMENSION,
            embedding_hash="tampered-hash",
            checksum=embedding_checksum("h", "tampered-hash", MODEL, DIMENSION),
            meta={"chunk_hash": "h"},
        )
        service = EmbeddingIntegrityService(UnitOfWork(session=db_session))
        embedding.checksum = embedding_checksum("different", "tampered-hash", MODEL, DIMENSION)
        assert service.verify_embedding(embedding) is False

    async def test_collect_counts(
        self, make_user, make_presentation, db_session
    ) -> None:
        user = await make_user()
        presentation = await make_presentation(user.id)
        await _make_chunk(db_session, presentation.id, position=0)
        await _make_chunk(
            db_session, presentation.id, position=1, status=ChunkStatus.FAILED.value
        )
        service = EmbeddingIntegrityService(UnitOfWork(session=db_session))

        report = await service.collect(presentation.id, PROVIDER, MODEL)
        assert report.total_chunks == 2
        assert report.embedded_chunks == 0
        assert report.failed_chunks == 1
        assert report.pending_chunks == 1

    async def test_collect_after_embedding(self, make_user, make_presentation, db_session) -> None:
        user = await make_user()
        presentation = await make_presentation(user.id)
        chunk = await _make_chunk(db_session, presentation.id, position=0)
        await EmbeddingService(UnitOfWork(session=db_session)).embed_chunks(
            [chunk], provider=_provider()
        )
        service = EmbeddingIntegrityService(UnitOfWork(session=db_session))

        report = await service.collect(presentation.id, PROVIDER, MODEL)
        assert report.embedded_chunks == 1
        assert report.coverage == 1.0
        assert report.stale_chunks == 0

    async def test_record_statistics_upserts(
        self, make_user, make_presentation, db_session
    ) -> None:
        user = await make_user()
        presentation = await make_presentation(user.id)
        chunk = await _make_chunk(db_session, presentation.id, position=0)
        await EmbeddingService(UnitOfWork(session=db_session)).embed_chunks(
            [chunk], provider=_provider()
        )
        index = await VectorIndexRepository(db_session).create_for_scope(
            presentation_id=presentation.id,
            lesson_id=None,
            index_type="presentation",
            strategy="heading",
            chunk_size=1500,
            chunk_overlap=150,
            max_chunk_tokens=1000,
            provider=PROVIDER,
            model=MODEL,
            dimension=DIMENSION,
            source_hash=None,
        )
        service = EmbeddingIntegrityService(UnitOfWork(session=db_session))

        row = await service.record_statistics(index)
        assert row.embedded_chunks == 1
        assert row.total_chunks == 1
        assert row.avg_dimension == DIMENSION

        stats_repo = EmbeddingStatisticsRepository(db_session)
        daily = await stats_repo.get_daily(index.id, datetime.now(UTC).date())
        assert daily is not None
        assert daily.embedded_chunks == 1

