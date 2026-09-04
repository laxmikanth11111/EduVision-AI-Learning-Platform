"""P10 review-schedule API schemas.

The adaptive review engine exposes a learner-scoped, time-aware review queue
built deterministically from mastery state. Every payload is owned by the
authenticated learner; concepts/lessons are resolved through the existing
ownership chain (404-equalized).
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class ReviewQueueItem(BaseModel):
    """A single concept due (or upcoming) for review."""

    schedule_id: str
    concept_id: str
    concept_name: str = ""
    lesson_id: str | None = None
    mastery_score: float | None = None
    status: str = "scheduled"
    interval_days: int = 1
    due_at: datetime | None = None
    last_reviewed_at: datetime | None = None
    scheduled_date: date | None = None
    review_count: int = 0
    priority: str = "medium"


class ReviewQueueResponse(BaseModel):
    """Bounded list of review items due now (or upcoming)."""

    items: list[ReviewQueueItem] = Field(default_factory=list)
    total: int = 0
    due_count: int = 0


class ReviewCompleteResponse(BaseModel):
    """Result of marking a concept review complete."""

    schedule_id: str
    concept_id: str
    concept_name: str = ""
    status: str = "completed"
    next_due_at: datetime | None = None
    next_interval_days: int = 1
    mastery_score: float | None = None
