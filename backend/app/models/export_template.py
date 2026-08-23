from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDMixin
from shared.constants import ExportFormat, ExportKind

PUBLIC_ID_PREFIX = "exptpl_"


def generate_export_template_public_id() -> str:
    return f"{PUBLIC_ID_PREFIX}{uuid.uuid4().hex[:16]}"


class ExportTemplate(Base, UUIDMixin, TimestampMixin):
    """Layout, CSS, and styling configuration templates for generated exports."""

    __tablename__ = "export_templates"

    public_id: Mapped[str] = mapped_column(
        String(40),
        unique=True,
        nullable=False,
        index=True,
        default=generate_export_template_public_id,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    template_key: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    kind: Mapped[str] = mapped_column(String(30), nullable=False, default=ExportKind.NOTES.value)
    format: Mapped[str] = mapped_column(String(20), nullable=False, default=ExportFormat.PDF.value)
    css_styles: Mapped[str | None] = mapped_column(Text, nullable=True)
    header_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    footer_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    config_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=True
    )
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    __table_args__ = (
        Index("ix_export_templates_kind_format", "kind", "format"),
    )
