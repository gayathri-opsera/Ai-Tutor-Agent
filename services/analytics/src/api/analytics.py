"""Analytics API routes."""
from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel
from typing import Any

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


class AnalyticsEvent(BaseModel):
    event_type: str
    user_id: str = ""
    topic: str = ""
    rating: int | None = None
    metadata: dict[str, Any] = {}


@router.post("/events", status_code=201)
async def record_event(body: AnalyticsEvent, request: Request):
    svc = request.app.state.analytics
    await svc.consume(body.model_dump())
    return {"ok": True}


@router.get("/summary")
async def get_summary(request: Request):
    svc = request.app.state.analytics
    return await svc.summary()


@router.get("/creator/dashboard")
async def creator_dashboard(request: Request):
    """Return per-course enrollment metrics scoped to the authenticated creator.

    Admins receive metrics for all courses (platform-wide view).
    """
    svc = request.app.state.analytics
    user = getattr(request.state, "user", None)
    caller_sub = getattr(user, "sub", None) if user else None
    is_admin = bool(user and any(r in {"Admin", "SuperAdmin"} for r in getattr(user, "roles", [])))
    creator_filter = None if is_admin else caller_sub
    return await svc.creator_dashboard(creator_keycloak_id=creator_filter)


@router.get("/admin/dashboard")
async def admin_dashboard(request: Request):
    """Return platform-wide aggregate metrics. Requires Admin or SuperAdmin role."""
    user = getattr(request.state, "user", None)
    if user is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Authentication required")
    if not any(r in {"Admin", "SuperAdmin"} for r in getattr(user, "roles", [])):
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Admin or SuperAdmin role required")
    svc = request.app.state.analytics
    return await svc.admin_dashboard()
