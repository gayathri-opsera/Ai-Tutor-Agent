"""Chat Orchestrator FastAPI app."""
from __future__ import annotations

import os

import asyncpg
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.chat import router as chat_router
from src.repository import DatabaseSessionRepository, InMemorySessionCache, MockSessionRepository
from src.service import ChatOrchestratorService

DATABASE_URL = os.getenv("DATABASE_URL", "")


def create_app(repository=None) -> FastAPI:
    app = FastAPI(title="Chat Orchestrator", version="1.0.0")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    app.include_router(chat_router)

    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    @app.on_event("startup")
    async def startup():
        cache = InMemorySessionCache()
        if repository is not None:
            # Injected repo (used in tests)
            repo = repository
        elif DATABASE_URL:
            try:
                pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
                repo = DatabaseSessionRepository(pool)
                app.state.db_pool = pool
            except Exception as exc:
                import logging
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
