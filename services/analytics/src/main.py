"""Analytics Service — FastAPI entrypoint."""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware

from src.api.analytics import router
from src.service import AnalyticsService, DB_DSN

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

_log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = await asyncpg.create_pool(dsn=DB_DSN, min_size=1, max_size=5)
    app.state.analytics = AnalyticsService(pool=pool)
    app.state.db_pool = pool
    yield
    await pool.close()


app = FastAPI(title="Analytics Service", lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# ── JWT auth middleware — needed so request.state.user is populated for require_role ──
try:
    from middleware import AuthMiddleware  # noqa: PLC0415

    async def _resolve_roles(user_id: str) -> list[str]:
        """Look up actual DB roles for a self-registered user (mock-reg-* token)."""
        pool = app.state.db_pool
        rows = await pool.fetch(
            """
            SELECT r.name FROM roles r
            JOIN user_roles ur ON ur.role_id = r.id
            WHERE ur.user_id = $1::uuid
            """,
            user_id,
        )
        return [r["name"] for r in rows]

    app.add_middleware(
        AuthMiddleware,
        exclude_paths=["/health", "/ready", "/metrics", "/docs", "/openapi.json"],
        role_resolver=_resolve_roles,
    )
except ImportError:
    _log.warning("AuthMiddleware unavailable — running without auth enforcement")

app.include_router(router)


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "analytics"}
