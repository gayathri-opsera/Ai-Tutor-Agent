from contextlib import asynccontextmanager
import hashlib

from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.cors import CORSMiddleware

from src.api.content import router
from src.api.admin_courses import router as admin_courses_router
from src.service import ContentManagementService, Document, KnowledgeBase, create_pool

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

# Demo seed data — inserted once into the DB if not already present.
# IDs are stable so the frontend fallbacks always resolve.
SEED_DATA = [
    {
        "kb": KnowledgeBase(
            id="bbbbbbbb-0001-0000-0000-000000000001",
            name="Python Fundamentals",
            description="Core Python programming: variables, functions, OOP, and async patterns.",
            organization_id="default",
        ),
        "docs": [
            Document(id="cccccccc-0001-0000-0000-000000000001", knowledge_base_id="bbbbbbbb-0001-0000-0000-000000000001", title="Introduction to Python",      content_type="text", chunk_count=2),
            Document(id="cccccccc-0002-0000-0000-000000000002", knowledge_base_id="bbbbbbbb-0001-0000-0000-000000000001", title="Async Programming in Python", content_type="text", chunk_count=1),
        ],
    },
    {
        "kb": KnowledgeBase(
            id="bbbbbbbb-0002-0000-0000-000000000002",
            name="Machine Learning Basics",
            description="Intro to supervised, unsupervised, and reinforcement learning.",
            organization_id="default",
        ),
        "docs": [
            Document(id="cccccccc-0003-0000-0000-000000000003", knowledge_base_id="bbbbbbbb-0002-0000-0000-000000000002", title="Linear Regression Explained", content_type="text", chunk_count=1),
        ],
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
                ON CONFLICT (id) DO UPDATE SET approval_status = 'approved'
                """,
                u["id"],
                u["email"],
                hashlib.sha256(u["email"]).hexdigest(),
                u["name"],
                u["keycloak_id"],
            )

        for entry in SEED_DATA:
            kb = entry["kb"]
            await conn.execute(
                """
                INSERT INTO knowledge_bases (id, name, description, organization_id, approval_status)
                VALUES ($1, $2, $3, $4, 'approved'::kb_approval_status_enum)
                ON CONFLICT (id) DO NOTHING
                """,
                kb.id, kb.name, kb.description, kb.organization_id,
            )
            for doc in entry["docs"]:
                await conn.execute(
                    """
                    INSERT INTO documents (id, knowledge_base_id, title, content_type, status, chunk_count)
                    VALUES ($1, $2, $3, $4::content_type_enum, 'active'::document_status_enum, $5)
                    ON CONFLICT (id) DO NOTHING
                    """,
                    doc.id, doc.knowledge_base_id, doc.title, doc.content_type, doc.chunk_count,
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
    app.add_middleware(
        AuthMiddleware,
        approval_checker=None,  # content-management doesn't gate on approval
        approval_exclude_paths=[],
    )
except Exception:
    pass  # Auth library unavailable — admin checks fall back to None user

app.include_router(router)
app.include_router(admin_courses_router)


@app.get("/health")
async def health():
    return {"status": "healthy"}
