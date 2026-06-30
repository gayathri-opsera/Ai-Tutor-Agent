from __future__ import annotations
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from src.service import AssessmentType

router = APIRouter(prefix="/api/v1/assessments", tags=["assessments"])

class CreateAssessment(BaseModel):
    title: str
    assessment_type: AssessmentType
    questions: list[dict]

class SubmitAnswers(BaseModel):
    answers: dict[str, int]

@router.post("")
async def create_assessment(body: CreateAssessment, request: Request):
    svc = request.app.state.assessment_service
    a = svc.create(body.title, body.assessment_type, body.questions)
    return {"id": a.id, "title": a.title, "question_count": len(a.questions)}

@router.post("/{assessment_id}/submit")
async def submit(assessment_id: str, body: SubmitAnswers, request: Request):
    svc = request.app.state.assessment_service
    try:
        return svc.submit(assessment_id, body.answers)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
