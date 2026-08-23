from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, model_validator

from shared.constants import (
    LearningMode,
    LessonDifficulty,
    LessonRetryState,
    LessonStatus,
    LessonVersionStatus,
)


class LessonGenerationRequest(BaseModel):
    mode: LearningMode
    title: str | None = Field(default=None, max_length=500)
    language: str | None = Field(default=None, max_length=10)
    difficulty: LessonDifficulty | None = None
    model: str | None = Field(default=None, max_length=100)
    target_units: list[str] | None = Field(
        default=None, max_length=100, description="Optional subset of content unit public ids"
    )


class GeneratedBlockResponse(BaseModel):
    id: str
    position: int
    topic: str
    description: str


class UsageSummary(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    estimated_cost: Decimal | None = None
    currency: str | None = None
    latency_ms: float | None = None
    retry_count: int = 0


class QualitySummary(BaseModel):
    score: float | None = None
    issues: list[dict[str, Any]] = Field(default_factory=list)
    checked_at: datetime | None = None
    version: str | None = None


class GeneratedVersionResponse(BaseModel):
    id: str
    version: int
    status: LessonVersionStatus
    title: str | None = None
    summary: str | None = None
    language: str | None = None
    difficulty: LessonDifficulty | None = None
    provider: str | None = None
    model: str | None = None
    prompt_version: str | None = None
    payload_schema_version: str | None = None
    generation_metadata: dict[str, Any] = Field(default_factory=dict)
    usage: UsageSummary = Field(default_factory=UsageSummary)
    error_code: str | None = None
    error_message: str | None = None
    quality: QualitySummary = Field(default_factory=QualitySummary)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime


class GeneratedVersionDetailResponse(GeneratedVersionResponse):
    blocks: list[GeneratedBlockResponse] = Field(default_factory=list)


class GeneratedLessonSummary(BaseModel):
    id: str
    presentation_id: str
    mode: LearningMode
    status: LessonStatus
    title: str | None = None
    language: str | None = None
    difficulty: LessonDifficulty | None = None
    model_override: str | None = None
    latest_version: int = 0
    retry_state: LessonRetryState = LessonRetryState.NONE
    duplicate: bool = False
    created_at: datetime
    updated_at: datetime


class GeneratedLessonResponse(GeneratedLessonSummary):
    attempt_count: int = 0
    max_attempts: int = 3
    next_retry_at: datetime | None = None
    version: GeneratedVersionDetailResponse | None = None


class GeneratedLessonStatusResponse(BaseModel):
    id: str
    presentation_id: str
    status: LessonStatus
    retry_state: LessonRetryState = LessonRetryState.NONE
    attempt_count: int = 0
    max_attempts: int = 3
    next_retry_at: datetime | None = None
    error_code: str | None = None
    error_message: str | None = None
    latest_version: int = 0
    duplicate: bool = False


# ── AI response payload (parsed from provider JSON output) ───────────────────


class LessonBlockPayload(BaseModel):
    topic: str = Field(min_length=1, max_length=500, description="Topic title from the outline")
    description: str = Field(min_length=1, description="Clear, well-structured description of this topic")


class LessonPayload(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    summary: str | None = None
    language: str | None = Field(default=None, max_length=10)
    difficulty: LessonDifficulty | None = None
    topics: list[LessonBlockPayload] = Field(default_factory=list)

    @model_validator(mode="after")
    def _require_topics(self) -> LessonPayload:
        if not self.topics:
            raise ValueError("lesson payload must contain at least one topic description")
        return self

    def payload_hash(self) -> str:
        import hashlib

        raw = self.model_dump_json(exclude_none=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()
