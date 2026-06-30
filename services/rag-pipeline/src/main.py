"""RAG Pipeline FastAPI application."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services" / "rag-pipeline"))

from src.vector_client import VectorDBClient  # noqa: E402
from src.api.rag import router as rag_router
from src.config import settings
from src.service import RAGPipelineService

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)


def create_app(vector_client: VectorDBClient | None = None) -> FastAPI:
    app = FastAPI(title="RAG Pipeline", version="1.0.0")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    app.include_router(rag_router)

    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    @app.on_event("startup")
    async def startup():
        client = vector_client or VectorDBClient(_mock_store={})
        await client.connect()
        app.state.rag_service = RAGPipelineService(client, settings.embedding_service_url)
        logger.info("RAG Pipeline started")

    return app


app = create_app()
