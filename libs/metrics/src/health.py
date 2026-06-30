"""Health and readiness endpoints."""
from __future__ import annotations

from fastapi import APIRouter
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.responses import Response


def create_health_router(*, ready_check=None) -> APIRouter:
    router = APIRouter(tags=["health"])

    @router.get("/health")
    async def health():
        return {"status": "healthy"}

    @router.get("/ready")
    async def ready():
        if ready_check and not ready_check():
            return Response(content='{"status":"not_ready"}', status_code=503, media_type="application/json")
        return {"status": "ready"}

    @router.get("/metrics")
    async def metrics():
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return router
