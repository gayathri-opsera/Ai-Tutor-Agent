#!/usr/bin/env python3
"""Assessment results 3-year retention purge script (WO-267).

Reads assessment_retention_days from admin_configurations (default 1095 = 3 years).
Permanently deletes assessment_results records whose completed_at is older than
the retention threshold.

Scheduled via Kubernetes CronJob at 03:30 UTC daily.
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
    "postgresql://ai_tutor:ai_tutor_local_password@postgres:5432/ai_tutor",
)
DEFAULT_RETENTION_DAYS = 1095  # 3 years


async def main() -> None:
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=2)

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT config_value FROM admin_configurations WHERE config_key = 'assessment_retention_days'"
        )
        retention_days = int(row["config_value"]) if row else DEFAULT_RETENTION_DAYS

        result = await conn.execute(
            f"""
            DELETE FROM local_assessment_results
            WHERE created_at < now() - INTERVAL '{retention_days} days'
            """,
        )

    deleted = int(result.split()[-1]) if result else 0
    logger.info(
        "Assessment results purge complete: deleted %d records older than %d days",
        deleted, retention_days,
    )
    await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
