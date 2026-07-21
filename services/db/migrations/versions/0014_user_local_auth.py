"""Add user_local_auth table for self-registration in mock/dev mode."""
from alembic import op
import sqlalchemy as sa

revision = "0014_user_local_auth"
down_revision = "0013_add_content_text_to_documents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_local_auth",
        sa.Column("id",            sa.dialects.postgresql.UUID(as_uuid=True),
                  server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column("user_id",       sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("email",         sa.Text(), nullable=False, unique=True),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("desired_role",  sa.Text(), nullable=False, server_default="Learner"),
        sa.Column("created_at",    sa.TIMESTAMP(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_user_local_auth_email", "user_local_auth", ["email"])


def downgrade() -> None:
    op.drop_index("ix_user_local_auth_email", table_name="user_local_auth")
    op.drop_table("user_local_auth")
