"""LLM Gateway API routes.

Endpoints (internal only — not exposed to external callers):
  POST /api/internal/llm/completions        — synchronous completion
  POST /api/internal/llm/completions/stream — SSE token-by-token streaming
"""
from __future__ import annotations

import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from src.router import LLMRouter
from src.schemas.request import CompletionRequest
from src.schemas.response import CompletionResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/internal/llm", tags=["llm-gateway"])


def _get_router(request: Request) -> LLMRouter:
    """FastAPI dependency: retrieve the shared LLMRouter from app state."""
    return request.app.state.llm_router


@router.post("/completions", response_model=CompletionResponse)
async def completions(
    body: CompletionRequest,
    llm_router: LLMRouter = Depends(_get_router),
) -> CompletionResponse:
    """Non-streaming LLM completion.

    Accepts a provider-agnostic request and returns a unified response.
    The circuit breaker transparently routes to the fallback provider on
    primary failure.
    """
    if not body.request_id:
        body = body.model_copy(update={"request_id": str(uuid.uuid4())})

    try:
        return await llm_router.complete(body)
    except Exception as exc:
        logger.exception("Completion failed for request_id=%s", body.request_id)
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/completions/stream")
async def completions_stream(
    body: CompletionRequest,
    llm_router: LLMRouter = Depends(_get_router),
) -> StreamingResponse:
    """SSE token-by-token streaming completion.

    Each Server-Sent Event carries a JSON-encoded `StreamChunk`.
    The final chunk includes `usage` and `estimated_cost_usd`.
    """
    if not body.request_id:
        body = body.model_copy(update={"request_id": str(uuid.uuid4())})

    async def event_generator():
        try:
            async for chunk in llm_router.stream(body):
                data = chunk.model_dump_json()
                yield f"data: {data}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as exc:
            logger.exception("Stream failed for request_id=%s", body.request_id)
            raw = str(exc)
            lower = raw.lower()
            if "credit balance" in lower or "credits" in lower or "billing" in lower:
                msg = "⚠️ AI account has no credits. Go to **console.anthropic.com → Billing** to add credits, then retry."
            elif "429" in raw:
                msg = "⚠️ AI rate limit hit. Please wait a moment and try again."
            elif "401" in raw or "403" in raw:
                msg = "⚠️ API key is invalid or unauthorised. Check your `.env` file."
            else:
                msg = f"⚠️ AI service error: {raw[:120]}"
            # Emit error as a delta token so the chat UI shows a message
            fallback = json.dumps({"delta": msg, "finish_reason": "error",
                                   "error": raw, "request_id": body.request_id})
            yield f"data: {fallback}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/embed")
async def embed(
    body: dict,
    request: Request,
) -> dict:
    """Generate embeddings — proxies to the dedicated embedding-service.

    The primary LLM provider (Anthropic) has no embedding endpoint; routing
    to the embedding-service avoids the NotImplementedError and keeps latency
    low by using the local sentence-transformers model.
    """
    import os, httpx as _httpx
    texts: list[str] = body.get("texts", [])
    model: str | None = body.get("model")
    if not texts:
        raise HTTPException(status_code=422, detail="'texts' list is required")

    embedding_url = os.getenv("EMBEDDING_SERVICE_URL", "http://embedding-service:8001")
    try:
        async with _httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{embedding_url}/api/internal/embeddings/generate",
                json={"texts": texts, "model": model},
            )
            resp.raise_for_status()
            data = resp.json()
            return {"embeddings": data.get("embeddings", []), "model": data.get("model", model or "multilingual")}
    except Exception as exc:
        logger.exception("Embed failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/health")
async def health(request: Request) -> dict:
    """Lightweight liveness + circuit-breaker state probe."""
    llm_router: LLMRouter = request.app.state.llm_router
    return {
        "status": "ok",
        "circuit_breaker": llm_router.circuit_stats(),
    }
