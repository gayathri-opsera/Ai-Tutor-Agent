"""Assessment API routes."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/assessments", tags=["assessments"])


class CreateAssessment(BaseModel):
    title: str
    assessment_type: str = "pre"
    knowledge_base_id: str = ""
    questions: list[dict]


class SubmitAnswers(BaseModel):
    user_id: str = "demo-user"
    answers: dict[str, int]


@router.post("", status_code=201)
async def create_assessment(body: CreateAssessment, request: Request):
    svc = request.app.state.assessment_service
    return await svc.create(body.title, body.assessment_type, body.questions, body.knowledge_base_id)


@router.get("")
async def list_assessments(knowledge_base_id: str | None = None, request: Request = None):
    svc = request.app.state.assessment_service
    if knowledge_base_id:
        items = await svc.list_by_kb(knowledge_base_id)
    else:
        items = await svc.list_all()
    return {"items": items, "total": len(items)}


@router.get("/{assessment_id}")
async def get_assessment(assessment_id: str, request: Request):
    svc = request.app.state.assessment_service
    result = await svc.get(assessment_id)
    if not result:
        raise HTTPException(404, "Assessment not found")
    return result


@router.post("/{assessment_id}/submit")
async def submit(assessment_id: str, body: SubmitAnswers, request: Request):
    svc = request.app.state.assessment_service
    try:
        return await svc.submit(assessment_id, body.user_id, body.answers)
    except ValueError as exc:
        raise HTTPException(404, str(exc))


@router.get("/results/{user_id}")
async def get_user_results(user_id: str, request: Request):
    svc = request.app.state.assessment_service
    results = await svc.get_results(user_id)
    return {"results": results}
