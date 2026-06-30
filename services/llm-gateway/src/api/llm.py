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
            error_payload = json.dumps({"error": str(exc), "request_id": body.request_id})
            yield f"data: {error_payload}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/health")
async def health(request: Request) -> dict:
    """Lightweight liveness + circuit-breaker state probe."""
    llm_router: LLMRouter = request.app.state.llm_router
    return {
        "status": "ok",
        "circuit_breaker": llm_router.circuit_stats(),
    }
