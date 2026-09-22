"""SQLAlchemy 2.0 Models for Checkpoint C4 — Topic-Level Animation Assets.

C4 extends the C3 topic visual asset model with deterministic educational
animation packages: a specification (scenes, steps, captions, interactions,
durations), a rendered package (self-contained HTML/SVG/CSS/JS), provenance,
and lifecycle state, all owner-scoped and fingerprinted for deduplication.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import JSON, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.database.base import Base, SoftDeleteMixin, TimestampMixin, UUIDMixin


def generate_animation_asset_public_id() -> str:
    return f"c4a_{uuid.uuid4().hex[:16]}"


class TopicAnimationAsset(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    """A generated animation asset associated with a topic/subtopic."""

    __tablename__ = "topic_animation_assets"

    public_id: Mapped[str] = mapped_column(
        String(40),
        unique=True,
        nullable=False,
        index=True,
        default=generate_animation_asset_public_id,
    )
    presentation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("presentations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        index=True,
    )
    topic_id: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    topic_title: Mapped[str] = mapped_column(String(500), nullable=False)
    subtopic_id: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    subtopic_title: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Animation specification and lifecycle
    animation_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="planned", index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # Generated package
    asset_format: Mapped[str] = mapped_column(String(16), nullable=False, default="html")
    asset_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    asset_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    package_content: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Educational content
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False, default="")
    learning_objective: Mapped[str] = mapped_column(Text, nullable=False, default="")
    provenance: Mapped[str] = mapped_column(String(32), nullable=False, default="ai_explained")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.8)

    # Structured JSON fields
    specification: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=False,
        default=dict,
    )
    explanation: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=False,
        default=dict,
    )
    source_references: Mapped[list[Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=False,
        default=list,
    )
    concept_ids: Mapped[list[Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=False,
        default=list,
    )
    generation_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=False,
        default=dict,
    )

    # Error handling
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        Index("ix_topic_animation_assets_pres_topic", "presentation_id", "topic_id"),
        Index("ix_topic_animation_assets_pres_subtopic", "presentation_id", "subtopic_id"),
        Index("ix_topic_animation_assets_status_version", "status", "version"),
    )
