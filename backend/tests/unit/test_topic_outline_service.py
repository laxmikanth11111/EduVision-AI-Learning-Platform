from __future__ import annotations

import uuid

import pytest

from app.ai.models import AIResponse, TokenUsage
from app.core.exceptions import (
    ConflictError,
)
from app.core.exceptions import (
    ValidationError as AppValidationError,
)
from app.database.unit_of_work import UnitOfWork
from app.models.content_block import ContentBlock
from app.models.content_unit import ContentUnit
from app.models.presentation import Presentation
from app.models.topic_outline import TopicOutline
from app.services.topic_outline_service import TopicOutlineService
from shared.constants import ContentBlockType, ContentUnitType

pytestmark = pytest.mark.asyncio


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


OUTLINE_JSON = (
    '{"title": "Unit 2 Overview", "topics": ['
    '{"title": "Introduction", "slide_ranges": [1, 2]},'
    '{"title": "Core Concepts", "slide_ranges": [3, 4]},'
    '{"title": "Wrap Up", "slide_ranges": [5, 6]}]}'
)


async def _seed(db_session: object, *, with_units: bool = True) -> Presentation:
    presentation = Presentation(owner_id=None, title="DA Unit 2")
    db_session.add(presentation)
    await db_session.flush()
    if with_units:
        for position in range(1, 7):
            unit = ContentUnit(
                presentation_id=presentation.id,
                unit_type=ContentUnitType.SLIDE.value,
                position=position,
                title=f"Slide {position}",
                raw_text=f"Body content {position}.",
            )
            db_session.add(unit)
            await db_session.flush()
            block = ContentBlock(
                content_unit_id=unit.id,
                block_type=ContentBlockType.PARAGRAPH.value,
                position=0,
                content=f"Paragraph {position}.",
            )
            db_session.add(block)
    await db_session.commit()
    return presentation


def _service(db_session: object, ai: FakeAIService) -> TopicOutlineService:
    return TopicOutlineService(UnitOfWork(session=db_session), ai_service=ai)


class TestRegenerate:
    async def test_conflict_when_no_units(self, db_session: object) -> None:
        presentation = await _seed(db_session, with_units=False)
        ai = FakeAIService(responses=[])
        with pytest.raises(ConflictError):
            await _service(db_session, ai).regenerate(presentation)

    async def test_happy_path_persists_and_returns_outline(
        self, db_session: object
    ) -> None:
        presentation = await _seed(db_session)
        ai = FakeAIService(responses=[_ai_response(OUTLINE_JSON)])
        service = _service(db_session, ai)

        result = await service.regenerate(presentation)

        assert result["presentation_id"] == presentation.public_id
        assert result["title"] == "Unit 2 Overview"
        assert result["status"] == "succeeded"
        assert len(result["topics"]) == 3
        assert result["topics"][0]["title"] == "Introduction"
        assert result["topics"][0]["slide_ranges"] == [1, 2]
        assert result["provider"] == "fake"
        assert result["model"] == "fake-model"
        assert len(ai.requests) == 1

        row = await TopicOutlineService(
            UnitOfWork(session=db_session), ai_service=ai
        ).get_outline_data(presentation)
        assert row["status"] == "succeeded"
        assert len(row["topics"]) == 3

    async def test_source_text_passes_slide_positions(
        self, db_session: object
    ) -> None:
        presentation = await _seed(db_session)
        ai = FakeAIService(responses=[_ai_response(OUTLINE_JSON)])
        await _service(db_session, ai).regenerate(presentation)
        request = ai.requests[0]
        assert "[1] Slide 1" in request.user_prompt
        assert "[6] Slide 6" in request.user_prompt
        assert "--- SOURCE CONTENT ---" in request.user_prompt
        assert request.response_format == "json"

    async def test_clamps_and_sorts_ranges(self, db_session: object) -> None:
        presentation = await _seed(db_session)
        payload = (
            '{"title": "T", "topics": ['
            '{"title": "Out Of Range", "slide_ranges": [10, 20]},'
            '{"title": "First", "slide_ranges": [2, 3]},'
            '{"title": "Wrap", "slide_ranges": [4, 6]}]}'
        )
        ai = FakeAIService(responses=[_ai_response(payload)])
        result = await _service(db_session, ai).regenerate(presentation)
        titles = [t["title"] for t in result["topics"]]
        assert titles == ["First", "Wrap", "Out Of Range"]
        out_of_range = result["topics"][-1]
        assert out_of_range["slide_ranges"] == [6, 6]

    async def test_regenerate_replaces_previous_outline(
        self, db_session: object
    ) -> None:
        presentation = await _seed(db_session)
        ai = FakeAIService(responses=[_ai_response(OUTLINE_JSON), _ai_response(
            '{"title": "V2", "topics": [{"title": "Only", "slide_ranges": [1, 6]}]}'
        )])
        service = _service(db_session, ai)
        await service.regenerate(presentation)
        result = await service.regenerate(presentation)
        assert result["title"] == "V2"
        assert len(result["topics"]) == 1

        repo_session = UnitOfWork(session=db_session)
        from app.repositories.topic_outline_repository import TopicOutlineRepository

        rows = await TopicOutlineRepository(repo_session.session).find(
            presentation_id=presentation.id
        )
        assert len(rows) == 1

    async def test_parse_failure_raises_validation_error(
        self, db_session: object
    ) -> None:
        presentation = await _seed(db_session)
        ai = FakeAIService(
            responses=[_ai_response("not json"), _ai_response("still not json")]
        )
        with pytest.raises(AppValidationError):
            await _service(db_session, ai).regenerate(presentation)
        assert len(ai.requests) == 2

    async def test_repairs_truncated_trailing_brace(self, db_session: object) -> None:
        presentation = await _seed(db_session)
        truncated = (
            '{"title": "Unit 2 Overview", "topics": ['
            '{"title": "Introduction", "slide_ranges": [1, 2]},'
            '{"title": "Core Concepts", "slide_ranges": [3, 4]},'
            '{"title": "Wrap Up", "slide_ranges": [5, 6]}'
        )
        ai = FakeAIService(responses=[_ai_response(truncated)])
        result = await _service(db_session, ai).regenerate(presentation)
        assert result["status"] == "succeeded"
        assert len(result["topics"]) == 3

    async def test_retries_with_compact_source_on_unparseable(
        self, db_session: object
    ) -> None:
        presentation = await _seed(db_session)
        ai = FakeAIService(
            responses=[
                _ai_response("not json"),
                _ai_response(
                    '{"title": "V2", "topics": [{"title": "Only", "slide_ranges": [1, 6]}]}'
                ),
            ]
        )
        result = await _service(db_session, ai).regenerate(presentation)
        assert result["title"] == "V2"
        assert len(ai.requests) == 2
        second_prompt = ai.requests[1].user_prompt
        assert "--- SOURCE CONTENT ---" in second_prompt
        assert "[1] Slide 1" in second_prompt


class TestParsePayload:
    async def test_fenced_json(self) -> None:
        from app.services.topic_outline_service import TopicOutlineService

        payload = TopicOutlineService._parse_payload(
            '```json\n{"title": "T", "topics": [{"title": "X", "slide_ranges": [1, 2]}]}\n```'
        )
        assert payload.title == "T"

    async def test_wrapped_outline_object(self) -> None:
        from app.services.topic_outline_service import TopicOutlineService

        payload = TopicOutlineService._parse_payload(
            '{"outline": {"title": "T", "topics": [{"title": "X", "slide_ranges": [1, 2]}]}}'
        )
        assert payload.title == "T"

    async def test_truncated_brace_repaired(self) -> None:
        from app.services.topic_outline_service import TopicOutlineService

        payload = TopicOutlineService._parse_payload(
            '{"title": "T", "topics": [{"title": "X", "slide_ranges": [1, 2]}'
        )
        assert payload.title == "T"
        assert len(payload.topics) == 1


class TestGetOutline:
    async def test_none_when_no_outline(self, db_session: object) -> None:
        presentation = await _seed(db_session)
        ai = FakeAIService(responses=[])
        result = await _service(db_session, ai).get_outline_data(presentation)
        assert result["status"] == "none"
        assert result["topics"] == []
        assert result["title"] is None

    async def test_stored_topics_none_and_values(self, db_session: object) -> None:
        presentation = await _seed(db_session)
        ai = FakeAIService(responses=[_ai_response(OUTLINE_JSON)])
        service = _service(db_session, ai)
        assert await service.get_stored_topics(presentation.id) is None

        await service.regenerate(presentation)
        stored = await service.get_stored_topics(presentation.id)
        assert stored is not None
        assert len(stored) == 3
        assert stored[0] == {"title": "Introduction", "slide_ranges": [1, 2]}


class TestSchema:
    async def test_payload_requires_topics(self) -> None:
        from pydantic import ValidationError

        from app.schemas.topic_outline import TopicOutlinePayload

        with pytest.raises(ValidationError):
            TopicOutlinePayload.model_validate_json('{"title": "T", "topics": []}')

    async def test_payload_rejects_bad_ranges(self) -> None:
        from pydantic import ValidationError

        from app.schemas.topic_outline import TopicOutlinePayload

        with pytest.raises(ValidationError):
            TopicOutlinePayload.model_validate_json(
                '{"title": "T", "topics": [{"title": "X", "slide_ranges": [0, 3]}]}'
            )
        with pytest.raises(ValidationError):
            TopicOutlinePayload.model_validate_json(
                '{"title": "T", "topics": [{"title": "X", "slide_ranges": [4, 2]}]}'
            )
