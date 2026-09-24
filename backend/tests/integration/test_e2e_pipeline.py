"""End-to-end pipeline tests: upload → extraction → lesson generation → player.

Tests the full user journey through API endpoints with mocked external
dependencies (storage, AI). Extraction is driven directly through the
service layer since Celery dispatch is patched out in tests.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.exceptions import ExtractionError, NotFoundError
from app.database.unit_of_work import UnitOfWork
from app.services.content_extraction_service import ContentExtractionService
from app.services.lesson_generation_service import LessonGenerationService

pytestmark = pytest.mark.integration

SOURCE_CONTENT = (
    b"Machine Learning Fundamentals\n\n"
    b"Supervised learning uses labeled data to train models. "
    b"The model learns to map inputs to known outputs. "
    b"Common algorithms include linear regression, decision trees, and neural networks.\n\n"
    b"Unsupervised learning finds hidden patterns in unlabeled data. "
    b"Clustering algorithms group similar data points together. "
    b"Dimensionality reduction techniques compress feature spaces.\n\n"
    b"Evaluation metrics quantify model performance. "
    b"Accuracy measures the fraction of correct predictions. "
    b"Precision and recall balance false positives and false negatives."
)

LESSON_AI_PAYLOAD = (
    '{"title": "ML Fundamentals", "summary": "A concise overview.", '
    '"language": "en", "difficulty": "intermediate", "topics": ['
    '{"topic": "Supervised Learning", "description": "Uses labeled data to train models."}, '
    '{"topic": "Unsupervised Learning", "description": "Finds patterns in unlabeled data."}, '
    '{"topic": "Evaluation Metrics", "description": "Quantify model performance."}'
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
    response = await client.post(
        "/api/v1/presentations",
        json={"title": title},
    )
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


async def _get_presentation(client: AsyncClient, pid: str):
    async with UnitOfWork() as uow:
        from app.repositories.presentation_repository import PresentationRepository
        repo = PresentationRepository(uow.session)
        return await repo.get_by_public_id(pid)


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


# ── TEST-E2E-01: Upload → Extract → Content retrieval ────────────────────────

class TestE2EUploadExtraction:
    async def test_upload_extracts_and_content_is_retrievable(self, client: AsyncClient) -> None:
        pid = await _create_presentation(client, "E2E Upload Test")
        await _upload_and_extract(client, pid)

        status_resp = await client.get(f"/api/v1/presentations/{pid}/processing-status")
        assert status_resp.status_code == 200
        assert status_resp.json()["data"]["extraction_status"] == "ready"
        assert status_resp.json()["data"]["units_count"] == 1

        content_resp = await client.get(f"/api/v1/presentations/{pid}/content")
        assert content_resp.status_code == 200
        units = content_resp.json()["data"]["units"]
        assert len(units) == 1
        assert len(units[0]["blocks"]) >= 3

    async def test_upload_wrong_extension_rejected(self, client: AsyncClient) -> None:
        pid = await _create_presentation(client, "Bad File")
        resp = await client.post(
            f"/api/v1/presentations/{pid}/source",
            files={"source": ("image.png", b"binary", "image/png")},
        )
        assert resp.status_code == 422

    async def test_empty_file_rejected(self, client: AsyncClient) -> None:
        pid = await _create_presentation(client, "Empty File")
        resp = await client.post(
            f"/api/v1/presentations/{pid}/source",
            files={"source": ("notes.txt", b"", "text/plain")},
        )
        assert resp.status_code == 409

    async def test_extraction_with_no_source_fails(self) -> None:
        pid = str(uuid.uuid4())
        with pytest.raises(NotFoundError):
            async with UnitOfWork() as uow:
                await ContentExtractionService(uow).extract_presentation(pid)


# ── TEST-E2E-02: Lesson generation via API with mocked AI ────────────────────

class TestE2EGenerationViaAPI:
    async def test_generate_lesson_via_api(self, client: AsyncClient) -> None:
        pid = await _create_presentation(client, "Lesson Gen Test")
        await _upload_and_extract(client, pid)

        fake_ai = _FakeAI(LESSON_AI_PAYLOAD)
        with patch(
            "app.services.lesson_generation_service.AIContentService",
            lambda uow=None, **kw: fake_ai,
        ):
            lesson_resp = await client.post(
                f"/api/v1/presentations/{pid}/lessons",
                json={"mode": "slide", "title": "ML Lesson", "language": "en"},
            )
            assert lesson_resp.status_code == 201
            lesson_data = lesson_resp.json()["data"]
            lesson_id = lesson_data["id"]
            assert lesson_data["status"] == "queued"

            async with UnitOfWork() as uow:
                gen_service = LessonGenerationService(uow, ai_service=fake_ai)
                await gen_service.run_generation(lesson_id)

            detail = await client.get(f"/api/v1/presentations/{pid}/lessons/{lesson_id}")
            assert detail.status_code == 200
            assert detail.json()["data"]["status"] == "ready"
            assert detail.json()["data"]["version"]["status"] == "succeeded"

    async def test_lesson_listed_after_generation(self, client: AsyncClient) -> None:
        pid = await _create_presentation(client, "List Test")
        await _upload_and_extract(client, pid)

        fake_ai = _FakeAI(LESSON_AI_PAYLOAD)
        with patch(
            "app.services.lesson_generation_service.AIContentService",
            lambda uow=None, **kw: fake_ai,
        ):
            lesson_resp = await client.post(
                f"/api/v1/presentations/{pid}/lessons",
                json={"mode": "reading"},
            )
            assert lesson_resp.status_code == 201
            lesson_id = lesson_resp.json()["data"]["id"]

            async with UnitOfWork() as uow:
                gen_service = LessonGenerationService(uow, ai_service=fake_ai)
                await gen_service.run_generation(lesson_id)

            list_resp = await client.get(f"/api/v1/presentations/{pid}/lessons")
            assert list_resp.status_code == 200
            items = list_resp.json()["data"]
            assert len(items) >= 1
            assert any(i["id"] == lesson_id for i in items)


# ── TEST-E2E-03: Heuristic fallback path ─────────────────────────────────────

class TestE2EHeuristicFallback:
    async def test_heuristic_fallback_produces_valid_lesson(self, client: AsyncClient) -> None:
        pid = await _create_presentation(client, "Heuristic Test")
        await _upload_and_extract(client, pid)

        async with UnitOfWork() as uow:
            from app.models.presentation import Presentation

            presentation = await _get_presentation(client, pid)

            from app.schemas.generated_lesson import LessonGenerationRequest
            from shared.constants import LearningMode

            gen_service = LessonGenerationService(uow)
            req = LessonGenerationRequest(mode=LearningMode.READING)
            lesson_summary = await gen_service.create_lesson(presentation, req)
            lesson_id = lesson_summary["id"]

            class FailingAI:
                async def generate(self, request):
                    from app.ai.errors import AIQuotaExceededError
                    raise AIQuotaExceededError(
                        provider="gemini",
                        message="quota exceeded",
                    )

            failing_ai = FailingAI()
            gen_service2 = LessonGenerationService(uow, ai_service=failing_ai)
            await gen_service2.run_generation(lesson_id)

        detail = await client.get(f"/api/v1/presentations/{pid}/lessons/{lesson_id}")
        assert detail.status_code == 200
        assert detail.json()["data"]["status"] == "ready"
        assert detail.json()["data"]["version"]["status"] == "succeeded"
        assert detail.json()["data"]["version"]["generation_metadata"]["generation_method"] == "heuristic"

    async def test_heuristic_no_content_raises(self, client: AsyncClient) -> None:
        pid = await _create_presentation(client, "Empty Content")
        resp = await client.post(
            f"/api/v1/presentations/{pid}/lessons",
            json={"mode": "slide"},
        )
        assert resp.status_code == 409


# ── TEST-E2E-04: AI output validation ────────────────────────────────────────

class TestE2EAIOutputValidation:
    async def test_invalid_ai_payload_fails(self, client: AsyncClient) -> None:
        pid = await _create_presentation(client, "Bad AI Output")
        await _upload_and_extract(client, pid)

        bad_ai = _FakeAI('{"title": "Bad", "no_topics_field": true}')

        async with UnitOfWork() as uow:
            presentation = await _get_presentation(client, pid)

            from app.schemas.generated_lesson import LessonGenerationRequest
            from shared.constants import LearningMode

            gen_service = LessonGenerationService(uow, ai_service=bad_ai)
            req = LessonGenerationRequest(mode=LearningMode.SLIDE)
            lesson_summary = await gen_service.create_lesson(presentation, req)
            lesson_id = lesson_summary["id"]

            from app.services.lesson_generation_service import LessonGenerationParseError
            with pytest.raises(LessonGenerationParseError):
                await gen_service.run_generation(lesson_id)

    async def test_empty_topics_in_payload_fails(self, client: AsyncClient) -> None:
        pid = await _create_presentation(client, "Empty Topics")
        await _upload_and_extract(client, pid)

        empty_topics_ai = _FakeAI('{"title": "No Topics", "topics": []}')

        async with UnitOfWork() as uow:
            presentation = await _get_presentation(client, pid)

            from app.schemas.generated_lesson import LessonGenerationRequest
            from shared.constants import LearningMode

            gen_service = LessonGenerationService(uow, ai_service=empty_topics_ai)
            req = LessonGenerationRequest(mode=LearningMode.SLIDE)
            lesson_summary = await gen_service.create_lesson(presentation, req)
            lesson_id = lesson_summary["id"]

            from app.services.lesson_generation_service import LessonGenerationParseError
            with pytest.raises(LessonGenerationParseError):
                await gen_service.run_generation(lesson_id)


# ── TEST-E2E-05: Lesson persists and is retrievable ──────────────────────────

class TestE2ELessonPersistence:
    async def test_lesson_survives_and_listed(self, client: AsyncClient) -> None:
        pid = await _create_presentation(client, "Persist Test")
        await _upload_and_extract(client, pid)

        fake_ai = _FakeAI(LESSON_AI_PAYLOAD)
        with patch(
            "app.services.lesson_generation_service.AIContentService",
            lambda uow=None, **kw: fake_ai,
        ):
            gen_resp = await client.post(
                f"/api/v1/presentations/{pid}/lessons",
                json={"mode": "slide"},
            )
            assert gen_resp.status_code == 201
            lesson_id = gen_resp.json()["data"]["id"]

            async with UnitOfWork() as uow:
                gen_svc = LessonGenerationService(uow, ai_service=fake_ai)
                await gen_svc.run_generation(lesson_id)

            detail_resp = await client.get(f"/api/v1/presentations/{pid}/lessons/{lesson_id}")
            assert detail_resp.status_code == 200
            detail = detail_resp.json()["data"]
            assert detail["status"] == "ready"
            assert detail["version"]["blocks"]
            assert len(detail["version"]["blocks"]) == 3

            list_resp = await client.get(f"/api/v1/presentations/{pid}/lessons")
            assert list_resp.status_code == 200
            assert any(i["id"] == lesson_id for i in list_resp.json()["data"])


# ── TEST-E2E-06: Lesson player start → advance → set-topic ──────────────────

class TestE2EPlayerFlow:
    async def test_player_full_flow(self, client: AsyncClient) -> None:
        pid = await _create_presentation(client, "Player Test")
        await _upload_and_extract(client, pid)

        fake_ai = _FakeAI(LESSON_AI_PAYLOAD)
        with patch(
            "app.services.lesson_generation_service.AIContentService",
            lambda uow=None, **kw: fake_ai,
        ):
            gen_resp = await client.post(
                f"/api/v1/presentations/{pid}/lessons",
                json={"mode": "slide"},
            )
            assert gen_resp.status_code == 201
            lesson_id = gen_resp.json()["data"]["id"]

            async with UnitOfWork() as uow:
                gen_svc = LessonGenerationService(uow, ai_service=fake_ai)
                await gen_svc.run_generation(lesson_id)

        state_resp = await client.get(f"/api/v1/lessons/{lesson_id}/player")
        assert state_resp.status_code == 200
        state = state_resp.json()["data"]
        assert state["lesson"]["status"] == "ready"
        assert len(state["topics"]) == 3
        assert state["session"] is None

        start_resp = await client.post(
            f"/api/v1/lessons/{lesson_id}/player/start",
            json={"device_id": "test-device"},
        )
        assert start_resp.status_code == 200
        session = start_resp.json()["data"]["session"]
        assert session["session_id"]
        assert session["topic_index"] == 0
        assert session["total_topics"] == 3
        session_id = session["session_id"]

        advance_resp = await client.post(
            f"/api/v1/lessons/{lesson_id}/player/advance",
            json={"session_id": session_id},
        )
        assert advance_resp.status_code == 200
        assert advance_resp.json()["data"]["topic_index"] == 1

        advance_resp2 = await client.post(
            f"/api/v1/lessons/{lesson_id}/player/advance",
            json={"session_id": session_id},
        )
        assert advance_resp2.status_code == 200
        assert advance_resp2.json()["data"]["topic_index"] == 2
        assert advance_resp2.json()["data"]["status"] == "completed"

        set_resp = await client.post(
            f"/api/v1/lessons/{lesson_id}/player/set-topic",
            json={"session_id": session_id, "topic_index": 0},
        )
        assert set_resp.status_code == 200
        assert set_resp.json()["data"]["topic_index"] == 0
        assert set_resp.json()["data"]["status"] == "active"

    async def test_player_ownership_enforced(self, client: AsyncClient) -> None:
        pid = await _create_presentation(client, "Ownership Test")
        await _upload_and_extract(client, pid)

        fake_ai = _FakeAI(LESSON_AI_PAYLOAD)
        with patch(
            "app.services.lesson_generation_service.AIContentService",
            lambda uow=None, **kw: fake_ai,
        ):
            gen_resp = await client.post(
                f"/api/v1/presentations/{pid}/lessons",
                json={"mode": "slide"},
            )
            assert gen_resp.status_code == 201
            lesson_id = gen_resp.json()["data"]["id"]

            async with UnitOfWork() as uow:
                gen_svc = LessonGenerationService(uow, ai_service=fake_ai)
                await gen_svc.run_generation(lesson_id)

        from app.core.dependencies import get_current_user
        from app.main import app as _app
        from tests.conftest import _FakeUser

        class OtherUser:
            id = uuid.UUID("99999999-9999-9999-9999-999999999999")
            email = "other@example.com"
            name = "Other"

        async def _other_user():
            return OtherUser()

        _app.dependency_overrides[get_current_user] = _other_user
        try:
            resp = await client.get(f"/api/v1/lessons/{lesson_id}/player")
            assert resp.status_code == 404
        finally:
            async def _restore():
                return _FakeUser()
            _app.dependency_overrides[get_current_user] = _restore


# ── TEST-E2E-07: Lesson generation on presentation without source ────────────

class TestE2ENoSourceLesson:
    async def test_generate_lesson_no_source_returns_409(self, client: AsyncClient) -> None:
        pid = await _create_presentation(client, "No Source")
        resp = await client.post(
            f"/api/v1/presentations/{pid}/lessons",
            json={"mode": "slide"},
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "CONFLICT"


# ── TEST-E2E-08: Duplicate lesson idempotency ────────────────────────────────

class TestE2EIdempotency:
    async def test_duplicate_idempotency_key_returns_same_lesson(self, client: AsyncClient) -> None:
        pid = await _create_presentation(client, "Idempotency Test")
        await _upload_and_extract(client, pid)

        fake_ai = _FakeAI(LESSON_AI_PAYLOAD)
        with patch(
            "app.services.lesson_generation_service.AIContentService",
            lambda uow=None, **kw: fake_ai,
        ):
            resp1 = await client.post(
                f"/api/v1/presentations/{pid}/lessons",
                json={"mode": "slide"},
                headers={"Idempotency-Key": "idem-key-123"},
            )
            assert resp1.status_code == 201
            id1 = resp1.json()["data"]["id"]

            resp2 = await client.post(
                f"/api/v1/presentations/{pid}/lessons",
                json={"mode": "slide"},
                headers={"Idempotency-Key": "idem-key-123"},
            )
            assert resp2.status_code == 201
            assert resp2.json()["data"]["id"] == id1
            assert resp2.json()["data"]["duplicate"] is True


# ── TEST-E2E-09: Multiple lessons on same presentation ───────────────────────

class TestE2EMultipleLessons:
    async def test_two_different_modes_produce_separate_lessons(self, client: AsyncClient) -> None:
        pid = await _create_presentation(client, "Multi Lesson")
        await _upload_and_extract(client, pid)

        fake_ai = _FakeAI(LESSON_AI_PAYLOAD)
        with patch(
            "app.services.lesson_generation_service.AIContentService",
            lambda uow=None, **kw: fake_ai,
        ):
            r1 = await client.post(
                f"/api/v1/presentations/{pid}/lessons",
                json={"mode": "slide"},
            )
            r2 = await client.post(
                f"/api/v1/presentations/{pid}/lessons",
                json={"mode": "reading"},
            )
            id1 = r1.json()["data"]["id"]
            id2 = r2.json()["data"]["id"]
            assert id1 != id2

            async with UnitOfWork() as uow:
                svc = LessonGenerationService(uow, ai_service=fake_ai)
                await svc.run_generation(id1)
                await svc.run_generation(id2)

            list_resp = await client.get(f"/api/v1/presentations/{pid}/lessons")
            items = list_resp.json()["data"]
            assert len(items) >= 2


# ── TEST-E2E-10: Full pipeline upload → extract → topic outline → lesson → player ─

class TestE2EFullPipeline:
    async def test_complete_pipeline(self, client: AsyncClient) -> None:
        pid = await _create_presentation(client, "Full Pipeline")
        await _upload_and_extract(client, pid)

        status_resp = await client.get(f"/api/v1/presentations/{pid}/processing-status")
        assert status_resp.json()["data"]["extraction_status"] == "ready"

        outline_json = '{"title": "ML Overview", "topics": [{"title": "Intro", "slide_ranges": [1, 1]}]}'
        fake_outline_ai = MagicMock(
            text=outline_json,
            provider="fake",
            model="fake-model",
            request_id="outline_1",
            correlation_id="corr_2",
        )

        class OutlineAI:
            async def generate(self, request):
                return fake_outline_ai

        with patch(
            "app.services.topic_outline_service.AIContentService",
            lambda uow=None: OutlineAI(),
        ):
            topic_resp = await client.post(
                f"/api/v1/presentations/{pid}/topics/regenerate",
            )
            assert topic_resp.status_code == 200
            assert topic_resp.json()["data"]["status"] == "succeeded"
            assert len(topic_resp.json()["data"]["topics"]) == 1

        fake_lesson_ai = _FakeAI(LESSON_AI_PAYLOAD)
        with patch(
            "app.services.lesson_generation_service.AIContentService",
            lambda uow=None, **kw: fake_lesson_ai,
        ):
            gen_resp = await client.post(
                f"/api/v1/presentations/{pid}/lessons",
                json={"mode": "slide", "title": "Full Pipeline Lesson"},
            )
            assert gen_resp.status_code == 201
            lesson_id = gen_resp.json()["data"]["id"]

            async with UnitOfWork() as uow:
                svc = LessonGenerationService(uow, ai_service=fake_lesson_ai)
                await svc.run_generation(lesson_id)

            verify_resp = await client.get(f"/api/v1/presentations/{pid}/lessons/{lesson_id}")
            assert verify_resp.json()["data"]["version"]["status"] == "succeeded"

        player_resp = await client.get(f"/api/v1/lessons/{lesson_id}/player")
        assert player_resp.status_code == 200
        player_data = player_resp.json()["data"]
        assert player_data["lesson"]["status"] == "ready"
        assert len(player_data["topics"]) == 3

        start_resp = await client.post(
            f"/api/v1/lessons/{lesson_id}/player/start",
            json={},
        )
        assert start_resp.status_code == 200
        sid = start_resp.json()["data"]["session"]["session_id"]

        for expected_idx in [1, 2]:
            adv = await client.post(
                f"/api/v1/lessons/{lesson_id}/player/advance",
                json={"session_id": sid},
            )
            assert adv.status_code == 200
            assert adv.json()["data"]["topic_index"] == expected_idx

        final = await client.get(f"/api/v1/lessons/{lesson_id}/player")
        final_state = final.json()["data"]
        assert final_state["session"]["topic_index"] == 2
        assert final_state["session"]["status"] == "completed"
