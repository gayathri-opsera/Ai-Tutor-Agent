"""Assessment API routes — WO-022 compliant.

Endpoints:
  POST   /api/v1/assessments                   — create assessment
  GET    /api/v1/assessments                   — list (filter by KB)
  POST   /api/v1/assessments/generate          — LLM question generation
  GET    /api/v1/assessments/{id}/take         — learner view (no correct answers)
  GET    /api/v1/assessments/{id}              — full view (admin/creator)
  POST   /api/v1/assessments/{id}/submit       — submit answers, get feedback
  GET    /api/v1/assessments/results/{user_id} — learner history
  GET    /api/v1/assessments/compare/{user_id} — pre/post comparison
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/assessments", tags=["assessments"])


# ── Request / Response models ────────────────────────────────────────────────

class CreateAssessment(BaseModel):
    title: str
    assessment_type: str = "pre"
    knowledge_base_id: str = ""
    questions: list[dict]
    answer_sheet: list[dict] | None = None


class GenerateRequest(BaseModel):
    knowledge_base_id: str
    topic: str
    count: int = Field(default=5, ge=1, le=20)
    difficulty: str = "medium"
    assessment_type: str = "quiz"
    auto_create: bool = True


class SubmitAnswers(BaseModel):
    user_id: str = "demo-user"
    answers: dict[str, int]


# ── Routes ───────────────────────────────────────────────────────────────────

@router.post("", status_code=201)
async def create_assessment(body: CreateAssessment, request: Request):
    svc = request.app.state.assessment_service
    return await svc.create(
        body.title, body.assessment_type, body.questions, body.knowledge_base_id,
        answer_sheet=body.answer_sheet,
    )


@router.get("")
async def list_assessments(
    knowledge_base_id: str | None = None, request: Request = None
):
    svc = request.app.state.assessment_service
    if knowledge_base_id:
        items = await svc.list_by_kb(knowledge_base_id)
    else:
        items = await svc.list_all()
    return {"items": items, "total": len(items)}


@router.post("/generate", status_code=201)
async def generate_assessment(body: GenerateRequest, request: Request):
    """LLM-based question generation from knowledge base content."""
    svc = request.app.state.assessment_service
    questions = await svc.generate_questions(
        body.knowledge_base_id, body.topic, body.count, body.difficulty
    )
    if not questions:
        raise HTTPException(502, "LLM did not return valid questions — try again or add more content to the knowledge base")

    if body.auto_create:
        result = await svc.create(
            title=f"{body.topic} — AI-Generated {body.assessment_type.title()} Assessment",
            assessment_type=body.assessment_type,
            questions=questions,
            knowledge_base_id=body.knowledge_base_id,
        )
        return {**result, "questions": questions}

    return {"questions": questions, "count": len(questions)}


@router.get("/results/{user_id}")
async def get_user_results(user_id: str, request: Request):
    svc = request.app.state.assessment_service
    results = await svc.get_results(user_id)
    return {"results": results}


@router.get("/compare/{user_id}")
async def get_pre_post_comparison(
    user_id: str,
    knowledge_base_id: str | None = None,
    request: Request = None,
):
    """Return pre/post comparison — improvement_percentage shows learning gain."""
    svc = request.app.state.assessment_service
    return await svc.get_pre_post_comparison(user_id, knowledge_base_id)


@router.get("/{assessment_id}/take")
async def take_assessment(assessment_id: str, request: Request):
    """Learner-safe endpoint — returns questions WITHOUT correct_index."""
    svc = request.app.state.assessment_service
    result = await svc.get_for_learner(assessment_id)
    if not result:
        raise HTTPException(404, "Assessment not found")
    return result


@router.get("/{assessment_id}")
async def get_assessment(assessment_id: str, request: Request):
    """Full assessment including correct answers — for admin/creator use."""
    svc = request.app.state.assessment_service
    result = await svc.get(assessment_id)
    if not result:
        raise HTTPException(404, "Assessment not found")
    return result


@router.post("/{assessment_id}/submit")
async def submit(assessment_id: str, body: SubmitAnswers, request: Request):
    """Score answers and return per-question feedback."""
    svc = request.app.state.assessment_service
    try:
        return await svc.submit(assessment_id, body.user_id, body.answers)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
