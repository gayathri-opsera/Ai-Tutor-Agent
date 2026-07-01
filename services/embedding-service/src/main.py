"""Embedding Service — FastAPI application entry point."""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.embeddings import router as embed_router
from src.config import settings
from src.service import EmbeddingService, make_backend

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(
        title="Embedding Service",
        description=(
            "Provider-agnostic embedding generation. Supports OpenAI (via LLM Gateway), "
            "sentence-transformers (local GPU), and a deterministic mock backend for testing."
        ),
        version="1.0.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["POST", "GET"],
        allow_headers=["*"],
    )

    app.include_router(embed_router)

    @app.get("/health")
    async def health() -> dict:
        return {"status": "healthy"}

    @app.on_event("startup")
    async def startup() -> None:
        if not hasattr(app.state, "embedding_service"):
            backend = make_backend()
            app.state.embedding_service = EmbeddingService(backend)
        logger.info(
            "Embedding Service started — backend=%s",
            app.state.embedding_service.backend.name,
        )

    return app


app = create_app()
