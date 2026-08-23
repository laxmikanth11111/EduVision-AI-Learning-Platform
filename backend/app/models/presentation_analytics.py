from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.database.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.presentation import Presentation


class PresentationAnalytics(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "presentation_analytics"

    presentation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("presentations.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    view_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unique_viewers: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    quiz_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    publish_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    learning_sessions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_quiz_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    completion_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_viewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    presentation: Mapped[Presentation] = relationship("Presentation", back_populates="analytics")
