"""Learner profile API."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/learner", tags=["learner"])


class ProfileUpdate(BaseModel):
    display_name: str | None = None
    preferences: dict[str, Any] | None = None


@router.get("/profile")
async def get_profile(user_id: str = "demo-user", request: Request = None):
    svc = request.app.state.profile_service
    profile = svc.get_or_create(user_id)
    return {
        "user_id": profile.user_id,
        "display_name": profile.display_name,
        "preferences": profile.preferences,
        "topics": [{"topic": t.topic, "level": t.level, "score": t.score} for t in profile.topics],
    }


@router.put("/profile")
async def update_profile(body: ProfileUpdate, user_id: str = "demo-user", request: Request = None):
    svc = request.app.state.profile_service
    profile = svc.update_profile(user_id, body.model_dump(exclude_none=True))
    return {"user_id": profile.user_id, "display_name": profile.display_name}


@router.get("/progress")
async def get_progress(user_id: str = "demo-user", request: Request = None):
    svc = request.app.state.profile_service
    return svc.get_progress(user_id)
