"""Add content_hash and updated_at to document_chunks for dedup and watermark sync.

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-17

- content_hash   TEXT NULL  — SHA-256 of chunk_text for deduplication (WO-263)
- updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()  — used by watermark delta sync (WO-262)
- unique constraint on (document_id, chunk_index) for ON CONFLICT upsert
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # document_chunks table (production) — use IF NOT EXISTS to be idempotent
    op.execute(
        "ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS content_hash TEXT"
    )
    op.execute(
        "ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS "
        "updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL"
    )
    # Create unique constraint for dedup upsert ON CONFLICT (document_id, chunk_index)
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'uq_document_chunks_doc_idx'
            ) THEN
                ALTER TABLE document_chunks
                ADD CONSTRAINT uq_document_chunks_doc_idx
                UNIQUE (document_id, chunk_index);
            END IF;
        END $$;
        """
    )
    # Mirror on local dev table (may not exist in all environments)
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'local_document_chunks') THEN
                ALTER TABLE local_document_chunks
                ADD COLUMN IF NOT EXISTS content_hash TEXT,
                ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();
            END IF;
        END $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'local_document_chunks') THEN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint
                    WHERE conname = 'uq_local_document_chunks_doc_idx'
                ) THEN
                    ALTER TABLE local_document_chunks
                    ADD CONSTRAINT uq_local_document_chunks_doc_idx
                    UNIQUE (document_id, chunk_index);
                END IF;
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE local_document_chunks DROP CONSTRAINT IF EXISTS uq_local_document_chunks_doc_idx")
    op.execute("ALTER TABLE local_document_chunks DROP COLUMN IF EXISTS content_hash, DROP COLUMN IF EXISTS updated_at")
    op.execute("ALTER TABLE document_chunks DROP CONSTRAINT IF EXISTS uq_document_chunks_doc_idx")
    op.drop_column("document_chunks", "updated_at")
    op.drop_column("document_chunks", "content_hash")
