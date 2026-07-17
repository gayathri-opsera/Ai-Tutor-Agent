"""Unit tests for answer_sheet_json support in assessment service (WO-163)."""
from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.assessment import router


def _make_app(svc_mock) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.assessment_service = svc_mock
        yield

    app = FastAPI(lifespan=lifespan)
    app.include_router(router)
    return app


SAMPLE_QUESTIONS = [
    {
        "id": "q1",
        "text": "What is a list in Python?",
        "options": ["A dict", "A sequence", "A set", "A tuple"],
        "correct_index": 1,
    }
]

SAMPLE_ANSWER_SHEET = [
    {
        "question_id": "q1",
        "correct_answer": "A sequence",
        "explanation": "A list is an ordered, mutable sequence.",
        "difficulty": "easy",
        "points": 1,
    }
]


def test_create_assessment_with_answer_sheet():
    svc = AsyncMock()
    svc.create.return_value = {
        "id": "a-1", "title": "Python Quiz", "assessment_type": "quiz",
        "question_count": 1, "has_answer_sheet": True,
    }
    app = _make_app(svc)

    with TestClient(app) as client:
        resp = client.post("/api/v1/assessments", json={
            "title": "Python Quiz",
            "assessment_type": "quiz",
            "knowledge_base_id": "kb-1",
            "questions": SAMPLE_QUESTIONS,
            "answer_sheet": SAMPLE_ANSWER_SHEET,
        })

    assert resp.status_code == 201
    data = resp.json()
    assert data["has_answer_sheet"] is True
    svc.create.assert_called_once_with(
        "Python Quiz", "quiz", SAMPLE_QUESTIONS, "kb-1",
        answer_sheet=SAMPLE_ANSWER_SHEET,
    )


def test_create_assessment_without_answer_sheet():
    svc = AsyncMock()
    svc.create.return_value = {
        "id": "a-2", "title": "No Sheet", "assessment_type": "pre",
        "question_count": 1, "has_answer_sheet": False,
    }
    app = _make_app(svc)

    with TestClient(app) as client:
        resp = client.post("/api/v1/assessments", json={
            "title": "No Sheet",
            "assessment_type": "pre",
            "knowledge_base_id": "kb-2",
            "questions": SAMPLE_QUESTIONS,
        })

    assert resp.status_code == 201
    svc.create.assert_called_once_with(
        "No Sheet", "pre", SAMPLE_QUESTIONS, "kb-2",
        answer_sheet=None,
    )


def test_get_assessment_returns_answer_sheet():
    svc = AsyncMock()
    svc.get.return_value = {
        "id": "a-1", "title": "Python Quiz", "assessment_type": "quiz",
        "knowledge_base_id": "kb-1",
        "questions": SAMPLE_QUESTIONS,
        "answer_sheet": SAMPLE_ANSWER_SHEET,
    }
    app = _make_app(svc)

    with TestClient(app) as client:
        resp = client.get("/api/v1/assessments/a-1")

    assert resp.status_code == 200
    data = resp.json()
    assert data["answer_sheet"] is not None
    assert data["answer_sheet"][0]["question_id"] == "q1"
    assert data["answer_sheet"][0]["explanation"] == "A list is an ordered, mutable sequence."
