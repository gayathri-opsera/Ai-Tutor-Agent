"""RAG Pipeline API routes."""
from __future__ import annotations

import asyncio
import json
import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Request

# Shared contract models — migrated to libs/contracts (WO-013).
# Re-exported here for backward compatibility with any code that imports directly
# from this module (e.g. `from src.api.rag import RetrieveRequest`).
from rag import (  # noqa: F401 — re-export
    ChunkResult,
    IngestChunk,
    IngestRequest,
    RetrieveRequest,
    RetrieveResponse,
)

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/api/internal/rag", tags=["rag"])

_EMBED_BATCH_SIZE = 50  # keep each embedding call small to avoid timeouts


async def _do_ingest(body: IngestRequest, service, db_pool) -> None:
    """Background task: embed chunks and upsert into vector store + DB.

    Implements chunk-level deduplication (WO-263):
    - Each chunk text is hashed with SHA-256 (content_hash).
    - If a chunk already exists in the DB with the same document_id, chunk_index,
      AND matching content_hash, it is skipped — no embedding or upsert occurs.
    - If the content_hash differs (chunk was updated), it is re-embedded and upserted.
    """
    import hashlib
    from src.vector_client import VectorRecord

    texts = [c.text for c in body.chunks]
    if not texts:
        return

    # Process in sub-batches so progress is saved even if later batches fail
    total_indexed = 0
    for batch_start in range(0, len(texts), _EMBED_BATCH_SIZE):
        batch_chunks = body.chunks[batch_start:batch_start + _EMBED_BATCH_SIZE]
        batch_texts  = [c.text for c in batch_chunks]

        # Deduplication: load existing content hashes for this document/chunk range
        abs_indices = [
            c.chunk_index if c.chunk_index is not None else batch_start + i
            for i, c in enumerate(batch_chunks)
        ]
        async with db_pool.acquire() as conn:
            existing_rows = await conn.fetch(
                """
                SELECT chunk_index, content_hash, id AS vector_id
                FROM document_chunks
                WHERE document_id = $1 AND chunk_index = ANY($2::int[])
                """,
                body.document_id,
                abs_indices,
            )
        existing_by_idx = {r["chunk_index"]: r for r in existing_rows}

        # Determine which chunks need embedding
        chunks_to_embed: list[tuple[int, int, object]] = []  # (batch_pos, abs_index, chunk)
        for i, (chunk, abs_idx) in enumerate(zip(batch_chunks, abs_indices)):
            new_hash = hashlib.sha256(chunk.text.encode()).hexdigest()
            ex = existing_by_idx.get(abs_idx)
            if not body.force and ex and ex["content_hash"] == new_hash:
                # Identical content and not a forced re-index — skip embedding
                logger.debug("Skipping unchanged chunk %d for document %s", abs_idx, body.document_id)
                continue
            chunks_to_embed.append((i, abs_idx, chunk))

        if not chunks_to_embed:
            continue

        embed_texts = [c.text for _, _, c in chunks_to_embed]
        try:
            embeddings = await service._embed_batch(embed_texts)
        except Exception as exc:
            logger.warning("Embedding batch %d-%d failed: %s — skipping",
                           batch_start, batch_start + len(embed_texts), exc)
            continue

        vector_records = []
        async with db_pool.acquire() as conn:
            for (_, abs_index, chunk), embedding in zip(chunks_to_embed, embeddings):
                chunk_id = str(uuid.uuid4())
                new_hash = hashlib.sha256(chunk.text.encode()).hexdigest()
                metadata = {
                    "knowledge_base_id": body.knowledge_base_id,
                    "document_id": body.document_id,
                    "document_title": body.document_title,
                    "text": chunk.text,
                    "chunk_index": abs_index,
                    **chunk.metadata,
                }
                await conn.execute(
                    """
                    INSERT INTO document_chunks
                      (id, document_id, chunk_index, chunk_text, vector_id, metadata, content_hash)
                    VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7)
                    ON CONFLICT (document_id, chunk_index)
                    DO UPDATE SET
                      chunk_text   = EXCLUDED.chunk_text,
                      vector_id    = EXCLUDED.vector_id,
                      metadata     = EXCLUDED.metadata,
                      content_hash = EXCLUDED.content_hash,
                      updated_at   = now()
                    """,
                    chunk_id,
                    body.document_id,
                    abs_index,
                    chunk.text,
                    chunk_id,
                    json.dumps(metadata),
                    new_hash,
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


# ── Suggested questions ────────────────────────────────────────────────────────

@router.get("/suggested-questions")
async def suggested_questions(knowledge_base_id: str, request: Request):
    """Return 3-5 course-contextual suggested questions for the chat landing screen.

    Retrieves representative chunks from the knowledge base, then calls the
    LLM gateway to generate relevant questions. Falls back to a static list
    if the LLM or RAG pipeline is unavailable.
    """
    service = request.app.state.rag_service

    FALLBACK_QUESTIONS = [
        "What are the key concepts covered in this course?",
        "Can you summarise the main topics?",
        "What are the most important things to learn here?",
    ]

    try:
        # Pull a representative sample of chunks from the KB
        sample_result = await service.retrieve(
            query="overview introduction key concepts main topics",
            knowledge_base_id=knowledge_base_id,
            top_k=5,
        )
        chunks = sample_result.get("chunks", [])
        if not chunks:
            return {"knowledge_base_id": knowledge_base_id, "questions": FALLBACK_QUESTIONS}

        context_text = "\n\n".join(c["text"][:300] for c in chunks[:4])
        prompt = (
            f"Based on the following course content, generate exactly 4 short, specific questions "
            f"a learner might want to ask. Return ONLY a JSON array of strings. No markdown, no explanation.\n\n"
            f"Content:\n{context_text}\n\nQuestions:"
        )

        import httpx
        import os as _os
        llm_url = _os.getenv("LLM_GATEWAY_URL", "http://llm-gateway:8003")
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{llm_url}/api/internal/complete",
                json={"messages": [{"role": "user", "content": prompt}], "max_tokens": 300},
            )
            resp.raise_for_status()
            data = resp.json()
            content = data.get("content") or data.get("choices", [{}])[0].get("message", {}).get("content", "")

        import json as _json
        # Extract the JSON array from the response
        start = content.find("[")
        end   = content.rfind("]") + 1
        if start >= 0 and end > start:
            questions = _json.loads(content[start:end])
            if isinstance(questions, list) and questions:
                return {"knowledge_base_id": knowledge_base_id, "questions": questions[:5]}
    except Exception as exc:
        logger.warning("Suggested questions generation failed (fallback): %s", exc)

    return {"knowledge_base_id": knowledge_base_id, "questions": FALLBACK_QUESTIONS}
