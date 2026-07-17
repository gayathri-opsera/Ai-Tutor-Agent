"""Admin course approval API — list, approve, reject, request-clarification.

Endpoints:
  GET  /api/v1/admin/courses/pending                      — paginated list
  POST /api/v1/admin/courses/{kb_id}/generate-overview    — AI overview via llm-gateway
  POST /api/v1/admin/courses/{kb_id}/approve              — approve course
  POST /api/v1/admin/courses/{kb_id}/reject               — reject with reason
  POST /api/v1/admin/courses/{kb_id}/request-clarification — ask creator
"""
from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from decorators import require_role  # type: ignore[import]  # from libs/auth

logger = logging.getLogger(__name__)

# FastAPI dependency — machine-verifiable authorization guard on every admin route.
_admin_guard = Depends(require_role("Admin", "SuperAdmin"))

LLM_GATEWAY_URL = os.getenv("LLM_GATEWAY_URL", "http://llm-gateway:8003")
KAFKA_ENABLED   = os.getenv("KAFKA_ENABLED", "false").lower() == "true"

router = APIRouter(prefix="/api/v1/admin/courses", tags=["admin-courses"])


# ── Pydantic models ───────────────────────────────────────────────────────────

class CourseApprovalItem(BaseModel):
    id: str
    name: str
    description: str
    organization_id: str
    approval_status: str
    ai_overview: str | None
    created_at: str


class PendingCoursesResponse(BaseModel):
    courses: list[CourseApprovalItem]
    total: int
    limit: int
    offset: int


class RejectRequest(BaseModel):
    reason: str


class ClarificationRequest(BaseModel):
    message: str


class CourseActionResponse(BaseModel):
    kb_id: str
    approval_status: str
    message: str


# ── Helpers ───────────────────────────────────────────────────────────────────



async def _emit_kafka_event(topic: str, payload: dict) -> None:
    """Fire-and-forget Kafka publish (graceful no-op when Kafka is unavailable)."""
    if not KAFKA_ENABLED:
        logger.debug("Kafka disabled — skipping event to %s", topic)
        return
    try:
        from libs.kafka.src import USER_APPROVAL_EVENTS  # noqa: F401 — just for type hints
        # Lazy import to avoid hard dependency in test/dev
        from kafka import KafkaProducer  # type: ignore[import]
        import json
        producer = KafkaProducer(
            bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092"),
            value_serializer=lambda v: json.dumps(v).encode(),
        )
        producer.send(topic, payload)
        producer.flush()
    except Exception as exc:
        logger.warning("Kafka event delivery failed (non-blocking): %s", exc)


async def _generate_ai_overview(kb_name: str, description: str) -> str:
    """Call llm-gateway to generate a course moderation overview."""
    prompt = (
        f"You are an educational content moderator. Summarise the following course "
        f"for an administrator reviewing it for platform approval. Be concise (2-3 sentences). "
        f"Course name: {kb_name}. Description: {description}"
    )
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{LLM_GATEWAY_URL}/api/internal/complete",
                json={"messages": [{"role": "user", "content": prompt}], "max_tokens": 200},
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("content") or data.get("choices", [{}])[0].get("message", {}).get("content", "")
    except Exception as exc:
        logger.warning("AI overview generation failed: %s", exc)
        return ""


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/pending", response_model=PendingCoursesResponse, dependencies=[_admin_guard])
async def list_pending_courses(
    request: Request,
    limit: int = 50,
    offset: int = 0,
) -> PendingCoursesResponse:
    """Return paginated courses awaiting admin approval."""
    svc = request.app.state.cms

    rows, total = await svc.list_by_approval_status("pending_review", limit=limit, offset=offset)
    return PendingCoursesResponse(
        courses=[CourseApprovalItem(**r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/{kb_id}/generate-overview", status_code=200, dependencies=[_admin_guard])
async def generate_overview(kb_id: str, request: Request) -> dict[str, Any]:
    """Generate an AI moderation overview for a pending course."""
    svc = request.app.state.cms

    kb = await svc.get_kb(kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail=f"Course {kb_id!r} not found")

    overview = await _generate_ai_overview(kb.name, kb.description or "")
    if overview:
        await svc.update_kb_field(kb_id, "ai_overview", overview)

    return {"kb_id": kb_id, "ai_overview": overview}


@router.post("/{kb_id}/approve", response_model=CourseActionResponse, dependencies=[_admin_guard])
async def approve_course(kb_id: str, request: Request) -> CourseActionResponse:
    """Approve a pending course — it becomes visible to learners."""
    svc = request.app.state.cms

    kb = await svc.get_kb(kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail=f"Course {kb_id!r} not found")

    await svc.update_kb_field(kb_id, "approval_status", "approved")

    actor_id = getattr(getattr(request.state, "user", None), "sub", "system")
    await _emit_kafka_event("course-approval-events", {
        "event_type": "course.approval.completed",
        "actor_id":   actor_id,
        "kb_id":      kb_id,
        "outcome":    "approved",
    })

    return CourseActionResponse(kb_id=kb_id, approval_status="approved",
                                message="Course approved and is now visible to learners")


@router.post("/{kb_id}/reject", response_model=CourseActionResponse, dependencies=[_admin_guard])
async def reject_course(
    kb_id: str,
    body: RejectRequest,
    request: Request,
) -> CourseActionResponse:
    """Reject a pending course with a mandatory reason."""
    svc = request.app.state.cms

    kb = await svc.get_kb(kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail=f"Course {kb_id!r} not found")

    await svc.update_kb_field(kb_id, "approval_status", "rejected")
    await svc.update_kb_field(kb_id, "rejection_reason", body.reason)

    actor_id = getattr(getattr(request.state, "user", None), "sub", "system")
    await _emit_kafka_event("course-approval-events", {
        "event_type": "course.approval.completed",
        "actor_id":   actor_id,
        "kb_id":      kb_id,
        "outcome":    "rejected",
        "reason":     body.reason,
    })

    return CourseActionResponse(kb_id=kb_id, approval_status="rejected",
                                message="Course rejected and creator will be notified")


@router.post("/{kb_id}/request-clarification", response_model=CourseActionResponse, dependencies=[_admin_guard])
async def request_clarification(
    kb_id: str,
    body: ClarificationRequest,
    request: Request,
) -> CourseActionResponse:
    """Ask the creator to clarify or revise their course submission."""
    svc = request.app.state.cms

    kb = await svc.get_kb(kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail=f"Course {kb_id!r} not found")

    await svc.update_kb_field(kb_id, "approval_status", "clarification_requested")
    await svc.update_kb_field(kb_id, "clarification_message", body.message)

    return CourseActionResponse(kb_id=kb_id, approval_status="clarification_requested",
                                message="Clarification requested from course creator")
