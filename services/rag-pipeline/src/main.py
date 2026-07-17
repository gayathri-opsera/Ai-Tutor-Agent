"""RAG Pipeline FastAPI application."""
from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.cors import CORSMiddleware

from src.vector_client import VectorDBClient, VectorRecord
from src.api.rag import router as rag_router
from src.config import settings
from src.service import RAGPipelineService

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)

try:
    from provider import get_db_dsn, get_weaviate_url  # type: ignore[import]
    DATABASE_URL = get_db_dsn()
    WEAVIATE_URL = get_weaviate_url()
except ImportError:
    DATABASE_URL = os.environ["DATABASE_URL"]
    WEAVIATE_URL = os.getenv("WEAVIATE_URL", "http://weaviate:8080")


async def _ensure_watermark_table(pool: asyncpg.Pool) -> None:
    """Create vector_sync_watermarks table if it does not exist."""
    async with pool.acquire() as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS vector_sync_watermarks (
                service      TEXT PRIMARY KEY,
                last_synced_at TIMESTAMPTZ NOT NULL DEFAULT '1970-01-01T00:00:00Z'
            )
            """
        )
        await conn.execute(
            """
            INSERT INTO vector_sync_watermarks (service, last_synced_at)
            VALUES ('rag-pipeline', '1970-01-01T00:00:00Z')
            ON CONFLICT (service) DO NOTHING
            """
        )


async def _delta_sync_vectors(pool: asyncpg.Pool, rag_service: RAGPipelineService) -> int:
    """Sync only document chunks updated since the last successful sync (watermark).

    Replaces the old full-bootstrap approach.  On first run the watermark is
    epoch-0 so all active chunks are ingested; on subsequent restarts only
    newly-updated chunks are re-embedded and upserted.
    """
    try:
        await _ensure_watermark_table(pool)

        async with pool.acquire() as conn:
            wm_row = await conn.fetchrow(
                "SELECT last_synced_at FROM vector_sync_watermarks WHERE service = 'rag-pipeline'"
            )
            watermark = wm_row["last_synced_at"] if wm_row else None

            rows = await conn.fetch(
                """
                SELECT dc.id, dc.document_id, dc.chunk_text, dc.metadata,
                       dc.updated_at,
                       d.title AS document_title,
                       kb.id   AS knowledge_base_id
                FROM document_chunks dc
                JOIN documents d  ON d.id  = dc.document_id
                JOIN knowledge_bases kb ON kb.id = d.knowledge_base_id
                WHERE d.is_active = true
                  AND dc.updated_at > $1
                ORDER BY dc.document_id, dc.chunk_index
                """,
                watermark,
            )

        if not rows:
            logger.info("Delta sync: no new or updated chunks since %s", watermark)
            return 0

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

        # Advance watermark to the most-recently-updated chunk we just synced
        new_watermark = max(r["updated_at"] for r in rows)
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE vector_sync_watermarks SET last_synced_at = $1 WHERE service = 'rag-pipeline'",
                new_watermark,
            )

        logger.info("Delta sync: upserted %d vectors, watermark advanced to %s",
                    len(records), new_watermark)
        return len(records)
    except Exception as exc:
        logger.warning("Vector delta sync failed (non-fatal): %s", exc)
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
    count = await _delta_sync_vectors(pool, rag_service)
    logger.info("RAG Pipeline started — %d chunks loaded into vector store", count)

    yield
    await pool.close()


def create_app(rag_service=None) -> FastAPI:
    _app = FastAPI(title="RAG Pipeline", version="1.0.0", lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=1000)
    _app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    _app.include_router(rag_router)
    if rag_service is not None:
        _app.state.rag_service = rag_service

    @_app.get("/health")
    async def health():
        """Health check with Weaviate connectivity status and vector sync metrics."""
        import time
        import httpx as _httpx

        weaviate_status = "unknown"
        try:
            async with _httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(f"{WEAVIATE_URL}/v1/.well-known/ready")
                weaviate_status = "healthy" if resp.status_code == 200 else f"degraded ({resp.status_code})"
        except Exception as exc:
            weaviate_status = f"unreachable ({exc})"

        overall = "healthy" if weaviate_status == "healthy" else "degraded"

        # Expose Prometheus-style metrics as plain text via Accept header or ?format=prometheus
        return {
            "status": overall,
            "weaviate_status": weaviate_status,
            "vector_sync": {
                "description": "See /metrics for Prometheus scrape endpoint",
            },
        }

    @_app.get("/metrics", include_in_schema=False)
    async def metrics():
        """Prometheus text exposition for vector sync observability."""
        from fastapi.responses import PlainTextResponse

        # Read watermark from DB if available
        last_sync_ts = 0.0
        sync_chunks_total = 0
        try:
            import asyncpg as _asyncpg
            pool = await _asyncpg.create_pool(
                os.getenv("DATABASE_URL", DATABASE_URL), min_size=1, max_size=1
            )
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT last_synced_at FROM vector_sync_watermarks WHERE service = 'rag-pipeline'"
                )
                if row and row["last_synced_at"]:
                    import datetime
                    last_sync_ts = row["last_synced_at"].timestamp()
                count_row = await conn.fetchrow("SELECT COUNT(*) AS n FROM document_chunks")
                if count_row:
                    sync_chunks_total = int(count_row["n"])
            await pool.close()
        except Exception:
            pass

        lines = [
            "# HELP vector_sync_last_success_timestamp Unix timestamp of last successful vector sync",
            "# TYPE vector_sync_last_success_timestamp gauge",
            f"vector_sync_last_success_timestamp {last_sync_ts}",
            "# HELP vector_sync_chunks_total Total document chunks indexed in vector store",
            "# TYPE vector_sync_chunks_total counter",
            f"vector_sync_chunks_total {sync_chunks_total}",
        ]
        return PlainTextResponse("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")

    return _app


app = create_app()
