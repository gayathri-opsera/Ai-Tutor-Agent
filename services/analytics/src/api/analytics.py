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
