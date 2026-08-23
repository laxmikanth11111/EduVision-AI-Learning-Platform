"""API schemas for the AI learning assistant (Phase 4D.6)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

# ── Request models ───────────────────────────────────────────────────────────


class SessionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lesson_id: str | None = Field(default=None, max_length=40)
    title: str = Field(default="AI Assistant", min_length=1, max_length=500)
    slide_position: int = Field(default=0, ge=0, le=100000)
    block_position: int = Field(default=0, ge=0, le=100000)


class ConversationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str | None = Field(default=None, max_length=40)
    lesson_id: str | None = Field(default=None, max_length=40)
    title: str | None = Field(default=None, max_length=500)
    slide_position: int | None = Field(default=None, ge=0, le=100000)
    block_position: int | None = Field(default=None, ge=0, le=100000)


class MessageSendRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=4000)
    client_message_id: str | None = Field(default=None, max_length=64)


class ConversationSummarizeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation_id: str = Field(min_length=1, max_length=40)


# ── Response models ──────────────────────────────────────────────────────────


class AssistantSessionResponse(BaseModel):
    id: str
    lesson_id: str | None = None
    title: str
    status: str
    slide_position: int = 0
    block_position: int = 0
    context_version: str = "1"
    last_message_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class AssistantConversationResponse(BaseModel):
    id: str
    session_id: str | None = None
    lesson_id: str | None = None
    title: str | None = None
    status: str
    slide_position: int = 0
    block_position: int = 0
    context_version: str = "1"
    message_count: int = 0
    summary: str | None = None
    summary_created_at: datetime | None = None
    last_message_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class AssistantMessageResponse(BaseModel):
    id: str
    role: str
    content: str
    status: str
    client_message_id: str | None = None
    model: str | None = None
    provider: str | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0
    error: str | None = None
    created_at: datetime
    updated_at: datetime


class AssistantExchangeResponse(BaseModel):
    user_message: AssistantMessageResponse | None = None
    assistant_message: AssistantMessageResponse | None = None
    prompt_hash: str | None = None
    conversation_id: str | None = None


class AssistantSummaryResponse(BaseModel):
    conversation_id: str
    summary: str | None = None
    dispatched: bool = False
