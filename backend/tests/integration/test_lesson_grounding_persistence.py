"""Persistence semantics of claim-level semantic grounding.

Verifies that the grounding decision is durably recorded and enforces the
version lifecycle:
  * grounded output      → version SUCCEEDED + lesson READY + blocks persisted,
                           generation_metadata.grounding present (verdict PASS)
  * fabricated output    → version FAILED (error_code safety_rejected),
                           lesson FAILED, no blocks, no READY
  * mixed topic          → the entire lesson is rejected (fail-safe)
  * heuristic fallback   → bypasses validate_output (verbatim source), succeeds
"""
from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.database.unit_of_work import UnitOfWork
from app.models.generated_block import GeneratedBlock
from app.models.generated_lesson import GeneratedLesson
from app.models.generated_lesson_version import GeneratedLessonVersion
from app.services.content_extraction_service import ContentExtractionService
from app.services.lesson_generation_service import LessonGenerationService
from app.services.lesson_safety import LessonSafetyError

pytestmark = pytest.mark.integration

SOURCE_CONTENT = (
    b"Computer Networks Fundamentals\n\n"
    b"TCP uses a three-way handshake to establish a connection. "
    b"HTTP is a stateless protocol. "
    b"DNS resolves domain names into IP addresses.\n\n"
    b"A router forwards packets between networks. "
    b"Switches operate within a single network segment."
)

GROUNDED_AI_PAYLOAD = (
    '{"title": "Networks", "summary": "Overview.", '
    '"language": "en", "difficulty": "beginner", "topics": ['
    '{"topic": "TCP", "description": "TCP uses a three-way handshake to establish a connection."}, '
    '{"topic": "HTTP", "description": "HTTP is a stateless protocol."}, '
    '{"topic": "DNS", "description": "DNS resolves domain names into IP addresses."}'
    ']}'
)

FABRICATED_AI_PAYLOAD = (
    '{"title": "Networks", "summary": "Overview.", '
    '"language": "en", "difficulty": "beginner", "topics": ['
    '{"topic": "TCP", "description": "TCP uses a three-way handshake to establish a connection."}, '
    '{"topic": "HTTP", "description": "HTTP guarantees zero packet loss for all connections."}'
    ']}'
)

MIXED_AI_PAYLOAD = (
    '{"title": "Networks", "summary": "Overview.", '
    '"language": "en", "difficulty": "beginner", "topics": ['
    '{"topic": "TCP", "description": "TCP uses a three-way handshake to establish a connection."}, '
    '{"topic": "DNS", "description": "DNS permanently caches every IP address forever."}'
    ']}'
)


@pytest.fixture
def mock_storage() -> MagicMock:
    storage = MagicMock()
    storage.upload_fileobj = AsyncMock(return_value="sources/mock-key")
    storage.download_fileobj = AsyncMock(return_value=SOURCE_CONTENT)
    return storage


@pytest.fixture(autouse=True)
def override_external_deps(mock_storage: MagicMock):
    with patch(
        "app.services.presentation_service.get_storage_backend",
        AsyncMock(return_value=mock_storage),
    ), patch(
        "app.services.content_extraction_service.get_storage_backend",
        AsyncMock(return_value=mock_storage),
    ):
        yield


async def _create_presentation(client: AsyncClient, title: str) -> str:
    response = await client.post("/api/v1/presentations", json={"title": title})
    assert response.status_code == 201
    return response.json()["data"]["id"]


async def _upload_and_extract(client: AsyncClient, presentation_id: str) -> None:
    upload_resp = await client.post(
        f"/api/v1/presentations/{presentation_id}/source",
        files={"source": ("lecture.txt", SOURCE_CONTENT, "text/plain")},
    )
    assert upload_resp.status_code == 200
    async with UnitOfWork() as uow:
        await ContentExtractionService(uow).extract_presentation(presentation_id)


class _FakeAI:
    def __init__(self, payload_text: str):
        self._text = payload_text

    async def generate(self, request):
        return MagicMock(
            text=self._text,
            provider="fake",
            model="fake-model",
            request_id="ai_req_1",
            correlation_id="corr_1",
            finish_reason=MagicMock(value="stop"),
            retry_count=0,
            usage=MagicMock(
                input_tokens=100,
                output_tokens=200,
                total_tokens=300,
                estimated_cost=None,
                currency=None,
            ),
            latency_ms=42.0,
        )


class _VerifierAwareFakeAI:
    """Returns the generation payload for the main generation call, and
    scripted LLM-verifier verdicts for grounding requests (detected via the
    ``lesson_grounding_verifier`` resource_type that LLMGroundingVerifier sets).

    Enables testing that the LLM verifier really runs through the exported
    lesson path (LessonGenerationService -> validate_output -> run_claim_grounding)
    rather than only through direct verifier calls.
    """

    def __init__(self, payload_text: str):
        self._text = payload_text
        self.verifier_calls = 0
        self.verifier_claims: list[str] = []

    async def generate(self, request):
        md = getattr(request, "metadata", None) or {}
        if md.get("resource_type") == "lesson_grounding_verifier":
            self.verifier_calls += 1
            prompt = getattr(request, "user_prompt", "")
            if "[CLAIM_START]" in prompt and "[CLAIM_END]" in prompt:
                claim = prompt.split("[CLAIM_START]")[1].split("[CLAIM_END]")[0]
                self.verifier_claims.append(claim)
                verdict = "unsupported" if "guarantees zero packet loss" in claim else "supported"
            else:
                verdict = "unsupported"
            return MagicMock(
                text=json.dumps({
                    "verdict": verdict,
                    "confidence": 0.9,
                    "evidence_spans": [],
                    "reason": "scripted verifier",
                }),
                provider="fake",
                model="fake-model",
                request_id="ai_req_1",
                correlation_id="corr_1",
                finish_reason=MagicMock(value="stop"),
                retry_count=0,
                usage=MagicMock(
                    input_tokens=100,
                    output_tokens=200,
                    total_tokens=300,
                    estimated_cost=None,
                    currency=None,
                ),
                latency_ms=42.0,
            )
        return MagicMock(
            text=self._text,
            provider="fake",
            model="fake-model",
            request_id="ai_req_1",
            correlation_id="corr_1",
            finish_reason=MagicMock(value="stop"),
            retry_count=0,
            usage=MagicMock(
                input_tokens=100,
                output_tokens=200,
                total_tokens=300,
                estimated_cost=None,
                currency=None,
            ),
            latency_ms=42.0,
        )


class TestGroundingPersistence:
    async def test_grounded_lesson_succeeds_with_report(
        self, client: AsyncClient
    ) -> None:
        pid = await _create_presentation(client, "Grounded")
        await _upload_and_extract(client, pid)

        fake_ai = _FakeAI(GROUNDED_AI_PAYLOAD)
        async with UnitOfWork() as uow:
            from app.repositories.presentation_repository import PresentationRepository
            from app.schemas.generated_lesson import LessonGenerationRequest
            from shared.constants import LearningMode

            presentation = await PresentationRepository(uow.session).get_by_public_id(pid)
            gen_service = LessonGenerationService(uow, ai_service=fake_ai)
            req = LessonGenerationRequest(mode=LearningMode.SLIDE)
            lesson_summary = await gen_service.create_lesson(presentation, req)
            lesson_id = lesson_summary["id"]
            await gen_service.run_generation(lesson_id)

        detail = await client.get(f"/api/v1/presentations/{pid}/lessons/{lesson_id}")
        assert detail.status_code == 200
        data = detail.json()["data"]
        assert data["status"] == "ready"
        assert data["version"]["status"] == "succeeded"

        grounding = data["version"]["generation_metadata"]["grounding"]
        assert grounding is not None
        assert grounding["enabled"] is True
        assert grounding["verifier"] == "deterministic"
        assert all(t["verdict"] == "PASS" for t in grounding["topics"])

        async with UnitOfWork() as uow:
            from app.repositories.generated_lesson_repository import GeneratedLessonRepository

            lesson = await GeneratedLessonRepository(uow.session).get_by_public_id(lesson_id)
            version_row = await uow.session.execute(
                select(GeneratedLessonVersion)
                .where(
                    GeneratedLessonVersion.lesson_id == lesson.id,
                    GeneratedLessonVersion.version == 1,
                )
            )
            version = version_row.scalar_one()
            block_rows = await uow.session.execute(
                select(GeneratedBlock)
                .where(GeneratedBlock.lesson_version_id == version.id)
                .order_by(GeneratedBlock.position)
            )
            blocks = list(block_rows.scalars().all())

            assert version.status == "succeeded"
            assert len(blocks) == 3
            assert [b.heading for b in blocks] == ["TCP", "HTTP", "DNS"]

    async def test_fabricated_lesson_fails_version_and_lesson(
        self, client: AsyncClient
    ) -> None:
        pid = await _create_presentation(client, "Fabricated")
        await _upload_and_extract(client, pid)

        fake_ai = _FakeAI(FABRICATED_AI_PAYLOAD)
        async with UnitOfWork() as uow:
            from app.repositories.presentation_repository import PresentationRepository
            from app.schemas.generated_lesson import LessonGenerationRequest
            from shared.constants import LearningMode

            presentation = await PresentationRepository(uow.session).get_by_public_id(pid)
            gen_service = LessonGenerationService(uow, ai_service=fake_ai)
            req = LessonGenerationRequest(mode=LearningMode.SLIDE)
            lesson_summary = await gen_service.create_lesson(presentation, req)
            lesson_id = lesson_summary["id"]
            with pytest.raises(LessonSafetyError):
                await gen_service.run_generation(lesson_id)

            from app.models.generated_lesson_version import LessonVersionStatus
            from app.repositories.generated_lesson_repository import GeneratedLessonRepository

            lesson = await GeneratedLessonRepository(uow.session).get_by_public_id(lesson_id)
            version_row = await uow.session.execute(
                select(GeneratedLessonVersion)
                .where(
                    GeneratedLessonVersion.lesson_id == lesson.id,
                    GeneratedLessonVersion.version == 1,
                )
            )
            version = version_row.scalar_one()
            block_rows = await uow.session.execute(
                select(GeneratedBlock)
                .where(GeneratedBlock.lesson_version_id == version.id)
                .order_by(GeneratedBlock.position)
            )
            blocks = list(block_rows.scalars().all())

            assert version.status == LessonVersionStatus.FAILED.value
            assert version.error_code == "safety_rejected"
            assert len(blocks) == 0

        detail = await client.get(f"/api/v1/presentations/{pid}/lessons/{lesson_id}")
        data = detail.json()["data"]
        assert data["status"] != "ready"
        assert data["version"] is None

        status = await client.get(
            f"/api/v1/presentations/{pid}/lessons/{lesson_id}/status"
        )
        status_data = status.json()["data"]
        assert status_data["status"] == "failed"
        assert status_data["error_code"] == "safety_rejected"

    async def test_mixed_topic_rejects_whole_lesson(self, client: AsyncClient) -> None:
        pid = await _create_presentation(client, "Mixed")
        await _upload_and_extract(client, pid)

        fake_ai = _FakeAI(MIXED_AI_PAYLOAD)
        async with UnitOfWork() as uow:
            from app.repositories.presentation_repository import PresentationRepository
            from app.schemas.generated_lesson import LessonGenerationRequest
            from shared.constants import LearningMode

            presentation = await PresentationRepository(uow.session).get_by_public_id(pid)
            gen_service = LessonGenerationService(uow, ai_service=fake_ai)
            req = LessonGenerationRequest(mode=LearningMode.SLIDE)
            lesson_summary = await gen_service.create_lesson(presentation, req)
            lesson_id = lesson_summary["id"]
            with pytest.raises(LessonSafetyError):
                await gen_service.run_generation(lesson_id)

            from app.repositories.generated_lesson_repository import GeneratedLessonRepository

            lesson = await GeneratedLessonRepository(uow.session).get_by_public_id(lesson_id)
            version_row = await uow.session.execute(
                select(GeneratedLessonVersion)
                .where(
                    GeneratedLessonVersion.lesson_id == lesson.id,
                    GeneratedLessonVersion.version == 1,
                )
            )
            version = version_row.scalar_one()
            block_rows = await uow.session.execute(
                select(GeneratedBlock)
                .where(GeneratedBlock.lesson_version_id == version.id)
                .order_by(GeneratedBlock.position)
            )
            blocks = list(block_rows.scalars().all())

            assert version.status == "failed"
            assert version.error_code == "safety_rejected"
            assert len(blocks) == 0

    async def test_llm_verifier_exercised_through_validate_output(
        self, client: AsyncClient, monkeypatch
    ) -> None:
        """§8 proof: with AI_PROVIDER != local the LLM verifier really runs
        through the exported lesson path (LessonGenerationService →
        validate_output → run_claim_grounding), not only via direct verifier
        calls.  The fabricated claim is rejected with the llm backend."""
        from app.core.config import settings as global_settings

        monkeypatch.setattr(global_settings, "AI_PROVIDER", "gemini")

        pid = await _create_presentation(client, "LLM Verifier Path")
        await _upload_and_extract(client, pid)

        fake_ai = _VerifierAwareFakeAI(FABRICATED_AI_PAYLOAD)
        async with UnitOfWork() as uow:
            from app.repositories.presentation_repository import PresentationRepository
            from app.schemas.generated_lesson import LessonGenerationRequest
            from shared.constants import LearningMode

            presentation = await PresentationRepository(uow.session).get_by_public_id(pid)
            gen_service = LessonGenerationService(uow, ai_service=fake_ai)
            req = LessonGenerationRequest(mode=LearningMode.SLIDE)
            lesson_summary = await gen_service.create_lesson(presentation, req)
            lesson_id = lesson_summary["id"]
            with pytest.raises(LessonSafetyError):
                await gen_service.run_generation(lesson_id)

        assert fake_ai.verifier_calls >= 1, "the LLM verifier was never called through validate_output"
        assert any("guarantees zero packet loss" in c for c in fake_ai.verifier_claims)

    async def test_heuristic_fallback_bypasses_grounding(self, client: AsyncClient) -> None:
        """Heuristic fallback extracts verbatim source content; it is not an AI
        payload, so validate_output is never invoked and the lesson succeeds."""
        pid = await _create_presentation(client, "Heuristic Grounded")
        await _upload_and_extract(client, pid)

        class _FailingAI:
            async def generate(self, request):
                from app.ai.errors import AIQuotaExceededError
                raise AIQuotaExceededError(provider="fake", message="quota exceeded")

        async with UnitOfWork() as uow:
            from app.repositories.presentation_repository import PresentationRepository
            from app.schemas.generated_lesson import LessonGenerationRequest
            from shared.constants import LearningMode

            presentation = await PresentationRepository(uow.session).get_by_public_id(pid)
            gen_service = LessonGenerationService(uow, ai_service=_FailingAI())
            req = LessonGenerationRequest(mode=LearningMode.READING)
            lesson_summary = await gen_service.create_lesson(presentation, req)
            lesson_id = lesson_summary["id"]
            await gen_service.run_generation(lesson_id)

        detail = await client.get(f"/api/v1/presentations/{pid}/lessons/{lesson_id}")
        data = detail.json()["data"]
        assert data["status"] == "ready"
        assert data["version"]["status"] == "succeeded"
        md = data["version"]["generation_metadata"]
        assert md["generation_method"] == "heuristic"
        assert md["grounding"] is None
