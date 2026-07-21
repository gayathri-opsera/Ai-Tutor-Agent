"""Add content_text column to documents table.

Revision ID: 0013
Revises: 0012
Create Date: 2026-07-20

The content-ingestion service stores extracted plain-text from uploaded
files (PDF, DOCX, video transcripts, etc.) directly on the documents row
so it can be served quickly without re-reading from object storage.
"""

from alembic import op
import sqlalchemy as sa

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # content_text holds extracted plain-text from ingested documents.
    # Nullable — text may not be available for all content types (e.g. pure binary).
    op.add_column(
        "documents",
        sa.Column("content_text", sa.Text, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("documents", "content_text")
