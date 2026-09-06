"""Learner-owned video project persistence (P16).

Backs the asynchronous, persistent video rendering runtime: a project blueprint
is composed synchronously and stored here, then a render job (inline executor or
Celery task) mutates ``status``/``progress_percentage`` until it reaches a
terminal ``ready`` or ``failed`` state. The row is the single source of truth for
ownership (``user_id``, FK CASCADE), so cross-user access resolves to the same
404 as an unknown project.

Learnability/ownership rules:
  - Every row is learner-owned (``user_id``, FK CASCADE).
  - ``video_id`` is the stable engine identifier (``video_<hex>``) and the name
    of the rendered binary under ``uploads/videos``.
  - ``project_data`` holds the ``VideoProject.model_dump(mode="json")`` blueprint
    so a re-render is deterministic (no regeneration drift).
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Float, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.database.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.user import User

PUBLIC_ID_PREFIX = "vproj_"


class VideoRenderStatus:
    QUEUED = "queued"
    RENDERING = "rendering"
    READY = "ready"
    FAILED = "failed"

    TERMINAL = {READY, FAILED}
    ACTIVE = {QUEUED, RENDERING}
    ACTIVE_STATUSES = ACTIVE


def generate_video_project_public_id() -> str:
    return f"{PUBLIC_ID_PREFIX}{uuid.uuid4().hex[:16]}"


class VideoProjectRecord(Base, UUIDMixin, TimestampMixin):
    """A learner-owned video project with its render lifecycle state."""

    __tablename__ = "video_projects"

    public_id: Mapped[str] = mapped_column(
        String(40),
        unique=True,
        nullable=False,
        index=True,
        default=generate_video_project_public_id,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    video_id: Mapped[str] = mapped_column(String(64), nullable=False)
    topic: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=VideoRenderStatus.QUEUED)
    progress_percentage: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    playable_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    error: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    project_data: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=True
    )

    user: Mapped[User | None] = relationship(
        "User", foreign_keys=[user_id], lazy="select"
    )

    __table_args__ = (
        Index("ix_video_projects_user_status", "user_id", "status"),
    )
