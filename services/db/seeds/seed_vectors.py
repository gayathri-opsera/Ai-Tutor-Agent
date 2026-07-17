#!/usr/bin/env python3
"""Idempotent seed data pipeline for Weaviate vector store.

Usage:
    python services/db/seeds/seed_vectors.py

Environment variables:
    DATABASE_URL        PostgreSQL DSN
    CONTENT_SERVICE_URL Base URL of the content-management service
    INGEST_SERVICE_URL  Base URL of the RAG pipeline ingest endpoint

The script is idempotent — running it multiple times will not create duplicate
documents, chunks, or vectors because:
  1. knowledge_bases and documents use ON CONFLICT DO NOTHING.
  2. document_chunks use ON CONFLICT (document_id, chunk_index) DO UPDATE
     only when content_hash changes (deduplication from WO-263).
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from pathlib import Path

import asyncpg
import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://ai_tutor:ai_tutor_local_password@localhost:5432/ai_tutor",
)
INGEST_URL = os.getenv("INGEST_SERVICE_URL", "http://localhost:8002")
SEEDS_DIR  = Path(__file__).parent / "vector_data"


async def ensure_knowledge_base(conn: asyncpg.Connection, kb_id: str, name: str) -> None:
    await conn.execute(
        """
        INSERT INTO knowledge_bases (id, name, description, is_active)
        VALUES ($1, $2, 'Seed knowledge base', true)
        ON CONFLICT (id) DO NOTHING
        """,
        kb_id, name,
    )


async def ensure_document(conn: asyncpg.Connection, doc_id: str, kb_id: str, title: str) -> None:
    await conn.execute(
        """
        INSERT INTO documents (id, knowledge_base_id, title, is_active, s3_key)
        VALUES ($1, $2, $3, true, $4)
        ON CONFLICT (id) DO NOTHING
        """,
        doc_id, kb_id, title, f"seeds/{doc_id}",
    )


async def ingest_document(doc: dict) -> int:
    """Send document chunks to the RAG pipeline ingest endpoint and return count."""
    payload = {
        "document_id":    doc["id"],
        "knowledge_base_id": doc["knowledge_base_id"],
        "document_title": doc["title"],
        "chunks": [
            {"text": c["text"], "chunk_index": c["chunk_index"]}
            for c in doc["chunks"]
        ],
    }
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(f"{INGEST_URL}/api/internal/rag/ingest", json=payload)
            resp.raise_for_status()
        logger.info("Ingested %d chunks for %s", len(doc["chunks"]), doc["title"])
        return len(doc["chunks"])
    except Exception as exc:
        logger.warning("Ingest failed for %s: %s — skipping", doc["id"], exc)
        return 0


async def main() -> None:
    seed_files = sorted(SEEDS_DIR.glob("*.json"))
    if not seed_files:
        logger.error("No seed files found in %s", SEEDS_DIR)
        return

    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=3)
    total_chunks = 0

    for path in seed_files:
        doc = json.loads(path.read_text())
        logger.info("Processing seed: %s", path.name)

        async with pool.acquire() as conn:
            await ensure_knowledge_base(conn, doc["knowledge_base_id"], "General Knowledge Base")
            await ensure_document(conn, doc["id"], doc["knowledge_base_id"], doc["title"])

        ingested = await ingest_document(doc)
        total_chunks += ingested

    await pool.close()
    logger.info("Seed pipeline complete — %d chunks processed across %d documents",
                total_chunks, len(seed_files))


if __name__ == "__main__":
    asyncio.run(main())
