"""Add retention config, data deletion requests, and audit log immutability.

Revision ID: 0012
Revises: 0011
Create Date: 2026-07-17

WO-266: admin_configurations with audit_retention_days=365
WO-267: admin_configurations with assessment_retention_days=1095
WO-268: data_deletion_requests table for PII purge workflow
WO-270: immutability trigger on audit_logs (blocks UPDATE/DELETE except purge account)
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── admin_configurations table ────────────────────────────────────────────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS admin_configurations (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            config_key  TEXT NOT NULL UNIQUE,
            config_value TEXT NOT NULL,
            description TEXT,
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    # Seed retention config values
    op.execute(
        """
        INSERT INTO admin_configurations (organization_id, config_key, config_value, description)
        VALUES
          ('system', 'audit_retention_days', '"365"',
           'Number of days to retain audit_logs records before purge'),
          ('system', 'assessment_retention_days', '"1095"',
           'Number of days to retain assessment_results records (3 years)')
        ON CONFLICT (organization_id, config_key) DO NOTHING
        """
    )

    # ── data_deletion_requests ────────────────────────────────────────────────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS data_deletion_requests (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id         TEXT NOT NULL,
            requested_by    TEXT NOT NULL,
            status          TEXT NOT NULL DEFAULT 'pending'
                              CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
            requested_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            scheduled_purge_at TIMESTAMPTZ NOT NULL DEFAULT (now() + INTERVAL '30 days'),
            completed_at    TIMESTAMPTZ,
            notes           TEXT
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_data_deletion_status ON data_deletion_requests (status, scheduled_purge_at)")

    # ── audit_logs immutability trigger (WO-270) ─────────────────────────────
    # The trigger blocks UPDATE/DELETE except when the executing role is 'ai_tutor_purge'
    # (the service account used by the retention CronJob).
    op.execute(
        """
        CREATE OR REPLACE FUNCTION audit_logs_immutability_guard()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            -- Allow the purge service account to delete old records
            IF current_user = 'ai_tutor_purge' THEN
                RETURN OLD;
            END IF;
            RAISE EXCEPTION
                'audit_logs is append-only: UPDATE and DELETE are not permitted (user=%). '
                'Use the retention purge job for scheduled cleanup.', current_user;
        END;
        $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_trigger WHERE tgname = 'trg_audit_logs_immutable'
            ) THEN
                CREATE TRIGGER trg_audit_logs_immutable
                BEFORE UPDATE OR DELETE ON audit_logs
                FOR EACH ROW EXECUTE FUNCTION audit_logs_immutability_guard();
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_audit_logs_immutable ON audit_logs")
    op.execute("DROP FUNCTION IF EXISTS audit_logs_immutability_guard()")
    op.execute("DROP TABLE IF EXISTS data_deletion_requests")
    op.execute("DELETE FROM admin_configurations WHERE config_key IN ('audit_retention_days', 'assessment_retention_days')")
