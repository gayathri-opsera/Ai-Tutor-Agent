"""Learner Profile Service — PostgreSQL-backed."""
from __future__ import annotations

import os
import uuid
from typing import Any

import asyncpg

DB_DSN = os.getenv(
    "DATABASE_URL",
    "postgresql://ai_tutor:ai_tutor_local_password@postgres:5432/ai_tutor",
)


class LearnerProfileService:
    def __init__(self, pool: asyncpg.Pool | None = None) -> None:
        self._pool = pool

    async def _pool_(self) -> asyncpg.Pool:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(dsn=DB_DSN, min_size=1, max_size=5)
        return self._pool

    async def get_or_create(self, user_id: str) -> dict[str, Any]:
        pool = await self._pool_()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM local_learner_profiles WHERE user_id = $1", user_id
            )
            if not row:
                await conn.execute(
                    """
                    INSERT INTO local_learner_profiles (user_id, display_name, proficiency_level, preferences)
                    VALUES ($1, $2, 'beginner', '{}')
                    ON CONFLICT (user_id) DO NOTHING
                    """,
                    user_id, user_id,
                )
                row = await conn.fetchrow(
                    "SELECT * FROM local_learner_profiles WHERE user_id = $1", user_id
                )
            return dict(row)

    async def update_profile(self, user_id: str, data: dict[str, Any]) -> dict[str, Any]:
        profile = await self.get_or_create(user_id)
        pool = await self._pool_()
        async with pool.acquire() as conn:
            if "display_name" in data or "proficiency_level" in data or "preferences" in data:
                await conn.execute(
                    """
                    UPDATE local_learner_profiles
                    SET display_name       = COALESCE($2, display_name),
                        proficiency_level  = COALESCE($3, proficiency_level),
                        preferences        = COALESCE($4::jsonb, preferences),
                        updated_at         = now()
                    WHERE user_id = $1
                    """,
                    user_id,
                    data.get("display_name"),
                    data.get("proficiency_level"),
                    str(data["preferences"]).replace("'", '"') if "preferences" in data else None,
                )
        return await self.get_or_create(user_id)

    async def update_topic(self, user_id: str, topic: str, level: str, score: float, kb_id: str | None = None) -> None:
        await self.get_or_create(user_id)
        pool = await self._pool_()
        async with pool.acquire() as conn:
            existing = await conn.fetchrow(
                "SELECT id FROM local_topic_progress WHERE user_id = $1 AND topic = $2",
                user_id, topic,
            )
            if existing:
                await conn.execute(
                    """
                    UPDATE local_topic_progress
                    SET status = $3, score = $4, question_count = question_count + 1,
                        knowledge_base_id = COALESCE($5, knowledge_base_id), updated_at = now()
                    WHERE user_id = $1 AND topic = $2
                    """,
                    user_id, topic, level, score, kb_id,
                )
            else:
                await conn.execute(
                    """
                    INSERT INTO local_topic_progress (id, user_id, topic, status, score, question_count, knowledge_base_id)
                    VALUES ($1, $2, $3, $4, $5, 1, $6)
                    """,
                    str(uuid.uuid4()), user_id, topic, level, score, kb_id,
                )
        # bump query count
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE local_learner_profiles SET total_queries = total_queries + 1, updated_at = now() WHERE user_id = $1",
                user_id,
            )

    async def _ensure_lesson_table(self, conn) -> None:
        """Create lesson progress table on first use (idempotent)."""
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS local_lesson_progress (
                id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id     TEXT NOT NULL,
                kb_id       TEXT NOT NULL,
                doc_id      TEXT NOT NULL,
                completed   BOOLEAN NOT NULL DEFAULT false,
                updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
                UNIQUE (user_id, kb_id, doc_id)
            )
            """
        )

    async def save_lesson_progress(
        self, user_id: str, kb_id: str, doc_id: str, completed: bool
    ) -> None:
        await self.get_or_create(user_id)
        pool = await self._pool_()
        async with pool.acquire() as conn:
            await self._ensure_lesson_table(conn)
            await conn.execute(
                """
                INSERT INTO local_lesson_progress (user_id, kb_id, doc_id, completed)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (user_id, kb_id, doc_id)
                DO UPDATE SET completed = $4, updated_at = now()
                """,
                user_id, kb_id, doc_id, completed,
            )

    async def get_course_progress(
        self, user_id: str, kb_id: str
    ) -> dict:
        pool = await self._pool_()
        async with pool.acquire() as conn:
            await self._ensure_lesson_table(conn)
            rows = await conn.fetch(
                """
                SELECT doc_id, completed, updated_at
                FROM local_lesson_progress
                WHERE user_id = $1 AND kb_id = $2
                """,
                user_id, kb_id,
            )
        lessons = [{"doc_id": str(r["doc_id"]), "completed": r["completed"]} for r in rows]
        completed_count = sum(1 for l in lessons if l["completed"])
        return {
            "user_id": user_id,
            "kb_id": kb_id,
            "lessons": lessons,
            "completed_doc_ids": [l["doc_id"] for l in lessons if l["completed"]],
            "completed_count": completed_count,
        }

    async def increment_session(self, user_id: str) -> None:
        await self.get_or_create(user_id)
        pool = await self._pool_()
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE local_learner_profiles SET total_sessions = total_sessions + 1, updated_at = now() WHERE user_id = $1",
                user_id,
            )

    async def get_progress(self, user_id: str) -> dict[str, Any]:
        profile = await self.get_or_create(user_id)
        pool = await self._pool_()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT topic, status, score, question_count, knowledge_base_id FROM local_topic_progress WHERE user_id = $1 ORDER BY updated_at DESC",
                user_id,
            )
        topics = [dict(r) for r in rows]
        return {
            "user_id": user_id,
            "display_name": profile["display_name"],
            "proficiency_level": profile["proficiency_level"],
            "total_sessions": profile["total_sessions"],
            "total_queries": profile["total_queries"],
            "mastered": [t["topic"] for t in topics if t["status"] == "mastered"],
            "in_progress": [t["topic"] for t in topics if t["status"] == "in_progress"],
            "not_started": [t["topic"] for t in topics if t["status"] == "not_started"],
            "topics": topics,
        }

    async def get_dashboard(self, user_id: str) -> dict[str, Any]:
        """Aggregate learner dashboard data for WO-247."""
        profile = await self.get_or_create(user_id)
        pool = await self._pool_()
        async with pool.acquire() as conn:
            # Assessment scores
            score_rows = await conn.fetch(
                """
                SELECT id AS assessment_id,
                       knowledge_base_id,
                       assessment_type,
                       created_at AS submitted_at,
                       COALESCE(
                         (SELECT AVG((answer->>'score')::numeric)
                          FROM jsonb_array_elements(COALESCE(questions_json::jsonb, '[]'::jsonb)) AS answer
                          WHERE answer->>'score' IS NOT NULL),
                         0
                       ) AS score
                FROM local_assessments
                WHERE id IN (
                    SELECT assessment_id FROM local_assessment_results WHERE user_id = $1
                )
                ORDER BY created_at DESC
                """,
                user_id,
            )
            # Lesson progress for completion %
            lesson_rows = await conn.fetch(
                "SELECT status FROM local_lesson_progress WHERE user_id = $1",
                user_id,
            )
            # Topic scores for topic breakdown
            topic_rows = await conn.fetch(
                "SELECT topic, score, knowledge_base_id FROM local_topic_progress WHERE user_id = $1",
                user_id,
            )

        total_lessons    = len(lesson_rows)
        completed_lessons = sum(1 for r in lesson_rows if r["status"] == "completed")
        overall_pct = round((completed_lessons / total_lessons) * 100, 1) if total_lessons else 0.0

        assessment_scores = [
            {
                "assessment_id":    str(r["assessment_id"]),
                "knowledge_base_id": str(r["knowledge_base_id"]) if r["knowledge_base_id"] else None,
                "score":             round(float(r["score"]), 1),
                "assessment_type":   r["assessment_type"],
                "submitted_at":      r["submitted_at"].isoformat() if r["submitted_at"] else None,
            }
            for r in score_rows
        ]

        return {
            "user_id":                    user_id,
            "overall_completion_percent": overall_pct,
            "assessment_scores":          assessment_scores,
            "time_on_platform_minutes":   int(profile.get("time_on_platform_minutes") or 0),
            "streak": {
                "current_streak_days": int(profile.get("current_streak_days") or 0),
                "longest_streak_days": int(profile.get("longest_streak_days") or 0),
                "last_active_date":    profile["last_active_date"].isoformat()
                                       if profile.get("last_active_date") else None,
            },
            "topic_progress": [
                {
                    "topic":            r["topic"],
                    "score":            round(float(r["score"]), 1),
                    "knowledge_base_id": str(r["knowledge_base_id"]) if r["knowledge_base_id"] else None,
                }
                for r in topic_rows
            ],
        }
