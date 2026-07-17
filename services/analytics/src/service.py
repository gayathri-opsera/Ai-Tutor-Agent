"""Analytics aggregation service — PostgreSQL-backed."""
from __future__ import annotations

import json
import os
import uuid
from typing import Any

import asyncpg

DB_DSN = os.getenv(
    "DATABASE_URL",
    "postgresql://ai_tutor:ai_tutor_local_password@postgres:5432/ai_tutor"  # local-dev only — set DATABASE_URL in production,
)


class AnalyticsService:
    def __init__(self, pool: asyncpg.Pool | None = None) -> None:
        self._pool = pool

    async def _get_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(dsn=DB_DSN, min_size=1, max_size=5)
        return self._pool

    async def consume(self, payload: dict) -> None:
        pool = await self._get_pool()
        event_id = str(uuid.uuid4())
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO local_analytics_events (id, event_type, user_id, topic, rating, metadata)
                VALUES ($1, $2, $3, $4, $5, $6::jsonb)
                """,
                event_id,
                payload.get("event_type", "unknown"),
                payload.get("user_id", ""),
                payload.get("topic", ""),
                payload.get("rating"),
                json.dumps(payload.get("metadata", {})),
            )

    async def summary(self) -> dict[str, Any]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            sessions = await conn.fetchval(
                "SELECT COUNT(*) FROM local_analytics_events WHERE event_type = 'session.created'"
            )
            queries = await conn.fetchval(
                "SELECT COUNT(*) FROM local_analytics_events WHERE event_type = 'query.submitted'"
            )
            avg_rating = await conn.fetchval(
                "SELECT AVG(rating) FROM local_analytics_events WHERE rating IS NOT NULL"
            )
            topic_rows = await conn.fetch(
                "SELECT topic, COUNT(*) as cnt FROM local_analytics_events WHERE topic != '' GROUP BY topic ORDER BY cnt DESC LIMIT 10"
            )
            recent = await conn.fetch(
                "SELECT event_type, user_id, topic, rating, created_at FROM local_analytics_events ORDER BY created_at DESC LIMIT 20"
            )
        return {
            "session_count": sessions or 0,
            "query_volume": queries or 0,
            "average_rating": round(float(avg_rating), 2) if avg_rating else 0.0,
            "topic_distribution": {r["topic"]: r["cnt"] for r in topic_rows},
            "recent_events": [dict(r) for r in recent],
        }

    async def creator_dashboard(self, creator_keycloak_id: str | None = None) -> dict[str, Any]:
        """Return per-course enrollment and progress metrics.

        If creator_keycloak_id is provided, filters to courses created by that user.
        Admins pass creator_keycloak_id=None to get all courses.
        """
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            filter_clause = (
                "AND kb.created_by_keycloak_id = $1"
                if creator_keycloak_id else ""
            )
            params = [creator_keycloak_id] if creator_keycloak_id else []

            courses = await conn.fetch(
                f"""
                SELECT
                    kb.id                                       AS knowledge_base_id,
                    kb.name                                     AS title,
                    kb.age_group,
                    kb.approval_status,
                    COUNT(DISTINCT ltp.user_id)                 AS enrollment_count,
                    COALESCE(AVG(ltp.completion_pct), 0)        AS avg_completion_pct,
                    COALESCE(AVG(ar.score), 0)                  AS avg_assessment_score
                FROM knowledge_bases kb
                LEFT JOIN learner_topic_progress ltp ON ltp.knowledge_base_id = kb.id
                LEFT JOIN assessments a ON a.knowledge_base_id = kb.id
                LEFT JOIN assessment_results ar ON ar.assessment_id = a.id
                WHERE kb.is_active = true {filter_clause}
                GROUP BY kb.id, kb.name, kb.age_group, kb.approval_status
                ORDER BY enrollment_count DESC
                """,
                *params,
            )

            total_enrollments = sum(int(r["enrollment_count"]) for r in courses)
            total_courses = len(courses)

        return {
            "total_courses":      total_courses,
            "total_enrollments":  total_enrollments,
            "courses": [
                {
                    "knowledge_base_id":   str(r["knowledge_base_id"]),
                    "title":               r["title"],
                    "age_group":           r["age_group"],
                    "approval_status":     str(r["approval_status"]),
                    "enrollment_count":    int(r["enrollment_count"]),
                    "avg_completion_pct":  round(float(r["avg_completion_pct"]), 1),
                    "avg_assessment_score": round(float(r["avg_assessment_score"]), 1),
                }
                for r in courses
            ],
        }

    async def admin_dashboard(self) -> dict[str, Any]:
        """Return platform-wide aggregate metrics for the admin dashboard."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            total_learners = await conn.fetchval(
                "SELECT COUNT(DISTINCT user_id) FROM learner_topic_progress"
            )
            total_courses = await conn.fetchval(
                "SELECT COUNT(*) FROM knowledge_bases WHERE is_active = true"
            )
            total_documents = await conn.fetchval(
                "SELECT COUNT(*) FROM documents WHERE status = 'active'"
            )
            total_chat_sessions = await conn.fetchval(
                "SELECT COUNT(*) FROM chat_sessions"
            )
            # Approval status distribution
            approval_rows = await conn.fetch(
                """
                SELECT approval_status::text, COUNT(*) AS cnt
                FROM knowledge_bases
                WHERE is_active = true
                GROUP BY approval_status
                """
            )
            # Top 10 most enrolled courses
            top_courses = await conn.fetch(
                """
                SELECT kb.name AS title, COUNT(DISTINCT ltp.user_id) AS enrollments
                FROM knowledge_bases kb
                LEFT JOIN learner_topic_progress ltp ON ltp.knowledge_base_id = kb.id
                WHERE kb.is_active = true AND kb.approval_status = 'approved'
                GROUP BY kb.id, kb.name
                ORDER BY enrollments DESC
                LIMIT 10
                """
            )

        return {
            "total_learners":       int(total_learners or 0),
            "total_courses":        int(total_courses or 0),
            "total_documents":      int(total_documents or 0),
            "total_chat_sessions":  int(total_chat_sessions or 0),
            "approval_status_distribution": {r["approval_status"]: int(r["cnt"]) for r in approval_rows},
            "top_courses_by_enrollment": [
                {"title": r["title"], "enrollments": int(r["enrollments"])}
                for r in top_courses
            ],
        }
