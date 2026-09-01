"""EffectivenessAssessment model — tracks pre/post/retention assessment pairs and learning gain."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.database.base import Base, TimestampMixin, UUIDMixin
from app.database.types import PortableJSONB

PUBLIC_ID_PREFIX = "eass_"


def generate_assessment_public_id() -> str:
    return f"{PUBLIC_ID_PREFIX}{uuid.uuid4().hex[:16]}"


class EffectivenessAssessment(Base, UUIDMixin, TimestampMixin):
    """Pairs baseline, post, and retention assessments for a user+presentation.

    Stores scores, concept-level breakdowns, and computed learning gain.
    """

    __tablename__ = "effectiveness_assessments"

    public_id: Mapped[str] = mapped_column(
        String(40), unique=True, nullable=False, index=True,
        default=generate_assessment_public_id,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    presentation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("presentations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    experiment_group: Mapped[str | None] = mapped_column(String(50), nullable=True)

    baseline_quiz_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True,
    )
    baseline_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    baseline_concept_scores: Mapped[dict[str, Any] | None] = mapped_column(
        PortableJSONB, nullable=True,
    )

    post_quiz_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True,
    )
    post_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    post_concept_scores: Mapped[dict[str, Any] | None] = mapped_column(
        PortableJSONB, nullable=True,
    )

    retention_quiz_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True,
    )
    retention_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    retention_concept_scores: Mapped[dict[str, Any] | None] = mapped_column(
        PortableJSONB, nullable=True,
    )
    retention_delay_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)

    absolute_gain: Mapped[float | None] = mapped_column(Float, nullable=True)
    normalized_gain: Mapped[float | None] = mapped_column(Float, nullable=True)
    retention_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    retention_pct: Mapped[float | None] = mapped_column(Float, nullable=True)

    total_learning_time_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    events_summary: Mapped[dict[str, Any] | None] = mapped_column(
        PortableJSONB, nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="in_progress",
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    __table_args__ = (
        Index("ix_effectiveness_user_presentation", "user_id", "presentation_id"),
        Index("ix_effectiveness_status", "status"),
    )
