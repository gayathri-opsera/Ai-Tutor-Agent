"""Shared PostgreSQL connection pool factory.

Eliminates duplicated asyncpg pool creation across 14 microservices.
Each service calls ``create_pool()`` once in its lifespan handler instead of
repeating the same pool options everywhere.

Usage::

    from libs.db.src.pool import create_pool

    @asynccontextmanager
    async def lifespan(app):
        app.state.pool = await create_pool()
        yield
        await app.state.pool.close()
"""
from __future__ import annotations

import os

import asyncpg

_DEFAULT_MIN = int(os.getenv("DB_POOL_MIN", "2"))
_DEFAULT_MAX = int(os.getenv("DB_POOL_MAX", "10"))

try:
    from provider import get_db_dsn  # type: ignore[import]
except ImportError:
    def get_db_dsn() -> str:  # type: ignore[misc]
        return os.environ.get(
            "DATABASE_URL",
            "postgresql://ai_tutor:ai_tutor_local_password@postgres:5432/ai_tutor",
        )


async def create_pool(
    *,
    dsn: str | None = None,
    min_size: int = _DEFAULT_MIN,
    max_size: int = _DEFAULT_MAX,
) -> asyncpg.Pool:
    """Create and return an asyncpg connection pool.

    Args:
        dsn: PostgreSQL DSN. Defaults to ``get_db_dsn()`` from ``libs/secrets``.
        min_size: Minimum number of pooled connections.
        max_size: Maximum number of pooled connections.

    Returns:
        An open ``asyncpg.Pool`` ready for use.
    """
    return await asyncpg.create_pool(
        dsn=dsn or get_db_dsn(),
        min_size=min_size,
        max_size=max_size,
        command_timeout=30,
        max_inactive_connection_lifetime=300,
    )
