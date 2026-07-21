"""Admin Config Service — FastAPI entrypoint."""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware

from src.api.admin_users import router as admin_users_router
from src.api.data_subject import router as data_subject_router
from src.api.auth import router as auth_router
from src.api.config import router as config_router
from src.repository import UserRepository
from src.service import AdminConfigService, DB_DSN

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

_log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = await asyncpg.create_pool(dsn=DB_DSN, min_size=1, max_size=5)
    app.state.admin_config = AdminConfigService(pool=pool)
    app.state.user_repo = UserRepository(pool=pool)
    app.state.db_pool = pool  # exposed for self-registration endpoints
    # Ensure standard roles exist (idempotent seed)
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO roles (name, description) VALUES
              ('Admin',      'Platform administrator'),
              ('SuperAdmin', 'Super administrator with all privileges'),
              ('Creator',    'Course creator and content manager'),
              ('Learner',    'Course learner')
            ON CONFLICT (name) DO NOTHING
            """
        )
    yield
    await pool.close()


app = FastAPI(title="Admin Configuration Service", lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# ── JWT auth middleware — validates Bearer tokens (or mock-jwt-* in dev) ──────
# libs/auth is on PYTHONPATH via Dockerfile.service so we import directly.
try:
    from middleware import AuthMiddleware  # noqa: PLC0415

    async def _check_approval(keycloak_id: str) -> str:
        """Fetch approval_status from DB for the authenticated user."""
        repo: UserRepository = app.state.user_repo
        return await repo.get_approval_status(keycloak_id) or "approved"

    async def _resolve_roles(user_id: str) -> list[str]:
        """Look up actual DB roles for a self-registered user (mock-reg-* token)."""
        repo: UserRepository = app.state.user_repo
        return await repo.get_user_roles(user_id)

    app.add_middleware(
        AuthMiddleware,
        exclude_paths=["/health", "/ready", "/metrics", "/docs", "/openapi.json",
                       "/api/v1/auth/self-register", "/api/v1/auth/mock-login"],
        approval_checker=_check_approval,
        role_resolver=_resolve_roles,
        # Public registration/login endpoints bypass auth entirely
        approval_exclude_paths=["/api/v1/auth/register",
                                 "/api/v1/auth/self-register",
                                 "/api/v1/auth/mock-login"],
    )
except ImportError:
    _log.warning("AuthMiddleware unavailable — running without auth enforcement")

app.include_router(config_router)
app.include_router(auth_router)
app.include_router(admin_users_router)
app.include_router(data_subject_router)


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "admin-config"}
