"""Learner profile API."""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/learner", tags=["learner"])


class ProfileUpdate(BaseModel):
    display_name: str | None = None
    proficiency_level: str | None = None
    preferences: dict[str, Any] | None = None


class TopicUpdate(BaseModel):
    topic: str
    level: str = "in_progress"
    score: float = 0.5
    knowledge_base_id: str | None = None


@router.get("/profile")
async def get_profile(user_id: str = "demo-user", request: Request = None):
    svc = request.app.state.profile_service
    profile = await svc.get_or_create(user_id)
    return profile


@router.put("/profile")
async def update_profile(body: ProfileUpdate, user_id: str = "demo-user", request: Request = None):
    svc = request.app.state.profile_service
    profile = await svc.update_profile(user_id, body.model_dump(exclude_none=True))
    return {"user_id": profile["user_id"], "display_name": profile["display_name"]}


@router.post("/topic")
async def update_topic(body: TopicUpdate, user_id: str = "demo-user", request: Request = None):
    svc = request.app.state.profile_service
    await svc.update_topic(user_id, body.topic, body.level, body.score, body.knowledge_base_id)
    return {"ok": True}


@router.get("/progress")
async def get_progress(user_id: str = "demo-user", request: Request = None):
    svc = request.app.state.profile_service
    return await svc.get_progress(user_id)
