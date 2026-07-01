"""Assessment engine — PostgreSQL-backed."""
from __future__ import annotations

import json
import os
import uuid
from enum import Enum
from typing import Any

import asyncpg


class AssessmentType(str, Enum):
    PRE = "pre"
    POST = "post"
    QUIZ = "quiz"

DB_DSN = os.getenv(
    "DATABASE_URL",
    "postgresql://ai_tutor:ai_tutor_local_password@postgres:5432/ai_tutor",
)


class AssessmentService:
    def __init__(self, pool: asyncpg.Pool | None = None) -> None:
        self._pool = pool

    async def _get_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(dsn=DB_DSN, min_size=1, max_size=5)
        return self._pool

    async def create(self, title: str, assessment_type: str, questions: list[dict], knowledge_base_id: str = "") -> dict:
        pool = await self._get_pool()
        aid = str(uuid.uuid4())
        qs_json = json.dumps(questions)
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO local_assessments (id, knowledge_base_id, title, assessment_type, questions_json)
                VALUES ($1, $2, $3, $4, $5::jsonb)
                """,
                aid, knowledge_base_id, title, assessment_type, qs_json,
            )
        return {"id": aid, "title": title, "assessment_type": assessment_type, "question_count": len(questions)}

    async def get(self, assessment_id: str) -> dict | None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM local_assessments WHERE id = $1", assessment_id)
        if not row:
            return None
        d = dict(row)
        raw_qs = d.pop("questions_json", None) or []
        # asyncpg may return JSONB as a Python object or as a JSON string
        if isinstance(raw_qs, str):
            raw_qs = json.loads(raw_qs)
        d["questions"] = raw_qs
        return d

    async def list_by_kb(self, knowledge_base_id: str) -> list[dict]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, title, assessment_type, created_at FROM local_assessments WHERE knowledge_base_id = $1 ORDER BY created_at DESC",
                knowledge_base_id,
            )
        return [dict(r) for r in rows]

    async def list_all(self) -> list[dict]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, title, assessment_type, knowledge_base_id, created_at FROM local_assessments ORDER BY created_at DESC"
            )
        return [dict(r) for r in rows]

    async def submit(self, assessment_id: str, user_id: str, answers: dict[str, int]) -> dict[str, Any]:
        assessment = await self.get(assessment_id)
        if not assessment:
            raise ValueError("Assessment not found")

        questions = assessment["questions"]
        correct = 0
        for q in questions:
            q_id = str(q.get("id", ""))
            if answers.get(q_id) == q.get("correct_index"):
                correct += 1
        total = len(questions)
        score = correct / max(total, 1)

        pool = await self._get_pool()
        result_id = str(uuid.uuid4())
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO local_assessment_results (id, assessment_id, user_id, score, correct, total, answers_json)
                VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)
                """,
                result_id, assessment_id, user_id, score, correct, total, json.dumps(answers),
            )
        return {
            "result_id": result_id,
            "assessment_id": assessment_id,
            "score": round(score, 3),
            "correct": correct,
            "total": total,
            "percentage": round(score * 100, 1),
        }

    async def get_results(self, user_id: str) -> list[dict]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT r.id, r.assessment_id, r.score, r.correct, r.total, r.submitted_at,
                       a.title, a.assessment_type
                FROM local_assessment_results r
                JOIN local_assessments a ON a.id = r.assessment_id
                WHERE r.user_id = $1
                ORDER BY r.submitted_at DESC
                """,
                user_id,
            )
        return [dict(r) for r in rows]
