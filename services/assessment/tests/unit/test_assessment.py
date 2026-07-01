"""Assessment unit tests — mocked asyncpg pool."""
import json
import uuid
import pytest
from httpx import ASGITransport, AsyncClient
from src.main import app
from src.service import AssessmentService, AssessmentType


class _InMemoryPool:
    def __init__(self):
        self._assessments: dict[str, dict] = {}
        self._results: dict[str, dict] = {}

    def acquire(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass

    async def execute(self, sql, *args):
        import datetime
        now = datetime.datetime.utcnow()
        if "INSERT INTO local_assessments" in sql:
            aid, kb_id, title, atype, qs = (
                str(args[0]), str(args[1]), str(args[2]), str(args[3]), args[4]
            )
            self._assessments[aid] = {
                "id": aid, "knowledge_base_id": kb_id,
                "title": title, "assessment_type": atype,
                "questions_json": json.loads(qs) if isinstance(qs, str) else qs,
                "created_at": now, "updated_at": now,
            }
        elif "INSERT INTO local_assessment_results" in sql:
            rid, aid, uid, score, correct, total, answers = (
                str(args[0]), str(args[1]), str(args[2]),
                float(args[3]), int(args[4]), int(args[5]), args[6]
            )
            self._results[rid] = {
                "id": rid, "assessment_id": aid, "user_id": uid,
                "score": score, "correct": correct, "total": total,
                "answers_json": answers, "submitted_at": now,
            }

    async def fetchrow(self, sql, *args):
        if "local_assessments WHERE id" in sql:
            return self._assessments.get(str(args[0]))
        return None

    async def fetch(self, sql, *args):
        if "local_assessments WHERE knowledge_base_id" in sql:
            kb = str(args[0])
            return [v for v in self._assessments.values() if v["knowledge_base_id"] == kb]
        if "local_assessments ORDER" in sql:
            return list(self._assessments.values())
        if "local_assessment_results" in sql:
            uid = str(args[0])
            rows = []
            for r in self._results.values():
                if r["user_id"] == uid:
                    a = self._assessments.get(r["assessment_id"], {})
                    rows.append({**r, "title": a.get("title", ""), "assessment_type": a.get("assessment_type", "")})
            return rows
        return []


@pytest.mark.asyncio
async def test_score_calculation():
    pool = _InMemoryPool()
    svc = AssessmentService(pool=pool)
    questions = [{"id": "q1", "text": "2+2?", "options": ["3", "4"], "correct_index": 1}]
    created = await svc.create("Test", AssessmentType.PRE.value, questions)
    assert created["question_count"] == 1

    result = await svc.submit(created["id"], "test-user", {"q1": 1})
    assert result["score"] == 1.0
    assert result["correct"] == 1


@pytest.mark.asyncio
async def test_assessment_api():
    pool = _InMemoryPool()
    app.state.assessment_service = AssessmentService(pool=pool)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/assessments",
            json={
                "title": "Pre Test",
                "assessment_type": "pre",
                "questions": [{"text": "2+2?", "options": ["3", "4"], "correct_index": 1}],
            },
        )
    assert resp.status_code in (200, 201)
