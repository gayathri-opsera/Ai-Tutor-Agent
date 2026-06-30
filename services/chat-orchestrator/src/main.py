"""Chat Orchestrator FastAPI app."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.chat import router as chat_router
from src.service import ChatOrchestratorService, InMemorySessionCache, MockSessionRepository


def create_app() -> FastAPI:
    app = FastAPI(title="Chat Orchestrator", version="1.0.0")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    app.include_router(chat_router)

    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    @app.on_event("startup")
    async def startup():
        cache = InMemorySessionCache()
        repo = MockSessionRepository()
        app.state.chat_service = ChatOrchestratorService(cache, repo)

    cache = InMemorySessionCache()
    repo = MockSessionRepository()
    app.state.chat_service = ChatOrchestratorService(cache, repo)
    return app


app = create_app()
