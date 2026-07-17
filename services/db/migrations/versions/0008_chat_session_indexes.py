"""Add partial index on chat_sessions.created_at for 7-day purge optimization.

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-17
"""
from __future__ import annotations

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Partial index speeds up the nightly purge CronJob
    # which deletes sessions older than 7 days.
    op.execute(
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_chat_sessions_created_at_active
        ON chat_sessions (created_at)
        WHERE is_active = true
        """
    )
    # Also add user_id index if not present — needed for ownership scoping.
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_chat_sessions_user_id
        ON chat_sessions (user_id)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_chat_sessions_created_at_active")
    op.execute("DROP INDEX IF EXISTS ix_chat_sessions_user_id")
