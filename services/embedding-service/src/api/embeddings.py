"""FastAPI router for the Embedding Service."""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request

from src.schemas import EmbedRequest, EmbedResponse
from src.service import EmbeddingService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/internal/embeddings", tags=["embeddings"])


def _get_service(request: Request) -> EmbeddingService:
    return request.app.state.embedding_service


@router.post("/generate", response_model=EmbedResponse)
async def generate_embeddings(body: EmbedRequest, request: Request) -> EmbedResponse:
    """Embed a batch of text chunks.

    Accepts up to 100 texts per request. Returns one vector per input text.
    """
    svc: EmbeddingService = _get_service(request)
    try:
        return await svc.generate(body)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.error("Embedding generation failed: %s", exc)
        raise HTTPException(status_code=502, detail="Upstream embedding backend error.")


@router.get("/health")
async def health(request: Request) -> dict:
    svc: EmbeddingService = _get_service(request)
    return {
        "status": "ok",
        "backend": svc.backend.name,
        "default_model": svc.backend.default_model(),
    }
