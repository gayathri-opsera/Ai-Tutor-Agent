"""Add age_group and created_by_keycloak_id to knowledge_bases table.

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-17
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

ALLOWED_AGE_GROUPS = ("children", "teens", "adults", "all_ages")


def upgrade() -> None:
    op.add_column(
        "knowledge_bases",
        sa.Column(
            "age_group",
            sa.String(20),
            nullable=True,
            comment="Target audience: children | teens | adults | all_ages",
        ),
    )
    # Store the creator's Keycloak subject UUID for ownership enforcement.
    # The existing created_by FK references the internal users table, but the
    # auth middleware provides only the Keycloak sub claim, so we cache it here
    # to avoid a join for every PUT/DELETE ownership check.
    op.add_column(
        "knowledge_bases",
        sa.Column("created_by_keycloak_id", sa.String(255), nullable=True),
    )
    op.create_index(
        "ix_knowledge_bases_created_by_keycloak",
        "knowledge_bases",
        ["created_by_keycloak_id"],
    )
    op.create_check_constraint(
        "ck_knowledge_bases_age_group",
        "knowledge_bases",
        "age_group IS NULL OR age_group IN ('children', 'teens', 'adults', 'all_ages')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_knowledge_bases_age_group", "knowledge_bases")
    op.drop_index("ix_knowledge_bases_created_by_keycloak", table_name="knowledge_bases")
    op.drop_column("knowledge_bases", "created_by_keycloak_id")
    op.drop_column("knowledge_bases", "age_group")
