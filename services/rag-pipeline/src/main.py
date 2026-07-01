"""RAG Pipeline FastAPI application."""
from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.vector_client import VectorDBClient, VectorRecord
from src.api.rag import router as rag_router
from src.config import settings
from src.service import RAGPipelineService

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://ai_tutor:ai_tutor_local_password@postgres:5432/ai_tutor",
)
WEAVIATE_URL = os.getenv("WEAVIATE_URL", "http://weaviate:8080")


async def _bootstrap_vectors(pool: asyncpg.Pool, rag_service: RAGPipelineService) -> int:
    """Load all indexed chunks from the DB into the in-memory vector store.

    This ensures the vector store is repopulated after a container restart
    even though vectors are stored in memory.
    """
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT dc.id, dc.document_id, dc.chunk_text, dc.metadata,
                       d.title AS document_title,
                       kb.id   AS knowledge_base_id
                FROM document_chunks dc
                JOIN documents d  ON d.id  = dc.document_id
                JOIN knowledge_bases kb ON kb.id = d.knowledge_base_id
                WHERE d.is_active = true
                ORDER BY dc.document_id, dc.chunk_index
                """
            )
        if not rows:
            return 0

        # Embed all chunk texts in batches
        texts = [r["chunk_text"] for r in rows]
        embeddings = await rag_service._embed_batch(texts)

        records = []
        for row, embedding in zip(rows, embeddings):
            try:
                meta = json.loads(row["metadata"]) if isinstance(row["metadata"], str) else dict(row["metadata"] or {})
            except Exception:
                meta = {}
            meta.update({
                "knowledge_base_id": str(row["knowledge_base_id"]),
                "document_id":       str(row["document_id"]),
                "document_title":    row["document_title"],
                "text":              row["chunk_text"],
            })
            records.append(VectorRecord(id=str(row["id"]), vector=embedding, metadata=meta))

        await rag_service.vector_client.upsert_vectors(records)
        logger.info("Bootstrapped %d vectors from DB", len(records))
        return len(records)
    except Exception as exc:
        logger.warning("Vector bootstrap failed (non-fatal): %s", exc)
        return 0


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Connect to PostgreSQL
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
    app.state.db_pool = pool

    # Connect to vector DB (Weaviate or in-memory fallback)
    vector_client = VectorDBClient(_mock_store={})
    await vector_client.connect(WEAVIATE_URL)

    rag_service = RAGPipelineService(vector_client, settings.embedding_service_url)
    app.state.rag_service = rag_service

    # Re-populate vector store from persisted chunks
    count = await _bootstrap_vectors(pool, rag_service)
    logger.info("RAG Pipeline started — %d chunks loaded into vector store", count)

    yield
    await pool.close()


def create_app(rag_service=None) -> FastAPI:
    _app = FastAPI(title="RAG Pipeline", version="1.0.0", lifespan=lifespan)
    _app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    _app.include_router(rag_router)
    if rag_service is not None:
        _app.state.rag_service = rag_service

    @_app.get("/health")
    async def health():
        return {"status": "healthy"}

    return _app


app = create_app()
