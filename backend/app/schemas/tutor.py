"""API schemas for the Mastery-Aware AI Tutor (P8)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# ── Request models ───────────────────────────────────────────────────────────


class TutorSessionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lesson_id: str | None = Field(default=None, max_length=40)
    presentation_id: str | None = Field(default=None, max_length=40)
    target_concept_id: str | None = Field(default=None, max_length=40)
    title: str = Field(default="AI Tutor", min_length=1, max_length=500)
    mode: str = Field(default="interactive", min_length=1, max_length=30)
    difficulty: str | None = Field(default=None, max_length=20)
    language: str | None = Field(default=None, max_length=10)


class TutorMessageSendRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=4000)
    client_message_id: str | None = Field(default=None, max_length=64)


class TutorRemediateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_concept_id: str = Field(min_length=1, max_length=40)
    lesson_id: str | None = Field(default=None, max_length=40)


# ── Response models ──────────────────────────────────────────────────────────


class TutorSessionResponse(BaseModel):
    id: str
    lesson_id: str | None = None
    presentation_id: str | None = None
    target_concept_id: str | None = None
    title: str
    status: str
    mode: str = "interactive"
    difficulty: str | None = None
    language: str | None = None
    context_version: str = "1"
    message_count: int = 0
    last_message_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class TutorMessageResponse(BaseModel):
    id: str
    role: str
    content: str
    status: str
    source_kind: str | None = None
    attribution: str | None = None
    confidence: str | None = None
    model: str | None = None
    provider: str | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0
    created_at: datetime
    updated_at: datetime


class TutorExchangeResponse(BaseModel):
    user_message: TutorMessageResponse | None = None
    assistant_message: TutorMessageResponse | None = None
    conversation_id: str | None = None


class TutorRemediateResponse(BaseModel):
    target_concept_id: str
    target_concept_name: str
    mastery_score: float | None = None
    source_kind: str
    attribution: str | None = None
    confidence: str | None = None
    response: str
    session_id: str | None = None
    conversation_id: str | None = None
    message_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
