from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Float, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.database.base import Base, TimestampMixin, UUIDMixin

PUBLIC_ID_PREFIX = "anl_"


def generate_analytics_public_id() -> str:
    return f"{PUBLIC_ID_PREFIX}{uuid.uuid4().hex[:16]}"


class LearningAnalyticsSnapshot(Base, UUIDMixin, TimestampMixin):
    """Aggregate snapshot of learner progress, quiz performance, and study engagement."""

    __tablename__ = "learning_analytics_snapshots"

    public_id: Mapped[str] = mapped_column(
        String(40),
        unique=True,
        nullable=False,
        index=True,
        default=generate_analytics_public_id,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        index=True,
    )
    lessons_completed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lessons_in_progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    quiz_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_quiz_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    study_streak_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_study_time_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    overall_completion_percentage: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    bookmarks_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    notes_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tutor_sessions_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    exports_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    snapshot_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    __table_args__ = (
        Index("ix_learning_analytics_user_date", "user_id", "snapshot_date"),
    )


class CreatorAnalyticsSnapshot(Base, UUIDMixin, TimestampMixin):
    """Aggregate creator metrics for engagement, difficult topics, and analytics."""

    __tablename__ = "creator_analytics_snapshots"

    public_id: Mapped[str] = mapped_column(
        String(40),
        unique=True,
        nullable=False,
        index=True,
        default=generate_analytics_public_id,
    )
    creator_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        index=True,
    )
    total_learners: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active_learners: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    presentation_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_learner_quiz_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    overall_engagement_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    difficult_topics: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    snapshot_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )


StudentAnalyticsSnapshot = LearningAnalyticsSnapshot  # backward compat alias
TeacherAnalyticsSnapshot = CreatorAnalyticsSnapshot  # backward compat alias


class SystemAnalytics(Base, UUIDMixin, TimestampMixin):
    """System-wide operational metrics for API volume, AI usage, storage, and jobs."""

    __tablename__ = "system_analytics"

    public_id: Mapped[str] = mapped_column(
        String(40),
        unique=True,
        nullable=False,
        index=True,
        default=generate_analytics_public_id,
    )
    total_api_requests: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_ai_requests: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_exports_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_processing_jobs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    storage_used_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    redis_keys_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    celery_jobs_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_documents_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
