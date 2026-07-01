"""Analytics aggregation service — PostgreSQL-backed."""
from __future__ import annotations

import json
import os
import uuid
from typing import Any

import asyncpg

DB_DSN = os.getenv(
    "DATABASE_URL",
    "postgresql://ai_tutor:ai_tutor_local_password@postgres:5432/ai_tutor",
)


class AnalyticsService:
    def __init__(self, pool: asyncpg.Pool | None = None) -> None:
        self._pool = pool

    async def _get_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(dsn=DB_DSN, min_size=1, max_size=5)
        return self._pool

    async def consume(self, payload: dict) -> None:
        pool = await self._get_pool()
        event_id = str(uuid.uuid4())
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO local_analytics_events (id, event_type, user_id, topic, rating, metadata)
                VALUES ($1, $2, $3, $4, $5, $6::jsonb)
                """,
                event_id,
                payload.get("event_type", "unknown"),
                payload.get("user_id", ""),
                payload.get("topic", ""),
                payload.get("rating"),
                json.dumps(payload.get("metadata", {})),
            )

    async def summary(self) -> dict[str, Any]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            sessions = await conn.fetchval(
                "SELECT COUNT(*) FROM local_analytics_events WHERE event_type = 'session.created'"
            )
            queries = await conn.fetchval(
                "SELECT COUNT(*) FROM local_analytics_events WHERE event_type = 'query.submitted'"
            )
            avg_rating = await conn.fetchval(
                "SELECT AVG(rating) FROM local_analytics_events WHERE rating IS NOT NULL"
            )
            topic_rows = await conn.fetch(
                "SELECT topic, COUNT(*) as cnt FROM local_analytics_events WHERE topic != '' GROUP BY topic ORDER BY cnt DESC LIMIT 10"
            )
            recent = await conn.fetch(
                "SELECT event_type, user_id, topic, rating, created_at FROM local_analytics_events ORDER BY created_at DESC LIMIT 20"
            )
        return {
            "session_count": sessions or 0,
            "query_volume": queries or 0,
            "average_rating": round(float(avg_rating), 2) if avg_rating else 0.0,
            "topic_distribution": {r["topic"]: r["cnt"] for r in topic_rows},
            "recent_events": [dict(r) for r in recent],
        }
