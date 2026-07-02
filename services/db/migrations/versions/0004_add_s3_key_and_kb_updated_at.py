"""Add s3_key to documents and updated_at to knowledge_bases.

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-02
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE documents
        ADD COLUMN IF NOT EXISTS s3_key TEXT
    """)
    op.execute("""
        ALTER TABLE knowledge_bases
        ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT now()
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS s3_key")
    op.execute("ALTER TABLE knowledge_bases DROP COLUMN IF EXISTS updated_at")
