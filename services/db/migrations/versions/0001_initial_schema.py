"""Initial schema — all tables for AI Tutor Agent platform.

Revision ID: 0001
Revises: (none)
Create Date: 2026-06-30
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, ENUM

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

# Enums
data_classification = ENUM(
    "PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED",
    name="data_classification_enum", create_type=True
)
content_type_enum = ENUM(
    "pdf", "docx", "mp4", "mp3", "wav", "url", "text",
    name="content_type_enum", create_type=True
)
document_status_enum = ENUM(
    "uploading", "processing", "active", "error", "retired",
    name="document_status_enum", create_type=True
)
message_role_enum = ENUM(
    "user", "assistant", "system",
    name="message_role_enum", create_type=True
)


def upgrade() -> None:
    # Enable pgcrypto for column-level encryption
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\"")

    # ------------------------------------------------------------------ roles
    op.create_table(
        "roles",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("name", sa.String(50), nullable=False, unique=True),
        sa.Column("description", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("data_classification", data_classification, nullable=False, server_default="INTERNAL"),
    )

    # ------------------------------------------------------------------ users
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        # PII columns stored as bytea (application-level AES-256 encryption)
        sa.Column("email_encrypted", sa.LargeBinary, nullable=False),
        sa.Column("email_hash", sa.String(64), nullable=False, unique=True),  # for lookups
        sa.Column("full_name_encrypted", sa.LargeBinary, nullable=False),
        sa.Column("keycloak_id", sa.String(255), unique=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("data_classification", data_classification, nullable=False, server_default="CONFIDENTIAL"),
    )
    op.create_index("ix_users_email_hash", "users", ["email_hash"])
    op.create_index("ix_users_keycloak_id", "users", ["keycloak_id"])

    # ------------------------------------------------------------------ user_roles
    op.create_table(
        "user_roles",
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role_id", UUID(as_uuid=True), sa.ForeignKey("roles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("user_id", "role_id"),
        sa.Column("data_classification", data_classification, nullable=False, server_default="INTERNAL"),
    )
    op.create_index("ix_user_roles_user_id", "user_roles", ["user_id"])

    # ------------------------------------------------------------------ knowledge_bases
    op.create_table(
        "knowledge_bases",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("organization_id", sa.String(255), nullable=False),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("data_classification", data_classification, nullable=False, server_default="INTERNAL"),
    )
    op.create_index("ix_knowledge_bases_org", "knowledge_bases", ["organization_id", "is_active"])

    # ------------------------------------------------------------------ documents
    op.create_table(
        "documents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("knowledge_base_id", UUID(as_uuid=True), sa.ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("content_type", content_type_enum, nullable=False),
        sa.Column("s3_bucket", sa.String(255)),
        sa.Column("s3_key", sa.Text),
        sa.Column("file_size_bytes", sa.BigInteger),
        sa.Column("status", document_status_enum, nullable=False, server_default="uploading"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("retired_at", sa.DateTime(timezone=True)),
        sa.Column("chunk_count", sa.Integer, server_default="0"),
        sa.Column("uploaded_by", UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("data_classification", data_classification, nullable=False, server_default="INTERNAL"),
    )
    op.create_index("ix_documents_kb_active", "documents", ["knowledge_base_id", "is_active"])
    op.create_index("ix_documents_status", "documents", ["status"])

    # ------------------------------------------------------------------ document_chunks
    op.create_table(
        "document_chunks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("document_id", UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("chunk_text", sa.Text, nullable=False),
        sa.Column("vector_id", sa.String(255)),  # ID in vector DB
        sa.Column("page_number", sa.Integer),
        sa.Column("metadata", JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("data_classification", data_classification, nullable=False, server_default="INTERNAL"),
    )
    op.create_index("ix_chunks_document", "document_chunks", ["document_id", "chunk_index"])
    op.create_index("ix_chunks_vector_id", "document_chunks", ["vector_id"])

    # ------------------------------------------------------------------ chat_sessions
    op.create_table(
        "chat_sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("knowledge_base_id", UUID(as_uuid=True), sa.ForeignKey("knowledge_bases.id")),
        sa.Column("title", sa.String(500)),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("data_classification", data_classification, nullable=False, server_default="CONFIDENTIAL"),
    )
    op.create_index("ix_sessions_user", "chat_sessions", ["user_id", "created_at"])

    # ------------------------------------------------------------------ chat_messages
    op.create_table(
        "chat_messages",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("session_id", UUID(as_uuid=True), sa.ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", message_role_enum, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("sources_json", JSONB, server_default="[]"),
        sa.Column("confidence_score", sa.Float),
        sa.Column("feedback", sa.SmallInteger),  # 1=thumbs up, -1=thumbs down
        sa.Column("feedback_at", sa.DateTime(timezone=True)),
        sa.Column("tokens_used", sa.Integer),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("data_classification", data_classification, nullable=False, server_default="CONFIDENTIAL"),
    )
    op.create_index("ix_messages_session_created", "chat_messages", ["session_id", "created_at"])

    # ------------------------------------------------------------------ learner_profiles
    op.create_table(
        "learner_profiles",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("preferred_difficulty", sa.String(50), server_default="beginner"),
        sa.Column("notes_encrypted", sa.LargeBinary),  # PII
        sa.Column("total_sessions", sa.Integer, server_default="0"),
        sa.Column("total_queries", sa.Integer, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("data_classification", data_classification, nullable=False, server_default="RESTRICTED"),
    )

    # ------------------------------------------------------------------ learner_topic_progress
    op.create_table(
        "learner_topic_progress",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("learner_profile_id", UUID(as_uuid=True), sa.ForeignKey("learner_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("knowledge_base_id", UUID(as_uuid=True), sa.ForeignKey("knowledge_bases.id")),
        sa.Column("topic", sa.String(255), nullable=False),
        sa.Column("status", sa.String(50), server_default="not_started"),  # not_started | in_progress | mastered
        sa.Column("proficiency_score", sa.Float, server_default="0.0"),
        sa.Column("last_activity_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("data_classification", data_classification, nullable=False, server_default="CONFIDENTIAL"),
    )
    op.create_index("ix_topic_progress_learner", "learner_topic_progress", ["learner_profile_id", "knowledge_base_id"])

    # ------------------------------------------------------------------ assessments
    op.create_table(
        "assessments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("knowledge_base_id", UUID(as_uuid=True), sa.ForeignKey("knowledge_bases.id"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("assessment_type", sa.String(50), server_default="pre"),  # pre | post | practice
        sa.Column("questions_json", JSONB, nullable=False, server_default="[]"),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("data_classification", data_classification, nullable=False, server_default="INTERNAL"),
    )

    # ------------------------------------------------------------------ assessment_results
    op.create_table(
        "assessment_results",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("assessment_id", UUID(as_uuid=True), sa.ForeignKey("assessments.id"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("score", sa.Float),
        sa.Column("answers_json", JSONB, server_default="{}"),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("data_classification", data_classification, nullable=False, server_default="CONFIDENTIAL"),
    )
    op.create_index("ix_results_user_assessment", "assessment_results", ["user_id", "assessment_id"])

    # ------------------------------------------------------------------ admin_configurations
    op.create_table(
        "admin_configurations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("organization_id", sa.String(255), nullable=False),
        sa.Column("config_key", sa.String(255), nullable=False),
        sa.Column("config_value", JSONB, nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("updated_by", UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("data_classification", data_classification, nullable=False, server_default="INTERNAL"),
        sa.UniqueConstraint("organization_id", "config_key", name="uq_admin_config"),
    )
    op.create_index("ix_admin_config_org", "admin_configurations", ["organization_id"])

    # ------------------------------------------------------------------ audit_logs
    op.create_table(
        "audit_logs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("actor_id", sa.String(255), nullable=False),
        sa.Column("actor_role", sa.String(100)),
        sa.Column("action", sa.String(255), nullable=False),
        sa.Column("resource_type", sa.String(100)),
        sa.Column("resource_id", sa.String(255)),
        sa.Column("outcome", sa.String(50), nullable=False),  # success | failure
        sa.Column("ip_address", sa.String(45)),
        sa.Column("metadata", JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("data_classification", data_classification, nullable=False, server_default="RESTRICTED"),
    )
    op.create_index("ix_audit_actor_time", "audit_logs", ["actor_id", "created_at"])
    op.create_index("ix_audit_action", "audit_logs", ["action", "created_at"])

    # ------------------------------------------------------------------ content_feedback
    op.create_table(
        "content_feedback",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("message_id", UUID(as_uuid=True), sa.ForeignKey("chat_messages.id"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("rating", sa.SmallInteger),  # 1 | -1
        sa.Column("comment", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("data_classification", data_classification, nullable=False, server_default="CONFIDENTIAL"),
    )


def downgrade() -> None:
    for tbl in [
        "content_feedback", "audit_logs", "admin_configurations",
        "assessment_results", "assessments", "learner_topic_progress",
        "learner_profiles", "chat_messages", "chat_sessions",
        "document_chunks", "documents", "knowledge_bases",
        "user_roles", "users", "roles",
    ]:
        op.drop_table(tbl)
    for enum_name in [
        "data_classification_enum", "content_type_enum",
        "document_status_enum", "message_role_enum",
    ]:
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
