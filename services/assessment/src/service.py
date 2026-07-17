"""Assessment engine — PostgreSQL-backed.

WO-022: Implements full assessment lifecycle per Forge spec:
- Multiple-choice auto-scoring with per-question feedback
- LLM-based question generation from knowledge base content
- Pre/post comparison tracking linked to learner profile
"""
from __future__ import annotations

import json
import os
import uuid
from enum import Enum
from typing import Any

import asyncpg
import httpx

DB_DSN = os.getenv(
    "DATABASE_URL",
    "postgresql://ai_tutor:ai_tutor_local_password@postgres:5432/ai_tutor"  # local-dev only — set DATABASE_URL in production,
)

# Internal service endpoints for LLM question generation
LLM_GATEWAY_URL = os.getenv("LLM_GATEWAY_URL", "http://llm-gateway:8004")
RAG_PIPELINE_URL = os.getenv("RAG_PIPELINE_URL", "http://rag-pipeline:8006")


class AssessmentType(str, Enum):
    PRE = "pre"
    POST = "post"
    QUIZ = "quiz"


class AssessmentService:
    def __init__(self, pool: asyncpg.Pool | None = None) -> None:
        self._pool = pool

    async def _get_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(dsn=DB_DSN, min_size=1, max_size=5)
        return self._pool

    # ── CRUD ────────────────────────────────────────────────────────────────────

    async def create(
        self,
        title: str,
        assessment_type: str,
        questions: list[dict],
        knowledge_base_id: str = "",
        answer_sheet: list[dict] | None = None,
    ) -> dict:
        pool = await self._get_pool()
        aid = str(uuid.uuid4())
        qs_json = json.dumps(questions)
        as_json = json.dumps(answer_sheet) if answer_sheet is not None else None
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO local_assessments
                  (id, knowledge_base_id, title, assessment_type, questions_json, answer_sheet_json)
                VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb)
                """,
                aid, knowledge_base_id, title, assessment_type, qs_json, as_json,
            )
        return {
            "id": aid,
            "title": title,
            "assessment_type": assessment_type,
            "question_count": len(questions),
            "has_answer_sheet": answer_sheet is not None,
        }

    async def get(self, assessment_id: str) -> dict | None:
        """Return assessment with correct answers — for admin/creator use."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM local_assessments WHERE id = $1", assessment_id
            )
        if not row:
            return None
        d = dict(row)
        raw_qs = d.pop("questions_json", None) or []
        if isinstance(raw_qs, str):
            raw_qs = json.loads(raw_qs)
        d["questions"] = raw_qs
        raw_as = d.pop("answer_sheet_json", None)
        if isinstance(raw_as, str):
            raw_as = json.loads(raw_as) if raw_as else None
        d["answer_sheet"] = raw_as
        return d

    async def get_for_learner(self, assessment_id: str) -> dict | None:
        """Return assessment with correct_index stripped — safe for learner delivery."""
        assessment = await self.get(assessment_id)
        if not assessment:
            return None
        sanitised = []
        for q in assessment.get("questions", []):
            sanitised.append({
                "id": q.get("id"),
                "text": q.get("text") or q.get("question_text", ""),
                "question_type": q.get("question_type", "multiple_choice"),
                "options": q.get("options", []),
            })
        return {
            "id": assessment["id"],
            "title": assessment["title"],
            "assessment_type": assessment["assessment_type"],
            "knowledge_base_id": assessment.get("knowledge_base_id", ""),
            "questions": sanitised,
        }

    async def list_by_kb(self, knowledge_base_id: str) -> list[dict]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, title, assessment_type, created_at
                FROM local_assessments
                WHERE knowledge_base_id = $1
                ORDER BY created_at DESC
                """,
                knowledge_base_id,
            )
        return [dict(r) for r in rows]

    async def list_all(self) -> list[dict]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, title, assessment_type, knowledge_base_id, created_at
                FROM local_assessments
                ORDER BY created_at DESC
                """
            )
        return [dict(r) for r in rows]

    # ── Submission & Scoring ────────────────────────────────────────────────────

    async def submit(
        self, assessment_id: str, user_id: str, answers: dict[str, int]
    ) -> dict[str, Any]:
        """Score an assessment and return per-question feedback."""
        assessment = await self.get(assessment_id)
        if not assessment:
            raise ValueError("Assessment not found")

        questions = assessment["questions"]
        correct = 0
        feedback_per_question: list[dict] = []

        for q in questions:
            q_id = str(q.get("id", ""))
            submitted_index = answers.get(q_id)
            correct_index = q.get("correct_index")
            is_correct = submitted_index == correct_index

            if is_correct:
                correct += 1

            options = q.get("options", [])
            feedback_per_question.append({
                "question_id": q_id,
                "question_text": q.get("text") or q.get("question_text", ""),
                "is_correct": is_correct,
                "submitted_index": submitted_index,
                "correct_index": correct_index,
                "correct_answer": options[correct_index] if correct_index is not None and correct_index < len(options) else None,
                "submitted_answer": options[submitted_index] if submitted_index is not None and submitted_index < len(options) else None,
            })

        total = len(questions)
        score = correct / max(total, 1)

        pool = await self._get_pool()
        result_id = str(uuid.uuid4())
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO local_assessment_results
                    (id, assessment_id, user_id, score, correct, total, answers_json)
                VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)
                """,
                result_id, assessment_id, user_id, score, correct, total,
                json.dumps(answers),
            )

        return {
            "result_id": result_id,
            "assessment_id": assessment_id,
            "score": round(score, 3),
            "correct": correct,
            "total": total,
            "percentage": round(score * 100, 1),
            "feedback_per_question": feedback_per_question,
        }

    async def get_results(self, user_id: str) -> list[dict]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT r.id, r.assessment_id, r.score, r.correct, r.total, r.submitted_at,
                       a.title, a.assessment_type, a.knowledge_base_id
                FROM local_assessment_results r
                JOIN local_assessments a ON a.id = r.assessment_id
                WHERE r.user_id = $1
                ORDER BY r.submitted_at DESC
                """,
                user_id,
            )
        return [dict(r) for r in rows]

    # ── Pre/Post Comparison ─────────────────────────────────────────────────────

    async def get_pre_post_comparison(
        self, user_id: str, knowledge_base_id: str | None = None
    ) -> dict:
        """Return pre vs post assessment improvement for a learner."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            query = """
                SELECT r.score, r.correct, r.total, r.submitted_at,
                       a.assessment_type, a.knowledge_base_id, a.title
                FROM local_assessment_results r
                JOIN local_assessments a ON a.id = r.assessment_id
                WHERE r.user_id = $1
                  AND a.assessment_type IN ('pre', 'post')
            """
            params: list = [user_id]
            if knowledge_base_id:
                query += " AND a.knowledge_base_id = $2"
                params.append(knowledge_base_id)
            query += " ORDER BY r.submitted_at ASC"
            rows = await conn.fetch(query, *params)

        pre_results = [dict(r) for r in rows if r["assessment_type"] == "pre"]
        post_results = [dict(r) for r in rows if r["assessment_type"] == "post"]

        pre_score = pre_results[-1]["score"] * 100 if pre_results else None
        post_score = post_results[-1]["score"] * 100 if post_results else None
        improvement = None
        if pre_score is not None and post_score is not None:
            improvement = round(post_score - pre_score, 1)

        return {
            "user_id": user_id,
            "knowledge_base_id": knowledge_base_id,
            "pre_score": round(pre_score, 1) if pre_score is not None else None,
            "post_score": round(post_score, 1) if post_score is not None else None,
            "improvement_percentage": improvement,
            "pre_attempts": len(pre_results),
            "post_attempts": len(post_results),
            "has_improvement": improvement is not None and improvement > 0,
        }

    # ── LLM-Based Question Generation ──────────────────────────────────────────

    async def generate_questions(
        self,
        knowledge_base_id: str,
        topic: str,
        count: int = 5,
        difficulty: str = "medium",
    ) -> list[dict]:
        """Generate multiple-choice questions from KB content using the LLM."""
        # Fetch relevant content from RAG pipeline
        context_text = await self._fetch_kb_context(knowledge_base_id, topic)

        prompt = f"""You are an expert at creating educational assessment questions.

Based on the following course content, generate exactly {count} multiple-choice questions at {difficulty} difficulty level about the topic: "{topic}".

COURSE CONTENT:
{context_text}

Return ONLY a valid JSON array (no markdown, no explanation) with this exact structure:
[
  {{
    "id": "q1",
    "text": "Question text here?",
    "question_type": "multiple_choice",
    "options": ["Option A", "Option B", "Option C", "Option D"],
    "correct_index": 0
  }}
]

Rules:
- Each question must have exactly 4 options
- correct_index is 0-based (0=A, 1=B, 2=C, 3=D)
- Questions must be directly answerable from the provided content
- Vary the position of the correct answer (don't always make it index 0)
- Make distractors plausible but clearly incorrect to someone who studied the material"""

        questions = await self._call_llm(prompt)
        # Assign stable UUIDs to generated questions
        for i, q in enumerate(questions):
            q["id"] = str(uuid.uuid4())
        return questions

    async def _fetch_kb_context(self, knowledge_base_id: str, topic: str) -> str:
        """Retrieve relevant content from the RAG pipeline for question generation."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{RAG_PIPELINE_URL}/api/v1/rag/retrieve",
                    json={
                        "query": topic,
                        "knowledge_base_id": knowledge_base_id,
                        "top_k": 5,
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    chunks = data.get("chunks", [])
                    return "\n\n".join(c.get("text", "") for c in chunks)
        except Exception:
            pass

        # Fallback: query DB for raw document text
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT content_text FROM documents
                WHERE knowledge_base_id = $1
                  AND status = 'active'
                  AND content_text IS NOT NULL
                ORDER BY created_at DESC
                LIMIT 3
                """,
                knowledge_base_id,
            )
        if rows:
            texts = [r["content_text"][:2000] for r in rows if r["content_text"]]
            return "\n\n".join(texts)
        return f"General knowledge about: {topic}"

    async def _call_llm(self, prompt: str) -> list[dict]:
        """Call the LLM Gateway for text generation; fall back to hardcoded sample."""
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{LLM_GATEWAY_URL}/api/internal/llm/generate",
                    json={
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": 2000,
                        "temperature": 0.3,
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    raw = data.get("content") or data.get("text", "")
                    # Strip markdown code fences if present
                    if "```" in raw:
                        raw = raw.split("```")[1]
                        if raw.startswith("json"):
                            raw = raw[4:]
                    return json.loads(raw.strip())
        except Exception:
            pass
        return []
