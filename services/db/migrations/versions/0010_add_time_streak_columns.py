"""Add time_on_platform and streak tracking columns to learner profiles.

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-17

Adds four columns used by the Learner Dashboard aggregation API (WO-247):
  - time_on_platform_minutes  INTEGER NOT NULL DEFAULT 0
  - current_streak_days       INTEGER NOT NULL DEFAULT 0
  - longest_streak_days       INTEGER NOT NULL DEFAULT 0
  - last_active_date          DATE    NULL
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "local_learner_profiles",
        sa.Column(
            "time_on_platform_minutes",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )
    op.add_column(
        "local_learner_profiles",
        sa.Column(
            "current_streak_days",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )
    op.add_column(
        "local_learner_profiles",
        sa.Column(
            "longest_streak_days",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )
    op.add_column(
        "local_learner_profiles",
        sa.Column(
            "last_active_date",
            sa.Date(),
            nullable=True,
        ),
    )

    # Production table (learner_profiles) mirrors local
    for col_sql in [
        "ADD COLUMN IF NOT EXISTS time_on_platform_minutes INTEGER NOT NULL DEFAULT 0",
        "ADD COLUMN IF NOT EXISTS current_streak_days INTEGER NOT NULL DEFAULT 0",
        "ADD COLUMN IF NOT EXISTS longest_streak_days INTEGER NOT NULL DEFAULT 0",
        "ADD COLUMN IF NOT EXISTS last_active_date DATE",
    ]:
        op.execute(f"ALTER TABLE learner_profiles {col_sql}")


def downgrade() -> None:
    for col in ("last_active_date", "longest_streak_days",
                "current_streak_days", "time_on_platform_minutes"):
        op.drop_column("local_learner_profiles", col)
        op.execute(f"ALTER TABLE learner_profiles DROP COLUMN IF EXISTS {col}")
