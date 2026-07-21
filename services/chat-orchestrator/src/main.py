"""Chat Orchestrator FastAPI app."""
from __future__ import annotations

import asyncio
import logging
import os

import asyncpg
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from src.api.chat import router as chat_router
from src.repository import DatabaseSessionRepository, InMemorySessionCache, MockSessionRepository
from src.service import ChatOrchestratorService

DATABASE_URL = os.getenv("DATABASE_URL", "")

# Sessions older than this many days are automatically deleted.
CHAT_RETENTION_DAYS = int(os.getenv("CHAT_RETENTION_DAYS", "7"))

logger = logging.getLogger(__name__)


async def _purge_loop(repo: DatabaseSessionRepository, interval_hours: int = 24) -> None:
    """Background task: purge old chat sessions every `interval_hours` hours."""
    while True:
        await asyncio.sleep(interval_hours * 3600)
        try:
            await repo.purge_old_sessions(CHAT_RETENTION_DAYS)
        except Exception as exc:
            logger.warning("Purge loop error: %s", exc)


def create_app(repository=None) -> FastAPI:
    app = FastAPI(title="Chat Orchestrator", version="1.0.0")
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    app.include_router(chat_router)

    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    @app.on_event("startup")
    async def startup():
        cache = InMemorySessionCache()
        if repository is not None:
            repo = repository
        elif DATABASE_URL:
            try:
                pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
                repo = DatabaseSessionRepository(pool)
                app.state.db_pool = pool
                # Run an immediate purge on startup, then every 24 hours.
                await repo.purge_old_sessions(CHAT_RETENTION_DAYS)
                asyncio.create_task(_purge_loop(repo))
            except Exception as exc:
                logging.getLogger(__name__).warning("DB unavailable, using in-memory repo: %s", exc)
                repo = MockSessionRepository()
        else:
            repo = MockSessionRepository()
        app.state.chat_service = ChatOrchestratorService(cache, repo)

    @app.on_event("shutdown")
    async def shutdown():
        pool = getattr(app.state, "db_pool", None)
        if pool:
            await pool.close()

    # Pre-wire for import-time access (create_app used without lifespan in tests)
    cache = InMemorySessionCache()
    repo = repository if repository is not None else MockSessionRepository()
    app.state.chat_service = ChatOrchestratorService(cache, repo)

    return app


app = create_app()
