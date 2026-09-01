from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from app.ai.errors import AIProviderUnavailableError, AITruncationError
from app.ai.models import AIResponse, TokenUsage
from app.core.config import settings
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.database.unit_of_work import UnitOfWork
from app.models.content_block import ContentBlock
from app.models.content_unit import ContentUnit
from app.models.generated_lesson import GeneratedLesson
from app.models.generated_lesson_version import GeneratedLessonVersion
from app.models.presentation import Presentation
from app.repositories.generated_lesson_repository import (
    GeneratedLessonRepository,
    GeneratedLessonVersionRepository,
)
from app.schemas.generated_lesson import LessonGenerationRequest
from app.services.lesson_generation_service import (
    ERROR_PAYLOAD_INVALID,
    ERROR_SAFETY_REJECTED,
    ERROR_SOURCE_EMPTY,
    LessonGenerationParseError,
    LessonGenerationService,
    LessonGenerationSourceError,
)
from app.services.lesson_safety import LessonSafetyError, LessonSafetyValidator
from shared.constants import (
    ContentBlockType,
    ContentUnitType,
    LearningMode,
    LessonDifficulty,
    LessonRetryState,
    LessonStatus,
    LessonVersionStatus,
)

pytestmark = pytest.mark.asyncio


def _payload_json(**overrides: object) -> str:
    data: dict[str, object] = {
        "title": "Generated Lesson",
        "summary": "A summary.",
        "language": "en",
        "difficulty": "beginner",
        "topics": [
            {"topic": "Intro", "description": "Body"},
            {"topic": "Details", "description": "More"},
        ],
    }
    data.update(overrides)
    return json.dumps(data)


class FakeAIService:
    def __init__(self, responses: list[AIResponse] | None = None, exc: Exception | None = None) -> None:
        self.responses = list(responses or [])
        self.exc = exc
        self.requests: list[object] = []

    async def generate(self, request: object) -> AIResponse:
        self.requests.append(request)
        if self.exc is not None:
            raise self.exc
        if not self.responses:
            raise AssertionError("no fake AI responses queued")
        return self.responses.pop(0)


def _ai_response(text: str, **overrides: object) -> AIResponse:
    values: dict[str, object] = {
        "text": text,
        "usage": TokenUsage(input_tokens=10, output_tokens=5),
        "provider": "fake",
        "model": "fake-model",
        "latency_ms": 12.5,
        "retry_count": 1,
        "request_id": "ai_req_1",
        "correlation_id": "corr_1",
    }
    values.update(overrides)
    return AIResponse(**values)


async def _seed(db_session: object, *, with_units: bool = True) -> Presentation:
    presentation = Presentation(owner_id=None, title="Test Deck")
    db_session.add(presentation)
    await db_session.flush()
    if with_units:
        unit = ContentUnit(
            presentation_id=presentation.id,
            unit_type=ContentUnitType.SLIDE.value,
            position=1,
            title="Slide One",
            raw_text="Hello world content.",
        )
        db_session.add(unit)
        await db_session.flush()
        block = ContentBlock(
            content_unit_id=unit.id,
            block_type=ContentBlockType.PARAGRAPH.value,
            position=0,
            content="Paragraph content.",
        )
        db_session.add(block)
    await db_session.commit()
    return presentation


def _request(**overrides: object) -> LessonGenerationRequest:
    values: dict[str, object] = {
        "mode": LearningMode.SLIDE,
        "title": "My Lesson",
        "language": "en",
        "difficulty": LessonDifficulty.BEGINNER,
    }
    values.update(overrides)
    return LessonGenerationRequest(**values)


def _service(db_session: object, **overrides: object) -> LessonGenerationService:
    kwargs: dict[str, object] = {"ai_service": FakeAIService()}
    kwargs.update(overrides)
    return LessonGenerationService(UnitOfWork(session=db_session), **kwargs)


class TestRepository:
    async def test_create_and_lookup(self, db_session) -> None:
        presentation = await _seed(db_session)
        repo = GeneratedLessonRepository(db_session)
        lesson = await repo.create(
            presentation_id=presentation.id,
            user_id=None,
            idempotency_key="k1",
            mode="slide",
            status="queued",
            title="T",
            language="en",
            difficulty="beginner",
            latest_version=0,
            attempt_count=0,
            max_attempts=3,
            retry_state="none",
        )
        assert lesson.public_id.startswith("lesson_")
        found = await repo.get_by_public_id(lesson.public_id)
        assert found is not None
        assert found.id == lesson.id
        assert found.created_at is not None

    async def test_get_for_presentation_scoping(self, db_session) -> None:
        presentation = await _seed(db_session)
        repo = GeneratedLessonRepository(db_session)
        lesson = await repo.create(
            presentation_id=presentation.id, user_id=None, mode="slide", status="queued"
        )
        await db_session.flush()
        found = await repo.get_by_public_id_for_presentation(presentation.id, lesson.public_id)
        assert found is not None
        wrong = await repo.get_by_public_id_for_presentation(
            uuid.uuid4(), lesson.public_id
        )
        assert wrong is None
        with pytest.raises(NotFoundError):
            await repo.get_by_public_id_for_presentation_or_raise(
                uuid.uuid4(), lesson.public_id
            )

    async def test_idempotency_lookup(self, db_session) -> None:
        presentation = await _seed(db_session)
        repo = GeneratedLessonRepository(db_session)
        a = await repo.create(
            presentation_id=presentation.id,
            user_id=None,
            idempotency_key="dup",
            mode="slide",
            status="queued",
        )
        await db_session.flush()
        found = await repo.find_by_idempotency_key(None, "dup")
        assert found is not None
        assert found.id == a.id
        assert await repo.find_by_idempotency_key(None, "missing") is None

    async def test_list_with_filters_and_pagination(self, db_session) -> None:
        presentation = await _seed(db_session)
        repo = GeneratedLessonRepository(db_session)
        await repo.create(presentation_id=presentation.id, user_id=None, mode="slide", status="queued")
        await repo.create(presentation_id=presentation.id, user_id=None, mode="quiz", status="ready")
        await repo.create(presentation_id=presentation.id, user_id=None, mode="slide", status="ready")
        await db_session.flush()
        items, total = await repo.list_for_presentation(presentation.id, page=1, page_size=25)
        assert total == 3
        items, total = await repo.list_for_presentation(presentation.id, page=1, page_size=25, status="ready")
        assert total == 2
        items, total = await repo.list_for_presentation(presentation.id, page=1, page_size=1, mode="slide")
        assert len(items) == 1
        assert total == 2

    async def test_version_repo_latest_succeeded_and_order(self, db_session) -> None:
        presentation = await _seed(db_session)
        lesson = await GeneratedLessonRepository(db_session).create(
            presentation_id=presentation.id,
            user_id=None,
            mode="slide",
            status="queued",
            latest_version=2,
            attempt_count=2,
            max_attempts=3,
            retry_state="none",
        )
        await db_session.flush()
        vrepo = GeneratedLessonVersionRepository(db_session)
        await vrepo.create(lesson_id=lesson.id, version=1, status="failed", title="T")
        await vrepo.create(lesson_id=lesson.id, version=2, status="succeeded", title="T")
        await db_session.flush()
        latest = await vrepo.get_latest_succeeded_for_lesson(lesson.id)
        assert latest is not None
        assert latest.version == 2
        versions = await vrepo.list_for_lesson(lesson.id)
        assert [v.version for v in versions] == [2, 1]
        by_version = await vrepo.get_by_lesson_and_version(lesson.id, 1)
        assert by_version is not None
        assert by_version.status == "failed"

    async def test_version_cascade_delete(self, db_session) -> None:
        presentation = await _seed(db_session)
        lesson = await GeneratedLessonRepository(db_session).create(
            presentation_id=presentation.id, user_id=None, mode="slide", status="queued"
        )
        await db_session.flush()
        vrepo = GeneratedLessonVersionRepository(db_session)
        await vrepo.create(lesson_id=lesson.id, version=1, status="succeeded", title="T")
        await db_session.flush()
        await vrepo.delete_for_lesson(lesson.id)
        assert await vrepo.count_for_lesson(lesson.id) == 0


class TestCreateLesson:
    async def test_create_queued_lesson(self, db_session) -> None:
        presentation = await _seed(db_session)
        service = _service(db_session)
        result = await service.create_lesson(presentation, _request())
        assert result["status"] == LessonStatus.QUEUED.value
        assert result["duplicate"] is False
        assert result["id"].startswith("lesson_")
        assert result["mode"] == LearningMode.SLIDE.value
        assert result["retry_state"] == LessonRetryState.NONE.value

    async def test_create_rejects_unsupported_language(self, db_session) -> None:
        presentation = await _seed(db_session)
        service = _service(db_session)
        with pytest.raises(ValidationError):
            await service.create_lesson(presentation, _request(language="xx"))

    async def test_create_conflicts_when_no_content(self, db_session) -> None:
        presentation = await _seed(db_session, with_units=False)
        service = _service(db_session)
        with pytest.raises(ConflictError):
            await service.create_lesson(presentation, _request())

    async def test_input_safety_rejects_generation(self, db_session) -> None:
        class RejectingValidator(LessonSafetyValidator):
            name = "rejecting"

            async def validate_input(self, **kwargs: object) -> None:
                raise LessonSafetyError("unsafe source")

            async def validate_output(self, **kwargs: object) -> None:
                return None

        presentation = await _seed(db_session)
        service = _service(db_session, safety_validator=RejectingValidator())
        with pytest.raises(LessonSafetyError):
            await service.create_lesson(presentation, _request())
        assert await GeneratedLessonRepository(db_session).count_for_presentation(presentation.id) == 0

    async def test_idempotency_replay_returns_existing(self, db_session) -> None:
        presentation = await _seed(db_session)
        service = _service(db_session)
        first = await service.create_lesson(presentation, _request(), idempotency_key="key-1")
        second = await service.create_lesson(presentation, _request(), idempotency_key="key-1")
        assert first["duplicate"] is False
        assert second["duplicate"] is True
        assert second["id"] == first["id"]
        assert await GeneratedLessonRepository(db_session).count_for_presentation(presentation.id) == 1

    async def test_idempotency_scoped_per_user(self, db_session) -> None:
        presentation = await _seed(db_session)
        service = _service(db_session)
        first = await service.create_lesson(presentation, _request(), idempotency_key="key-2")
        second = await service.create_lesson(presentation, _request(), idempotency_key="key-2")
        assert second["duplicate"] is True
        assert second["id"] == first["id"]

    async def test_create_stamps_user_id_from_presentation_owner(self, db_session) -> None:
        """WS5: generated lessons adopt the owning user for scoped lookup."""
        owner_id = uuid.uuid4()
        presentation = await _seed(db_session)
        presentation.owner_id = owner_id
        result = await _service(db_session).create_lesson(presentation, _request())
        lesson = await GeneratedLessonRepository(db_session).get_by_public_id(
            result["id"]
        )
        assert lesson is not None
        assert lesson.user_id == owner_id

    async def test_create_with_null_owner_keeps_user_id_null(self, db_session) -> None:
        presentation = await _seed(db_session)
        presentation.owner_id = None
        result = await _service(db_session).create_lesson(presentation, _request())
        lesson = await GeneratedLessonRepository(db_session).get_by_public_id(
            result["id"]
        )
        assert lesson is not None
        assert lesson.user_id is None


class TestRunGeneration:
    async def test_success_persists_version_blocks_and_usage(self, db_session) -> None:
        presentation = await _seed(db_session)
        fake = FakeAIService([_ai_response(_payload_json())])
        service = _service(db_session, ai_service=fake)
        created = await service.create_lesson(presentation, _request())
        result = await service.run_generation(created["id"])

        assert result["status"] == LessonStatus.READY.value
        assert result["latest_version"] == 1
        assert result["retry_state"] == LessonRetryState.NONE.value

        lesson = await GeneratedLessonRepository(db_session).get_by_public_id(created["id"])
        assert lesson is not None
        assert lesson.status == LessonStatus.READY.value
        assert lesson.attempt_count == 1

        versions = await GeneratedLessonVersionRepository(db_session).list_for_lesson(lesson.id)
        assert len(versions) == 1
        version = versions[0]
        assert version.status == LessonVersionStatus.SUCCEEDED.value
        assert version.title == "Generated Lesson"
        assert version.language == "en"
        assert version.difficulty == LessonDifficulty.BEGINNER.value
        assert version.input_tokens == 10
        assert version.output_tokens == 5
        assert version.total_tokens == 15
        assert version.provider == "fake"
        assert version.model == "fake-model"
        assert version.prompt_version == "3"
        assert version.payload_schema_version == "1"
        assert version.request_id == "ai_req_1"
        assert version.correlation_id == "corr_1"
        assert version.provider_retry_count == 1
        assert version.latency_ms == 12.5
        assert len(version.payload_hash) == 64
        assert len(version.prompt_hash) == 64
        assert version.generation_metadata["source_units_count"] == 1
        assert version.generation_metadata["safety_checks"] == ["noop"]
        assert version.quality_score is None

        assert len(version.blocks) == 2
        assert version.blocks[0].position == 0
        assert version.blocks[0].public_id.startswith("gblk_")
        assert version.blocks[0].block_type_enum.value == "paragraph"

        # AI request metadata carries resource context for usage accounting
        assert fake.requests
        ai_req = fake.requests[0]
        assert ai_req.metadata["resource_type"] == "generated_lesson"
        assert ai_req.metadata["resource_id"] == created["id"]
        assert ai_req.metadata["presentation_id"] == presentation.public_id

    async def test_get_lesson_includes_latest_version_and_blocks(self, db_session) -> None:
        presentation = await _seed(db_session)
        fake = FakeAIService([_ai_response(_payload_json())])
        service = _service(db_session, ai_service=fake)
        created = await service.create_lesson(presentation, _request())
        await service.run_generation(created["id"])

        detail = await service.get_lesson(presentation, created["id"])
        assert detail["status"] == LessonStatus.READY.value
        assert detail["version"] is not None
        assert detail["version"]["version"] == 1
        assert len(detail["version"]["blocks"]) == 2

    async def test_generation_succeeds_with_null_meta_blocks(self, db_session) -> None:
        presentation = await _seed(db_session)
        raw = _payload_json(
            topics=[
                {"topic": "Intro", "description": "Body"},
                {"topic": "Details", "description": "More"},
            ]
        )
        fake = FakeAIService([_ai_response(raw)])
        service = _service(db_session, ai_service=fake)
        created = await service.create_lesson(presentation, _request())
        await service.run_generation(created["id"])

        lesson = await GeneratedLessonRepository(db_session).get_by_public_id(created["id"])
        assert lesson is not None
        assert lesson.status == LessonStatus.READY.value
        blocks = list((await GeneratedLessonVersionRepository(db_session).list_for_lesson(lesson.id))[0].blocks)
        assert len(blocks) == 2

    async def test_transient_error_falls_back_to_heuristic(self, db_session) -> None:
        presentation = await _seed(db_session)
        exc = AIProviderUnavailableError(provider="fake", model="fake-model")
        fake = FakeAIService(exc=exc)
        service = _service(db_session, ai_service=fake)
        created = await service.create_lesson(presentation, _request())

        result = await service.run_generation(created["id"])

        assert result["status"] == "ready"
        lesson = await GeneratedLessonRepository(db_session).get_by_public_id(created["id"])
        assert lesson is not None
        assert lesson.status == LessonStatus.READY.value
        assert lesson.attempt_count == 1
        versions = await GeneratedLessonVersionRepository(db_session).list_for_lesson(lesson.id)
        assert len(versions) == 1
        assert versions[0].status == LessonVersionStatus.SUCCEEDED.value
        assert versions[0].generation_metadata["generation_method"] == "heuristic"

    async def test_ai_error_falls_back_to_heuristic(self, db_session) -> None:
        presentation = await _seed(db_session)
        fake = FakeAIService(
            exc=AIProviderUnavailableError(provider="fake", model="fake-model")
        )
        service = _service(db_session, ai_service=fake)
        with patch.object(settings, "AI_LESSON_MAX_ATTEMPTS", 1):
            created = await service.create_lesson(presentation, _request())
            result = await service.run_generation(created["id"])

        assert result["status"] == "ready"
        lesson = await GeneratedLessonRepository(db_session).get_by_public_id(created["id"])
        assert lesson is not None
        assert lesson.status == LessonStatus.READY.value
        assert lesson.attempt_count == 1
        versions = await GeneratedLessonVersionRepository(db_session).list_for_lesson(lesson.id)
        assert versions[0].generation_metadata["generation_method"] == "heuristic"

    async def test_truncation_falls_back_to_heuristic(self, db_session) -> None:
        presentation = await _seed(db_session)
        exc = AITruncationError(provider="fake", model="fake-model")
        fake = FakeAIService(exc=exc)
        service = _service(db_session, ai_service=fake)
        created = await service.create_lesson(presentation, _request())

        result = await service.run_generation(created["id"])

        assert result["status"] == "ready"
        lesson = await GeneratedLessonRepository(db_session).get_by_public_id(created["id"])
        assert lesson is not None
        assert lesson.status == LessonStatus.READY.value
        assert lesson.attempt_count == 1
        versions = await GeneratedLessonVersionRepository(db_session).list_for_lesson(lesson.id)
        assert len(versions) == 1
        assert versions[0].status == LessonVersionStatus.SUCCEEDED.value
        assert versions[0].generation_metadata["generation_method"] == "heuristic"

    async def test_ai_error_falls_back_to_heuristic_no_retry(self, db_session) -> None:
        presentation = await _seed(db_session)
        exc = AITruncationError(provider="fake", model="fake-model")
        fake = FakeAIService(exc=exc)
        service = _service(db_session, ai_service=fake)
        created = await service.create_lesson(presentation, _request())

        result = await service.run_generation(created["id"])
        result2 = await service.run_generation(created["id"])

        assert result["status"] == "ready"
        assert result2["status"] == "ready"
        assert len(fake.requests) == 2

    async def test_unparsable_output_fails_version(self, db_session) -> None:
        presentation = await _seed(db_session)
        fake = FakeAIService([_ai_response("this is not json")])
        service = _service(db_session, ai_service=fake)
        created = await service.create_lesson(presentation, _request())

        with pytest.raises(LessonGenerationParseError):
            await service.run_generation(created["id"])

        lesson = await GeneratedLessonRepository(db_session).get_by_public_id(created["id"])
        assert lesson is not None
        assert lesson.status == LessonStatus.FAILED.value
        versions = await GeneratedLessonVersionRepository(db_session).list_for_lesson(lesson.id)
        assert versions[0].error_code == ERROR_PAYLOAD_INVALID
        assert versions[0].error_message is not None

    async def test_output_safety_rejection_fails_version(self, db_session) -> None:
        class RejectingOutputValidator(LessonSafetyValidator):
            name = "rejecting_output"

            async def validate_input(self, **kwargs: object) -> None:
                return None

            async def validate_output(self, **kwargs: object) -> None:
                raise LessonSafetyError("unsafe output")

        presentation = await _seed(db_session)
        fake = FakeAIService([_ai_response(_payload_json())])
        service = _service(
            db_session, ai_service=fake, safety_validator=RejectingOutputValidator()
        )
        created = await service.create_lesson(presentation, _request())

        with pytest.raises(LessonSafetyError):
            await service.run_generation(created["id"])

        lesson = await GeneratedLessonRepository(db_session).get_by_public_id(created["id"])
        assert lesson is not None
        assert lesson.status == LessonStatus.FAILED.value
        versions = await GeneratedLessonVersionRepository(db_session).list_for_lesson(lesson.id)
        assert versions[0].error_code == ERROR_SAFETY_REJECTED

    async def test_source_gone_after_creation(self, db_session) -> None:
        presentation = await _seed(db_session, with_units=False)
        lesson = await GeneratedLessonRepository(db_session).create(
            presentation_id=presentation.id,
            user_id=None,
            mode="slide",
            status="queued",
            latest_version=0,
            attempt_count=0,
            max_attempts=3,
            retry_state="none",
        )
        await db_session.flush()
        service = _service(db_session)
        with pytest.raises(LessonGenerationSourceError):
            await service.run_generation(lesson.public_id)
        failed = await GeneratedLessonRepository(db_session).get_by_public_id(lesson.public_id)
        assert failed is not None
        assert failed.status == LessonStatus.FAILED.value
        versions = await GeneratedLessonVersionRepository(db_session).list_for_lesson(lesson.id)
        assert versions[0].error_code == ERROR_SOURCE_EMPTY


class TestReadAndDelete:
    async def _ready_lesson(
        self, db_session, presentation: Presentation
    ) -> str:
        fake = FakeAIService([_ai_response(_payload_json())])
        service = _service(db_session, ai_service=fake)
        created = await service.create_lesson(presentation, _request())
        await service.run_generation(created["id"])
        return created["id"]

    async def test_list_lessons_with_filters(self, db_session) -> None:
        presentation = await _seed(db_session)
        service = _service(db_session)
        await service.create_lesson(presentation, _request())
        await service.create_lesson(presentation, _request(mode=LearningMode.READING, title="Reading"))

        items, total = await service.list_lessons(
            presentation, page=1, page_size=25, mode=None, status=None
        )
        assert total == 2
        items, total = await service.list_lessons(
            presentation, page=1, page_size=25, mode="reading", status=None
        )
        assert total == 1
        assert items[0]["mode"] == "reading"

    async def test_get_status_poll(self, db_session) -> None:
        presentation = await _seed(db_session)
        service = _service(db_session)
        created = await service.create_lesson(presentation, _request())
        status = await service.get_status(presentation, created["id"])
        assert status["status"] == LessonStatus.QUEUED.value
        assert status["retry_state"] == LessonRetryState.NONE.value
        assert status["max_attempts"] == settings.AI_LESSON_MAX_ATTEMPTS
        assert status["error_code"] is None

    async def test_get_status_exposes_failed_error(self, db_session) -> None:
        presentation = await _seed(db_session)
        fake = FakeAIService([_ai_response("not json")])
        service = _service(db_session, ai_service=fake)
        created = await service.create_lesson(presentation, _request())
        with pytest.raises(LessonGenerationParseError):
            await service.run_generation(created["id"])
        status = await service.get_status(presentation, created["id"])
        assert status["status"] == LessonStatus.FAILED.value
        assert status["error_code"] == ERROR_PAYLOAD_INVALID

    async def test_list_and_get_versions(self, db_session) -> None:
        presentation = await _seed(db_session)
        service = _service(db_session)
        lesson_id = await self._ready_lesson(db_session, presentation)

        versions = await service.list_versions(presentation, lesson_id)
        assert len(versions) == 1
        assert "blocks" not in versions[0]

        detail = await service.get_version(presentation, lesson_id, versions[0]["id"])
        assert detail["version"] == 1
        assert len(detail["blocks"]) == 2

    async def test_get_lesson_not_found_raises(self, db_session) -> None:
        presentation = await _seed(db_session)
        service = _service(db_session)
        with pytest.raises(NotFoundError):
            await service.get_lesson(presentation, "lesson_missing")

    async def test_delete_lesson_hard(self, db_session) -> None:
        presentation = await _seed(db_session)
        service = _service(db_session)
        created = await service.create_lesson(presentation, _request())
        repo = GeneratedLessonRepository(db_session)
        assert await repo.count_for_presentation(presentation.id) == 1
        await service.delete_lesson(presentation, created["id"])
        assert await repo.count_for_presentation(presentation.id) == 0
        with pytest.raises(NotFoundError):
            await service.get_lesson(presentation, created["id"])
