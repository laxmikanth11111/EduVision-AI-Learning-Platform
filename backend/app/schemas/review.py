"""P10 review-schedule API schemas.

The adaptive review engine exposes a learner-scoped, time-aware review queue
built deterministically from mastery state. Every payload is owned by the
authenticated learner; concepts/lessons are resolved through the existing
ownership chain (404-equalized).
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, Field


class ReviewOutcome(str, Enum):
    """Controlled self-reported recall outcome vocabulary (P14).

    ``good`` is the default so legacy callers keep today's exact behavior.
    """

    again = "again"
    hard = "hard"
    good = "good"
    easy = "easy"


class ReviewCompleteIn(BaseModel):
    """Optional request body for a review completion (P14).

    An absent/empty body is fully backward compatible and behaves exactly as
    today: the learner performed a plain successful review (``good``).
    """

    outcome: ReviewOutcome = ReviewOutcome.good


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
    # P14 retention enrichments (additive; may be "new" / None for legacy rows).
    retention_status: str = "new"
    review_accuracy: float | None = None


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
    # P14: echoed outcome + the updated retention signal for this concept.
    outcome: str = "good"
    retained_strength: float | None = None
    review_accuracy: float | None = None
