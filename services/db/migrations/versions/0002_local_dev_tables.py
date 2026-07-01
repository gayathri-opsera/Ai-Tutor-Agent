"""Local dev persistence tables — no FK dependency on users table.

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-01
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Simplified learner profiles for local dev (no FK to users)
    op.create_table(
        "local_learner_profiles",
        sa.Column("user_id", sa.Text, primary_key=True),
        sa.Column("display_name", sa.Text, server_default=""),
        sa.Column("proficiency_level", sa.Text, server_default="beginner"),
        sa.Column("preferences", JSONB, server_default="{}"),
        sa.Column("total_sessions", sa.Integer, server_default="0"),
        sa.Column("total_queries", sa.Integer, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "local_topic_progress",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("user_id", sa.Text, sa.ForeignKey("local_learner_profiles.user_id", ondelete="CASCADE"), nullable=False),
        sa.Column("topic", sa.Text, nullable=False),
        sa.Column("knowledge_base_id", sa.Text),
        sa.Column("status", sa.Text, server_default="not_started"),
        sa.Column("score", sa.Float, server_default="0.0"),
        sa.Column("question_count", sa.Integer, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_local_topic_user", "local_topic_progress", ["user_id"])
    op.create_index("ix_local_topic_user_topic", "local_topic_progress", ["user_id", "topic"], unique=True)

    # Simplified assessments for local dev
    op.create_table(
        "local_assessments",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("knowledge_base_id", sa.Text, server_default=""),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("assessment_type", sa.Text, server_default="pre"),
        sa.Column("questions_json", JSONB, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_local_assessments_kb", "local_assessments", ["knowledge_base_id"])

    op.create_table(
        "local_assessment_results",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("assessment_id", sa.Text, sa.ForeignKey("local_assessments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Text, nullable=False),
        sa.Column("score", sa.Float, server_default="0.0"),
        sa.Column("correct", sa.Integer, server_default="0"),
        sa.Column("total", sa.Integer, server_default="0"),
        sa.Column("answers_json", JSONB, server_default="{}"),
        sa.Column("submitted_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_local_results_user", "local_assessment_results", ["user_id"])

    # Simplified admin config (no FK to users)
    op.create_table(
        "local_admin_config",
        sa.Column("org_id", sa.Text, primary_key=False),
        sa.Column("config_key", sa.Text, primary_key=False),
        sa.Column("config_value", JSONB, nullable=False, server_default="null"),
        sa.Column("description", sa.Text, server_default=""),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("org_id", "config_key"),
    )
    op.create_index("ix_local_admin_config_org", "local_admin_config", ["org_id"])

    # Analytics events
    op.create_table(
        "local_analytics_events",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("event_type", sa.Text, nullable=False),
        sa.Column("user_id", sa.Text, server_default=""),
        sa.Column("topic", sa.Text, server_default=""),
        sa.Column("rating", sa.Integer),
        sa.Column("metadata", JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_local_analytics_type", "local_analytics_events", ["event_type"])
    op.create_index("ix_local_analytics_user", "local_analytics_events", ["user_id"])

    # Seed default admin config
    op.execute("""
        INSERT INTO local_admin_config (org_id, config_key, config_value, description)
        VALUES
          ('default', 'confidence_threshold', '0.4', 'Minimum confidence score to show answer'),
          ('default', 'max_rag_chunks', '5', 'Max RAG chunks per query'),
          ('default', 'session_ttl_minutes', '60', 'Session expiry in minutes'),
          ('default', 'default_model_tier', '"standard"', 'LLM model tier: small | standard | large'),
          ('default', 'data_retention_days', '90', 'Days to retain chat history')
        ON CONFLICT DO NOTHING
    """)


def downgrade() -> None:
    op.drop_table("local_analytics_events")
    op.drop_table("local_admin_config")
    op.drop_table("local_assessment_results")
    op.drop_table("local_assessments")
    op.drop_table("local_topic_progress")
    op.drop_table("local_learner_profiles")
