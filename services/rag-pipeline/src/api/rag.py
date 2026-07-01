"""RAG Pipeline API routes."""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Request
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class RetrieveRequest(BaseModel):
    query: str
    knowledge_base_id: str
    top_k: int = Field(default=5, ge=1, le=50)
    filters: dict[str, Any] | None = None
    use_hybrid: bool = True


class ChunkResult(BaseModel):
    chunk_id: str
    text: str
    document_id: str
    document_title: str
    score: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class RetrieveResponse(BaseModel):
    chunks: list[ChunkResult]
    query_embedding: list[float]


class IngestChunk(BaseModel):
    text: str
    chunk_index: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class IngestRequest(BaseModel):
    document_id: str
    knowledge_base_id: str
    document_title: str
    chunks: list[IngestChunk]


router = APIRouter(prefix="/api/internal/rag", tags=["rag"])

_EMBED_BATCH_SIZE = 50  # keep each embedding call small to avoid timeouts


async def _do_ingest(body: IngestRequest, service, db_pool) -> None:
    """Background task: embed chunks and upsert into vector store + DB."""
    from src.vector_client import VectorRecord

    texts = [c.text for c in body.chunks]
    if not texts:
        return

    # Process in sub-batches so progress is saved even if later batches fail
    total_indexed = 0
    for batch_start in range(0, len(texts), _EMBED_BATCH_SIZE):
        batch_chunks = body.chunks[batch_start:batch_start + _EMBED_BATCH_SIZE]
        batch_texts  = [c.text for c in batch_chunks]
        try:
            embeddings = await service._embed_batch(batch_texts)
        except Exception as exc:
            logger.warning("Embedding batch %d-%d failed: %s — skipping",
                           batch_start, batch_start + len(batch_texts), exc)
            continue

        vector_records = []
        async with db_pool.acquire() as conn:
            for i, (chunk, embedding) in enumerate(zip(batch_chunks, embeddings)):
                chunk_id = str(uuid.uuid4())
                abs_index = batch_start + i
                metadata = {
                    "knowledge_base_id": body.knowledge_base_id,
                    "document_id": body.document_id,
                    "document_title": body.document_title,
                    "text": chunk.text,
                    "chunk_index": chunk.chunk_index if chunk.chunk_index is not None else abs_index,
                    **chunk.metadata,
                }
                await conn.execute(
                    """
                    INSERT INTO document_chunks (id, document_id, chunk_index, chunk_text, vector_id, metadata)
                    VALUES ($1, $2, $3, $4, $5, $6::jsonb)
                    ON CONFLICT (id) DO NOTHING
                    """,
                    chunk_id,
                    body.document_id,
                    chunk.chunk_index if chunk.chunk_index is not None else abs_index,
                    chunk.text,
                    chunk_id,
                    json.dumps(metadata),
                )
                vector_records.append(VectorRecord(id=chunk_id, vector=embedding, metadata=metadata))

        if vector_records:
            await service.vector_client.upsert_vectors(vector_records)
            total_indexed += len(vector_records)

    logger.info("Ingest complete: %d/%d chunks indexed for document %s",
                total_indexed, len(texts), body.document_id)


@router.post("/ingest", status_code=202)
async def ingest_document(body: IngestRequest, background_tasks: BackgroundTasks, request: Request):
    """Accept chunks and schedule embedding + vector-store upsert as a background task."""
    service  = request.app.state.rag_service
    db_pool  = request.app.state.db_pool

    if not body.chunks:
        return {"indexed": 0, "queued": 0}

    background_tasks.add_task(_do_ingest, body, service, db_pool)
    logger.info("Queued %d chunks for background ingest (document %s)",
                len(body.chunks), body.document_id)
    return {"queued": len(body.chunks), "document_id": body.document_id}


@router.post("/retrieve", response_model=RetrieveResponse)
async def retrieve(body: RetrieveRequest, request: Request):
    service = request.app.state.rag_service
    result = await service.retrieve(
        body.query,
        body.knowledge_base_id,
        top_k=body.top_k,
        filters=body.filters,
        use_hybrid=body.use_hybrid,
    )
    return RetrieveResponse(**result)


@router.get("/debug/vector-store")
async def debug_vector_store(request: Request, kb_id: str = ""):
    """Debug: inspect stored vectors to diagnose score issues."""
    vc = request.app.state.rag_service.vector_client
    ns = vc._mock.get("default", {}) if vc._mock is not None else {}
    total = len(ns)
    
    # Sample a vector from the given KB
    sample = None
    for rec in ns.values():
        if not kb_id or str(rec.metadata.get("knowledge_base_id", "")) == kb_id:
            sample = rec
            break
    
    if not sample:
        return {"total_vectors": total, "error": "no matching vector found"}
    
    vec = sample.vector
    vec_norm = sum(x*x for x in vec) ** 0.5
    nonzero = sum(1 for x in vec if abs(x) > 1e-9)
    
    return {
        "total_vectors": total,
        "sample_id": sample.id,
        "sample_text": sample.metadata.get("text", "")[:80],
        "vector_dim": len(vec),
        "vector_norm": round(vec_norm, 6),
        "nonzero_dims": nonzero,
        "first_5_values": [round(v, 6) for v in vec[:5]],
    }
