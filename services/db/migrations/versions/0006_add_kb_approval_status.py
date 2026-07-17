"""Add approval_status and ai_overview columns to knowledge_bases table.

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-17
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

kb_approval_enum = ENUM(
    "pending_review",
    "approved",
    "rejected",
    "clarification_requested",
    name="kb_approval_status_enum",
    create_type=True,
)


def upgrade() -> None:
    kb_approval_enum.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "knowledge_bases",
        sa.Column(
            "approval_status",
            kb_approval_enum,
            nullable=False,
            server_default="pending_review",
        ),
    )
    op.add_column(
        "knowledge_bases",
        sa.Column("ai_overview", sa.Text, nullable=True),
    )
    op.add_column(
        "knowledge_bases",
        sa.Column("rejection_reason", sa.Text, nullable=True),
    )
    op.add_column(
        "knowledge_bases",
        sa.Column("clarification_message", sa.Text, nullable=True),
    )
    # Courses that already existed before this migration are auto-approved.
    op.execute(
        "UPDATE knowledge_bases SET approval_status = 'approved' "
        "WHERE created_at < NOW()"
    )
    op.create_index(
        "ix_knowledge_bases_approval_status",
        "knowledge_bases",
        ["approval_status"],
    )


def downgrade() -> None:
    op.drop_index("ix_knowledge_bases_approval_status", table_name="knowledge_bases")
    op.drop_column("knowledge_bases", "clarification_message")
    op.drop_column("knowledge_bases", "rejection_reason")
    op.drop_column("knowledge_bases", "ai_overview")
    op.drop_column("knowledge_bases", "approval_status")
    kb_approval_enum.drop(op.get_bind(), checkfirst=True)
