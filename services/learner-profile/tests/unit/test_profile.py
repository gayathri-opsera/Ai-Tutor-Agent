"""Learner profile unit tests — mocked asyncpg pool."""
import datetime
import uuid
import pytest
from httpx import ASGITransport, AsyncClient
from src.main import app
from src.service import LearnerProfileService


class _InMemoryPool:
    def __init__(self):
        self._profiles: dict[str, dict] = {}
        self._topics: dict[tuple, dict] = {}
        self._lessons: dict[tuple, dict] = {}

    def acquire(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass

    async def fetchrow(self, sql, *args):
        user_id = str(args[0]) if args else None
        if "local_learner_profiles" in sql and user_id:
            return self._profiles.get(user_id)
        if "local_topic_progress" in sql and len(args) >= 2:
            key = (str(args[0]), str(args[1]))
            row = self._topics.get(key)
            return {"id": row["id"]} if row else None
        return None

    async def fetch(self, sql, *args):
        user_id = str(args[0]) if args else None
        if "local_topic_progress" in sql and user_id:
            return [v for k, v in self._topics.items() if k[0] == user_id]
        if "local_lesson_progress" in sql and len(args) >= 2:
            uid, kb_id = str(args[0]), str(args[1])
            return [{"doc_id": v["doc_id"], "completed": v["completed"]}
                    for k, v in self._lessons.items() if k[0] == uid and k[1] == kb_id]
        return []

    async def execute(self, sql, *args):
        now = datetime.datetime.utcnow()
        if "CREATE TABLE IF NOT EXISTS local_lesson_progress" in sql:
            return  # DDL — no-op in tests
        if "INSERT INTO local_learner_profiles" in sql:
            uid = str(args[0])
            self._profiles[uid] = {
                "user_id": uid, "display_name": str(args[1]),
                "proficiency_level": "beginner", "preferences": {},
                "total_sessions": 0, "total_queries": 0,
                "created_at": now, "updated_at": now,
            }
        elif "UPDATE local_learner_profiles" in sql:
            uid = str(args[0])
            if uid in self._profiles:
                if "display_name" in sql:
                    if args[1]: self._profiles[uid]["display_name"] = str(args[1])
                    if args[2]: self._profiles[uid]["proficiency_level"] = str(args[2])
                if "total_queries" in sql:
                    self._profiles[uid]["total_queries"] += 1
                if "total_sessions" in sql:
                    self._profiles[uid]["total_sessions"] += 1
        elif "INSERT INTO local_topic_progress" in sql:
            tid, uid, topic = str(args[0]), str(args[1]), str(args[2])
            self._topics[(uid, topic)] = {
                "id": tid, "user_id": uid, "topic": topic,
                "status": str(args[3]), "score": float(args[4]),
                "question_count": 1, "knowledge_base_id": str(args[5]) if args[5] else None,
                "updated_at": now,
            }
        elif "UPDATE local_topic_progress" in sql:
            uid, topic = str(args[0]), str(args[1])
            if (uid, topic) in self._topics:
                self._topics[(uid, topic)]["status"] = str(args[2])
                self._topics[(uid, topic)]["score"] = float(args[3])
                self._topics[(uid, topic)]["question_count"] += 1
        elif "INSERT INTO local_lesson_progress" in sql:
            uid, kb_id, doc_id, completed = str(args[0]), str(args[1]), str(args[2]), bool(args[3])
            self._lessons[(uid, kb_id, doc_id)] = {"doc_id": doc_id, "completed": completed}
        elif "local_lesson_progress" in sql and "DO UPDATE" in sql:
            uid, kb_id, doc_id, completed = str(args[0]), str(args[1]), str(args[2]), bool(args[3])
            self._lessons[(uid, kb_id, doc_id)] = {"doc_id": doc_id, "completed": completed}


@pytest.mark.asyncio
async def test_profile_crud():
    pool = _InMemoryPool()
    app.state.profile_service = LearnerProfileService(pool=pool)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/learner/profile?user_id=test-user")
        assert resp.status_code == 200
        upd = await client.put(
            "/api/v1/learner/profile?user_id=test-user",
            json={"display_name": "Test User"},
        )
        assert upd.status_code == 200


@pytest.mark.asyncio
async def test_progress_tracking():
    pool = _InMemoryPool()
    svc = LearnerProfileService(pool=pool)
    await svc.update_topic("u1", "math", "mastered", 0.95)
    progress = await svc.get_progress("u1")
    assert "math" in progress["mastered"]


@pytest.mark.asyncio
async def test_lesson_progress_save_and_retrieve():
    pool = _InMemoryPool()
    svc = LearnerProfileService(pool=pool)
    await svc.save_lesson_progress("u1", "kb-1", "doc-1", completed=True)
    result = await svc.get_course_progress("u1", "kb-1")
    assert result["completed_count"] == 1
    assert "doc-1" in result["completed_doc_ids"]


@pytest.mark.asyncio
async def test_lesson_progress_toggle():
    pool = _InMemoryPool()
    svc = LearnerProfileService(pool=pool)
    # Mark complete then uncomplete
    await svc.save_lesson_progress("u1", "kb-1", "doc-1", completed=True)
    await svc.save_lesson_progress("u1", "kb-1", "doc-1", completed=False)
    result = await svc.get_course_progress("u1", "kb-1")
    assert result["completed_count"] == 0


@pytest.mark.asyncio
async def test_lesson_progress_api_endpoints():
    pool = _InMemoryPool()
    app.state.profile_service = LearnerProfileService(pool=pool)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Save lesson completion
        r1 = await client.post(
            "/api/v1/learner/lesson?user_id=u1",
            json={"kb_id": "kb-1", "doc_id": "doc-1", "completed": True},
        )
        assert r1.status_code == 200
        assert r1.json()["completed"] is True

        # Retrieve course progress
        r2 = await client.get("/api/v1/learner/course/kb-1/progress?user_id=u1")
        assert r2.status_code == 200
        data = r2.json()
        assert data["completed_count"] == 1
        assert "doc-1" in data["completed_doc_ids"]


@pytest.mark.asyncio
async def test_course_progress_empty():
    pool = _InMemoryPool()
    app.state.profile_service = LearnerProfileService(pool=pool)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/api/v1/learner/course/kb-empty/progress?user_id=u1")
        assert r.status_code == 200
        assert r.json()["completed_count"] == 0
