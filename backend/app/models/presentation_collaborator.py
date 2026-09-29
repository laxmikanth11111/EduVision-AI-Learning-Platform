"""Presentation collaborators.

The ``presentation_collaborators`` table has existed since migration
``0001_initial`` (with ``ON DELETE CASCADE`` foreign keys to both
``presentations`` and ``users``, plus a ``(presentation_id, user_id)`` unique
constraint), but the ORM mapping was never written. That left the table
unreachable through the ORM and made two call sites import a module that did
not exist:

* ``PresentationRepository.list_viewable_for_user`` -- the import is inside the
  function body, so it never failed at application startup; it would have
  raised ``ModuleNotFoundError`` the first time anyone called the method.
* ``scripts/seed_manual_test.py`` -- a top-level import, so the script could not
  be run at all.

This model mirrors the migration schema exactly so that
``metadata.create_all`` (used by the SQLite test suites) and the real migration
lineage agree.
"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.database.base import Base, TimestampMixin, UUIDMixin


class PresentationCollaborator(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "presentation_collaborators"

    presentation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("presentations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Mirrors shared.constants.CollaboratorRole (owner/editor/viewer). Stored as
    # a plain string so the column stays varchar(20) exactly as migration 0001
    # created it, rather than depending on an enum type that the database does
    # not have.
    role: Mapped[str] = mapped_column(String(20), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "presentation_id",
            "user_id",
            name="uq_presentation_collaborators_pres_user",
        ),
    )
