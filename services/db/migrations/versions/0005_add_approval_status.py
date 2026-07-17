"""Add approval_status column to users table.

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-17

Adds an approval_status field to users so that new registrations start as
'pending' and require explicit admin approval before gaining platform access.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

# Create the enum type independently so it can be reused or dropped cleanly.
approval_status_enum = ENUM(
    "pending", "approved", "rejected",
    name="approval_status_enum",
    create_type=True,
)


def upgrade() -> None:
    # Create the enum type first
    approval_status_enum.create(op.get_bind(), checkfirst=True)

    # Add column to users table with NOT NULL constraint and default 'pending'.
    # Existing rows get 'approved' to avoid locking out pre-migration users.
    op.add_column(
        "users",
        sa.Column(
            "approval_status",
            approval_status_enum,
            nullable=False,
            server_default="approved",   # pre-existing users are already approved
        ),
    )

    # Flip the server default to 'pending' for all new rows going forward.
    op.alter_column(
        "users",
        "approval_status",
        server_default="pending",
    )

    # Index for efficient filtering by status (admin dashboard queries)
    op.create_index("ix_users_approval_status", "users", ["approval_status"])


def downgrade() -> None:
    op.drop_index("ix_users_approval_status", table_name="users")
    op.drop_column("users", "approval_status")
    approval_status_enum.drop(op.get_bind(), checkfirst=True)
