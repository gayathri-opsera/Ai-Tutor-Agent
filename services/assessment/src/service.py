"""Assessment engine."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AssessmentType(str, Enum):
    PRE = "pre"
    POST = "post"


@dataclass
class Question:
    id: str
    text: str
    options: list[str]
    correct_index: int


@dataclass
class Assessment:
    id: str
    title: str
    assessment_type: AssessmentType
    questions: list[Question] = field(default_factory=list)
    score: float | None = None
    submitted: bool = False


class AssessmentService:
    def __init__(self, store: dict[str, Assessment] | None = None) -> None:
        self._store = store if store is not None else {}

    def create(self, title: str, assessment_type: AssessmentType, questions: list[dict]) -> Assessment:
        aid = str(uuid.uuid4())
        qs = [
            Question(id=str(uuid.uuid4()), text=q["text"], options=q["options"], correct_index=q["correct_index"])
            for q in questions
        ]
        assessment = Assessment(id=aid, title=title, assessment_type=assessment_type, questions=qs)
        self._store[aid] = assessment
        return assessment

    def submit(self, assessment_id: str, answers: dict[str, int]) -> dict[str, Any]:
        assessment = self._store.get(assessment_id)
        if not assessment:
            raise ValueError("Assessment not found")
        correct = 0
        for q in assessment.questions:
            if answers.get(q.id) == q.correct_index:
                correct += 1
        score = correct / max(len(assessment.questions), 1)
        assessment.score = score
        assessment.submitted = True
        return {"assessment_id": assessment_id, "score": score, "correct": correct, "total": len(assessment.questions)}
