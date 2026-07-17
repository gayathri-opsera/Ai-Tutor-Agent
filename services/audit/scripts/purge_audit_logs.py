#!/usr/bin/env python3
"""Automated audit log purge script (WO-266).

Reads audit_retention_days from admin_configurations (default 365).
Permanently deletes audit_logs records older than that threshold.
Runs as the ai_tutor_purge DB role so the immutability trigger allows the
DELETE (WO-270).

Scheduled via Kubernetes CronJob at 03:00 UTC daily.
"""
from __future__ import annotations

import asyncio
import logging
import os

import asyncpg

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://ai_tutor_purge:ai_tutor_local_password@postgres:5432/ai_tutor",
)
DEFAULT_RETENTION_DAYS = 365


async def main() -> None:
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=2)

    async with pool.acquire() as conn:
        # Read configured retention period
        row = await conn.fetchrow(
            "SELECT config_value FROM admin_configurations WHERE config_key = 'audit_retention_days'"
        )
        retention_days = int(row["config_value"]) if row else DEFAULT_RETENTION_DAYS

        result = await conn.execute(
            f"""
            DELETE FROM audit_logs
            WHERE created_at < now() - INTERVAL '{retention_days} days'
            """,
        )

    deleted = int(result.split()[-1]) if result else 0
    logger.info("Audit log purge complete: deleted %d records older than %d days", deleted, retention_days)
    await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
