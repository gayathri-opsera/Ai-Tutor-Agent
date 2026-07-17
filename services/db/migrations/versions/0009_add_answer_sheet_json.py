"""Add answer_sheet_json column to assessments and local_assessments tables.

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-17

answer_sheet_json stores structured answer key data per question:
  [{ "question_id": str, "correct_answer": str, "explanation": str,
     "difficulty": str, "points": int }]
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Production assessments table
    op.add_column(
        "assessments",
        sa.Column("answer_sheet_json", JSONB, nullable=True),
    )
    # Local dev assessments table (mirrors production for local testing)
    op.execute(
        """
        ALTER TABLE local_assessments
        ADD COLUMN IF NOT EXISTS answer_sheet_json JSONB
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE local_assessments DROP COLUMN IF EXISTS answer_sheet_json")
    op.drop_column("assessments", "answer_sheet_json")
