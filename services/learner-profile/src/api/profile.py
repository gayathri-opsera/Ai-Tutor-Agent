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


class LessonProgress(BaseModel):
    kb_id: str
    doc_id: str
    completed: bool


class EnrollRequest(BaseModel):
    kb_id: str


@router.get("/enrollments")
async def list_enrollments(user_id: str = "demo-user", request: Request = None):
    """Return list of KB IDs the user is enrolled in."""
    pool = request.app.state.db_pool
    rows = await pool.fetch(
        "SELECT kb_id::text FROM enrollments WHERE user_id = (SELECT id FROM users WHERE keycloak_id = $1 OR id::text = $1 LIMIT 1)",
        user_id,
    )
    return {"enrolled_kb_ids": [r["kb_id"] for r in rows]}


@router.post("/enroll")
async def enroll(body: EnrollRequest, user_id: str = "demo-user", request: Request = None):
    """Enroll the user in a course (knowledge base)."""
    pool = request.app.state.db_pool
    # Resolve user UUID
    user_row = await pool.fetchrow(
        "SELECT id FROM users WHERE keycloak_id = $1 OR id::text = $1 LIMIT 1", user_id
    )
    if not user_row:
        return {"ok": False, "error": "User not found"}
    uid = user_row["id"]
    await pool.execute(
        "INSERT INTO enrollments (user_id, kb_id) VALUES ($1, $2::uuid) ON CONFLICT DO NOTHING",
        uid, body.kb_id,
    )
    return {"ok": True, "kb_id": body.kb_id}


@router.delete("/enroll/{kb_id}")
async def unenroll(kb_id: str, user_id: str = "demo-user", request: Request = None):
    """Unenroll the user from a course."""
    pool = request.app.state.db_pool
    user_row = await pool.fetchrow(
        "SELECT id FROM users WHERE keycloak_id = $1 OR id::text = $1 LIMIT 1", user_id
    )
    if not user_row:
        return {"ok": False, "error": "User not found"}
    uid = user_row["id"]
    await pool.execute(
        "DELETE FROM enrollments WHERE user_id = $1 AND kb_id = $2::uuid",
        uid, kb_id,
    )
    return {"ok": True, "kb_id": kb_id}


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


@router.post("/lesson")
async def save_lesson(body: LessonProgress, user_id: str = "demo-user", request: Request = None):
    """Record a lesson (document) as completed or uncompleted for a user."""
    svc = request.app.state.profile_service
    await svc.save_lesson_progress(user_id, body.kb_id, body.doc_id, body.completed)
    return {"ok": True, "completed": body.completed}


@router.get("/course/{kb_id}/progress")
async def get_course_progress(kb_id: str, user_id: str = "demo-user", request: Request = None):
    """Return per-lesson completion state for a user within a knowledge base."""
    svc = request.app.state.profile_service
    return await svc.get_course_progress(user_id, kb_id)


@router.post("/session")
async def increment_session(user_id: str = "demo-user", request: Request = None):
    """Increment the session counter for a learner — called by chat orchestrator on session create."""
    svc = request.app.state.profile_service
    await svc.increment_session(user_id)
    return {"ok": True}


@router.get("/dashboard")
async def get_dashboard(user_id: str = "demo-user", request: Request = None):
    """Aggregated learner dashboard: completion %, assessment scores, time, streak, topic progress."""
    svc = request.app.state.profile_service
    return await svc.get_dashboard(user_id)
