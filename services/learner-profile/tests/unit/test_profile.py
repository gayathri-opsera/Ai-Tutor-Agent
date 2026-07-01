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
        return []

    async def execute(self, sql, *args):
        now = datetime.datetime.utcnow()
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
