"""Admin configuration service — PostgreSQL-backed."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

import asyncpg

DB_DSN = os.getenv(
    "DATABASE_URL",
    "postgresql://ai_tutor:ai_tutor_local_password@postgres:5432/ai_tutor",
)


class AdminConfigService:
    def __init__(self, pool: asyncpg.Pool | None = None) -> None:
        self._pool = pool

    async def _get_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(dsn=DB_DSN, min_size=1, max_size=5)
        return self._pool

    async def get(self, org_id: str, key: str) -> dict | None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT org_id, config_key, config_value, description, updated_at FROM local_admin_config WHERE org_id = $1 AND config_key = $2",
                org_id, key,
            )
        return dict(row) if row else None

    async def set(self, org_id: str, key: str, value: Any, description: str = "") -> dict:
        pool = await self._get_pool()
        value_json = json.dumps(value)
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO local_admin_config (org_id, config_key, config_value, description, updated_at)
                VALUES ($1, $2, $3::jsonb, $4, now())
                ON CONFLICT (org_id, config_key) DO UPDATE
                SET config_value = $3::jsonb, description = COALESCE(NULLIF($4,''), local_admin_config.description), updated_at = now()
                """,
                org_id, key, value_json, description,
            )
        return {"org_id": org_id, "key": key, "value": value}

    async def list_all(self, org_id: str) -> list[dict]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT org_id, config_key, config_value, description, updated_at FROM local_admin_config WHERE org_id = $1 ORDER BY config_key",
                org_id,
            )
        return [dict(r) for r in rows]

    async def delete(self, org_id: str, key: str) -> bool:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM local_admin_config WHERE org_id = $1 AND config_key = $2", org_id, key
            )
        return result != "DELETE 0"
