"""Add animation_usefulness to user_feedback and retention to comparison.

Revision ID: 0024_p3_feedback_and_comparison
Revises: 0023_learning_effectiveness
Create Date: 2026-08-20 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0024_p3_feedback_and_comparison"
down_revision = "0023_learning_effectiveness"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # ── user_feedback: add animation_usefulness column ───────────────────
    fb_cols = {c["name"] for c in inspector.get_columns("user_feedback")}
    if "animation_usefulness" not in fb_cols:
        op.add_column(
            "user_feedback",
            sa.Column("animation_usefulness", sa.Integer(), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    fb_cols = {c["name"] for c in inspector.get_columns("user_feedback")}
    if "animation_usefulness" in fb_cols:
        op.drop_column("user_feedback", "animation_usefulness")
