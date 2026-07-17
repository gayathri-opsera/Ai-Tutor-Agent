"""Analytics API routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, field_validator

try:
    from decorators import require_role  # type: ignore[import]  # libs/auth
    _admin_guard = Depends(require_role("Admin", "SuperAdmin"))
except ImportError:
    _admin_guard = None  # fallback for environments without libs/auth on path
from typing import Any

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


class AnalyticsEvent(BaseModel):
    event_type: str = Field(..., min_length=1, max_length=128,
                            description="Dot-separated event name, e.g. 'course.view'")
    user_id: str = Field(default="", max_length=256)
    topic: str = Field(default="", max_length=256)
    rating: int | None = Field(default=None, ge=1, le=5,
                               description="Optional satisfaction rating 1–5")
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("event_type")
    @classmethod
    def event_type_format(cls, v: str) -> str:
        """Reject whitespace-only or obviously invalid event names."""
        if not v.strip():
            raise ValueError("event_type must not be blank")
        return v.strip().lower()


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


@router.get("/admin/dashboard", dependencies=[_admin_guard] if _admin_guard else [])
async def admin_dashboard(request: Request):
    """Return platform-wide aggregate metrics. Requires Admin or SuperAdmin role."""
    svc = request.app.state.analytics
    return await svc.admin_dashboard()
