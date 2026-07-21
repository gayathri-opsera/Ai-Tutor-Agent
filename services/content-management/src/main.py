from contextlib import asynccontextmanager
import hashlib

from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.cors import CORSMiddleware

from src.api.content import router
from src.api.admin_courses import router as admin_courses_router
from src.service import ContentManagementService, create_pool

# ── Demo / mock user seed ──────────────────────────────────────────────────────
# These users match the mock auth roster in the frontend (VITE_AUTH_MOCK=true).
# All FK-constrained tables (chat_sessions, learner_profiles, etc.) require the
# user to exist in the `users` table — seeding them here ensures a fresh DB works.
MOCK_USERS = [
    {
        "id":       "aaaaaaaa-0001-0000-0000-000000000001",
        "email":    b"admin@ai-tutor.local",
        "name":     b"Alice Admin",
        "keycloak_id": "aaaaaaaa-0001-0000-0000-000000000001",
    },
    {
        "id":       "cccccccc-0002-0000-0000-000000000002",
        "email":    b"creator@ai-tutor.local",
        "name":     b"Chris Creator",
        "keycloak_id": "cccccccc-0002-0000-0000-000000000002",
    },
    {
        "id":       "dddddddd-0003-0000-0000-000000000003",
        "email":    b"learner@ai-tutor.local",
        "name":     b"Leah Learner",
        "keycloak_id": "dddddddd-0003-0000-0000-000000000003",
    },
]



async def _seed_db(pool) -> None:
    """Upsert demo KB + document rows so fresh DB deployments have data."""
    async with pool.acquire() as conn:
        # Seed all mock users so FK constraints on chat_sessions, learner_profiles,
        # etc. are satisfied when running with VITE_AUTH_MOCK=true.
        for u in MOCK_USERS:
            await conn.execute(
                """
                INSERT INTO users (id, email_encrypted, email_hash, full_name_encrypted, keycloak_id, approval_status)
                VALUES ($1::uuid, $2, $3, $4, $5::text, 'approved')
                ON CONFLICT DO NOTHING
                """,
                u["id"],
                u["email"],
                hashlib.sha256(u["email"]).hexdigest(),
                u["name"],
                u["keycloak_id"],
            )


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = await create_pool()
    await _seed_db(pool)
    app.state.cms = ContentManagementService(pool)
    yield
    await pool.close()


app = FastAPI(title="Content Management", lifespan=lifespan, redirect_slashes=False)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Wire up AuthMiddleware so request.state.user is populated with the caller's
# JWT claims (roles, sub, etc.) — required for admin-only endpoints.
try:
    import sys, os
    sys.path.insert(0, "/app/libs/auth/src")
    from middleware import AuthMiddleware  # noqa: PLC0415

    async def _resolve_roles(user_id: str) -> list[str]:
        """Look up actual DB roles for a self-registered user (mock-reg-* token)."""
        pool = app.state.cms._pool if hasattr(app.state, "cms") else None
        if pool is None:
            return []
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
        approval_checker=None,  # content-management doesn't gate on approval
        approval_exclude_paths=[],
        role_resolver=_resolve_roles,
    )
except Exception:
    pass  # Auth library unavailable — admin checks fall back to None user

app.include_router(router)
app.include_router(admin_courses_router)


@app.get("/health")
async def health():
    return {"status": "healthy"}
