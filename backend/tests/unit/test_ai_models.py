from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.ai.models import AIMessage, AIRequest, AIResponse, FinishReason, TokenUsage


class TestAIRequest:
    def test_request_id_auto_generated(self) -> None:
        request = AIRequest(user_prompt="hello")
        assert request.request_id is not None
        assert request.request_id.startswith("ai_")

    def test_request_id_preserved_when_provided(self) -> None:
        request = AIRequest(user_prompt="hello", request_id="custom-id")
        assert request.request_id == "custom-id"

    def test_blank_user_prompt_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AIRequest(user_prompt="   ")

    def test_effective_messages_with_system_and_history(self) -> None:
        request = AIRequest(
            user_prompt="final",
            system_prompt="be nice",
            messages=[
                AIMessage(role="user", content="first"),
                AIMessage(role="assistant", content="reply"),
            ],
        )
        messages = request.effective_messages
        assert [(m.role, m.content) for m in messages] == [
            ("system", "be nice"),
            ("user", "first"),
            ("assistant", "reply"),
            ("user", "final"),
        ]

    def test_effective_messages_without_system(self) -> None:
        request = AIRequest(user_prompt="final")
        assert [(m.role, m.content) for m in request.effective_messages] == [
            ("user", "final")
        ]


class TestAIMessage:
    def test_empty_content_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AIMessage(role="user", content="   ")


class TestTokenUsage:
    def test_total_computed_when_zero(self) -> None:
        usage = TokenUsage(input_tokens=10, output_tokens=5)
        assert usage.total_tokens == 15

    def test_total_preserved_when_set(self) -> None:
        usage = TokenUsage(input_tokens=10, output_tokens=5, total_tokens=100)
        assert usage.total_tokens == 100


class TestAIResponse:
    @pytest.mark.parametrize(
        ("finish_reason", "expected"),
        [
            (FinishReason.STOP, True),
            (FinishReason.LENGTH, True),
            (FinishReason.CONTENT_FILTER, False),
            (FinishReason.ERROR, False),
            (FinishReason.OTHER, False),
        ],
    )
    def test_success_flag(self, finish_reason: FinishReason, expected: bool) -> None:
        response = AIResponse(
            text="x",
            finish_reason=finish_reason,
            usage=TokenUsage(),
            provider="local",
            model="local-mock-1",
        )
        assert response.success is expected
