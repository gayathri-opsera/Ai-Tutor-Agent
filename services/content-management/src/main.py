from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.content import router
from src.api.admin_courses import router as admin_courses_router
from src.service import ContentManagementService, Document, KnowledgeBase, create_pool

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
        for entry in SEED_DATA:
            kb = entry["kb"]
            await conn.execute(
                """
                INSERT INTO knowledge_bases (id, name, description, organization_id)
                VALUES ($1, $2, $3, $4)
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


app = FastAPI(title="Content Management", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
app.include_router(admin_courses_router)


@app.get("/health")
async def health():
    return {"status": "healthy"}
