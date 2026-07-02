"""Add pending_review to document_status_enum for low-quality transcription flagging.

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-02
"""
from __future__ import annotations

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE is not transactional in PostgreSQL, so it must run
    # outside a transaction block. Alembic's op.execute handles this fine for DDL.
    op.execute("ALTER TYPE document_status_enum ADD VALUE IF NOT EXISTS 'pending_review'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values; downgrade is a no-op.
    pass
