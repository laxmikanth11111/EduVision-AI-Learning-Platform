"""Normalized AI request / response models.

Every provider must accept an ``AIRequest`` and return an ``AIResponse`` using
exactly these shapes, so upper layers never perform provider-specific parsing.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.utils.uuid_helpers import new_uuid

DEFAULT_PROVIDER_TYPE = "gemini"
DEFAULT_MODEL = "gemini-1.5-flash"


class AIProviderType(str, Enum):
    GEMINI = "gemini"
    OPENAI = "openai"
    LOCAL = "local"


class AIResponseFormat(str, Enum):
    TEXT = "text"
    JSON = "json"
    MARKDOWN = "markdown"


class FinishReason(str, Enum):
    STOP = "stop"
    LENGTH = "length"
    CONTENT_FILTER = "content_filter"
    ERROR = "error"
    OTHER = "other"


RoleName = Literal["system", "user", "assistant", "model"]


class AIMessage(BaseModel):
    """A single chat message part of the normalized conversation."""

    role: RoleName
    content: str

    @field_validator("content")
    @classmethod
    def _content_not_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("message content must not be empty")
        return value


class TokenUsage(BaseModel):
    """Token accounting for a single provider call."""

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    estimated_cost: Decimal | None = Field(default=None, ge=0)
    currency: str = "USD"
    provider: str | None = None
    model: str | None = None
    latency_ms: float | None = Field(default=None, ge=0)
    retry_count: int = Field(default=0, ge=0)
    finish_reason: FinishReason | None = None

    @model_validator(mode="after")
    def _compute_total(self) -> TokenUsage:
        if self.total_tokens <= 0:
            self.total_tokens = self.input_tokens + self.output_tokens
        return self


class AIRequest(BaseModel):
    """Normalized request accepted by every provider implementation."""

    user_prompt: str = Field(min_length=1)
    system_prompt: str | None = None
    messages: list[AIMessage] | None = None
    temperature: float | None = Field(default=None, ge=0, le=2)
    top_p: float | None = Field(default=None, ge=0, le=1)
    max_tokens: int | None = Field(default=None, gt=0)
    stop_sequences: list[str] = Field(default_factory=list)
    response_format: AIResponseFormat = AIResponseFormat.TEXT
    language: str | None = None
    difficulty: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    model_override: str | None = None
    request_id: str | None = None
    correlation_id: str | None = None

    @field_validator("user_prompt")
    @classmethod
    def _prompt_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("user_prompt must not be blank")
        return value

    @model_validator(mode="after")
    def _ensure_request_id(self) -> AIRequest:
        if not self.request_id:
            self.request_id = f"ai_{new_uuid().hex}"
        return self

    @property
    def effective_messages(self) -> list[AIMessage]:
        """Conversation (system + history + current user prompt) for chat APIs."""
        conversation: list[AIMessage] = []
        if self.system_prompt:
            conversation.append(AIMessage(role="system", content=self.system_prompt))
        if self.messages:
            conversation.extend(self.messages)
        conversation.append(AIMessage(role="user", content=self.user_prompt))
        return conversation


class AIResponse(BaseModel):
    """Normalized response returned by every provider implementation."""

    text: str
    finish_reason: FinishReason = FinishReason.STOP
    usage: TokenUsage
    provider: str
    model: str
    latency_ms: float = Field(default=0, ge=0)
    retry_count: int = Field(default=0, ge=0)
    request_id: str = ""
    correlation_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def success(self) -> bool:
        return self.finish_reason in {FinishReason.STOP, FinishReason.LENGTH}
