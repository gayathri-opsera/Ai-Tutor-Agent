"""Assessment unit tests — WO-022 coverage.

Tests cover:
- create, get, get_for_learner (correct answers stripped)
- submit with per-question feedback
- pre/post comparison
- LLM generation (mocked)
- API endpoints: /take, /submit, /compare, /generate
"""
from __future__ import annotations

import datetime
import json
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.service import AssessmentService, AssessmentType


# ── In-memory store ──────────────────────────────────────────────────────────

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

    async def execute(self, sql: str, *args):
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

    async def fetchrow(self, sql: str, *args):
        if "local_assessments WHERE id" in sql:
            return self._assessments.get(str(args[0]))
        return None

    async def fetch(self, sql: str, *args):
        # Normalise whitespace so multi-line SQL strings match reliably
        sql_flat = " ".join(sql.split())

        # Check more-specific patterns FIRST (JOIN queries before simple selects)
        if "local_assessment_results" in sql_flat and "assessment_type IN" in sql_flat:
            # pre/post comparison query (JOIN)
            uid = str(args[0])
            kb_filter = str(args[1]) if len(args) > 1 else None
            rows = []
            for r in self._results.values():
                if r["user_id"] == uid:
                    a = self._assessments.get(r["assessment_id"], {})
                    if a.get("assessment_type") in ("pre", "post"):
                        if kb_filter and a.get("knowledge_base_id") != kb_filter:
                            continue
                        rows.append({
                            **r,
                            "title": a.get("title", ""),
                            "assessment_type": a.get("assessment_type", ""),
                            "knowledge_base_id": a.get("knowledge_base_id", ""),
                        })
            return rows
        if "local_assessment_results" in sql_flat:
            # learner history query
            uid = str(args[0])
            rows = []
            for r in self._results.values():
                if r["user_id"] == uid:
                    a = self._assessments.get(r["assessment_id"], {})
                    rows.append({
                        **r,
                        "title": a.get("title", ""),
                        "assessment_type": a.get("assessment_type", ""),
                        "knowledge_base_id": a.get("knowledge_base_id", ""),
                    })
            return rows
        # Simple local_assessments queries (no results join)
        if "local_assessments" in sql_flat and "knowledge_base_id = $1" in sql_flat:
            kb = str(args[0])
            return [v for v in self._assessments.values() if v["knowledge_base_id"] == kb]
        if "local_assessments" in sql_flat and "ORDER BY" in sql_flat:
            return list(self._assessments.values())
        return []


def _sample_questions():
    return [
        {
            "id": "q1",
            "text": "What does Hallo mean?",
            "question_type": "multiple_choice",
            "options": ["Hello", "Goodbye", "Please", "Thank you"],
            "correct_index": 0,
        },
        {
            "id": "q2",
            "text": "What is Danke?",
            "question_type": "multiple_choice",
            "options": ["Hello", "Please", "Thank you", "Sorry"],
            "correct_index": 2,
        },
    ]


# ── Service unit tests ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_and_get():
    pool = _InMemoryPool()
    svc = AssessmentService(pool=pool)
    qs = _sample_questions()
    created = await svc.create("German Quiz", AssessmentType.PRE.value, qs, kb_id := "kb-001")
    assert created["question_count"] == 2

    full = await svc.get(created["id"])
    assert full is not None
    assert full["title"] == "German Quiz"
    assert len(full["questions"]) == 2
    # correct_index must be present for creator view
    assert "correct_index" in full["questions"][0]


@pytest.mark.asyncio
async def test_get_for_learner_strips_correct_index():
    pool = _InMemoryPool()
    svc = AssessmentService(pool=pool)
    qs = _sample_questions()
    created = await svc.create("Safe Quiz", AssessmentType.QUIZ.value, qs, "kb-002")

    learner_view = await svc.get_for_learner(created["id"])
    assert learner_view is not None
    for q in learner_view["questions"]:
        # correct_index MUST NOT be exposed to learners
        assert "correct_index" not in q
        assert "options" in q


@pytest.mark.asyncio
async def test_get_for_learner_not_found():
    pool = _InMemoryPool()
    svc = AssessmentService(pool=pool)
    result = await svc.get_for_learner("non-existent-id")
    assert result is None


@pytest.mark.asyncio
async def test_submit_perfect_score():
    pool = _InMemoryPool()
    svc = AssessmentService(pool=pool)
    qs = _sample_questions()
    created = await svc.create("Test", AssessmentType.POST.value, qs, "kb-003")

    result = await svc.submit(created["id"], "user-1", {"q1": 0, "q2": 2})
    assert result["score"] == 1.0
    assert result["correct"] == 2
    assert result["total"] == 2
    assert result["percentage"] == 100.0


@pytest.mark.asyncio
async def test_submit_partial_score():
    pool = _InMemoryPool()
    svc = AssessmentService(pool=pool)
    qs = _sample_questions()
    created = await svc.create("Test", AssessmentType.QUIZ.value, qs, "kb-004")

    result = await svc.submit(created["id"], "user-2", {"q1": 0, "q2": 0})  # q2 wrong
    assert result["correct"] == 1
    assert result["percentage"] == 50.0


@pytest.mark.asyncio
async def test_submit_returns_per_question_feedback():
    pool = _InMemoryPool()
    svc = AssessmentService(pool=pool)
    qs = _sample_questions()
    created = await svc.create("Feedback Test", AssessmentType.QUIZ.value, qs, "kb-005")

    result = await svc.submit(created["id"], "user-3", {"q1": 0, "q2": 0})
    assert "feedback_per_question" in result
    feedback = result["feedback_per_question"]
    assert len(feedback) == 2

    q1_fb = next(f for f in feedback if f["question_id"] == "q1")
    assert q1_fb["is_correct"] is True
    assert q1_fb["correct_answer"] == "Hello"

    q2_fb = next(f for f in feedback if f["question_id"] == "q2")
    assert q2_fb["is_correct"] is False
    assert q2_fb["correct_answer"] == "Thank you"
    assert q2_fb["submitted_answer"] == "Hello"


@pytest.mark.asyncio
async def test_submit_assessment_not_found():
    pool = _InMemoryPool()
    svc = AssessmentService(pool=pool)
    with pytest.raises(ValueError, match="Assessment not found"):
        await svc.submit("non-existent", "user-4", {})


@pytest.mark.asyncio
async def test_pre_post_comparison_no_data():
    pool = _InMemoryPool()
    svc = AssessmentService(pool=pool)
    result = await svc.get_pre_post_comparison("user-new", "kb-999")
    assert result["pre_score"] is None
    assert result["post_score"] is None
    assert result["improvement_percentage"] is None


@pytest.mark.asyncio
async def test_pre_post_comparison_with_data():
    pool = _InMemoryPool()
    svc = AssessmentService(pool=pool)

    pre = await svc.create("Pre", AssessmentType.PRE.value, _sample_questions(), "kb-comp")
    post = await svc.create("Post", AssessmentType.POST.value, _sample_questions(), "kb-comp")

    # Pre: 0% (all wrong)
    await svc.submit(pre["id"], "user-comp", {"q1": 3, "q2": 0})
    # Post: 100% (all correct)
    await svc.submit(post["id"], "user-comp", {"q1": 0, "q2": 2})

    comparison = await svc.get_pre_post_comparison("user-comp", "kb-comp")
    assert comparison["pre_score"] == 0.0
    assert comparison["post_score"] == 100.0
    assert comparison["improvement_percentage"] == 100.0
    assert comparison["has_improvement"] is True


@pytest.mark.asyncio
async def test_list_by_kb():
    pool = _InMemoryPool()
    svc = AssessmentService(pool=pool)
    await svc.create("A1", "quiz", _sample_questions(), "kb-list")
    await svc.create("A2", "pre", _sample_questions(), "kb-list")
    await svc.create("A3", "post", _sample_questions(), "kb-other")

    items = await svc.list_by_kb("kb-list")
    assert len(items) == 2


# ── API integration tests ─────────────────────────────────────────────────────

@pytest.fixture
def client_with_pool():
    pool = _InMemoryPool()
    app.state.assessment_service = AssessmentService(pool=pool)
    return pool


@pytest.mark.asyncio
async def test_api_create(client_with_pool):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/assessments",
            json={
                "title": "API Test",
                "assessment_type": "pre",
                "knowledge_base_id": "kb-api-1",
                "questions": _sample_questions(),
            },
        )
    assert resp.status_code == 201
    assert resp.json()["question_count"] == 2


@pytest.mark.asyncio
async def test_api_take_strips_correct_index(client_with_pool):
    pool = client_with_pool
    svc = AssessmentService(pool=pool)
    created = await svc.create("Take Test", "quiz", _sample_questions(), "kb-api-2")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(f"/api/v1/assessments/{created['id']}/take")
    assert resp.status_code == 200
    data = resp.json()
    for q in data["questions"]:
        assert "correct_index" not in q


@pytest.mark.asyncio
async def test_api_take_not_found(client_with_pool):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/assessments/bad-id/take")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_api_submit_feedback(client_with_pool):
    pool = client_with_pool
    svc = AssessmentService(pool=pool)
    created = await svc.create("Submit Test", "quiz", _sample_questions(), "kb-api-3")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/assessments/{created['id']}/submit",
            json={"user_id": "api-user", "answers": {"q1": 0, "q2": 2}},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["percentage"] == 100.0
    assert "feedback_per_question" in data
    assert all(f["is_correct"] for f in data["feedback_per_question"])


@pytest.mark.asyncio
async def test_api_compare(client_with_pool):
    pool = client_with_pool
    svc = AssessmentService(pool=pool)
    pre = await svc.create("Pre", "pre", _sample_questions(), "kb-cmp")
    post = await svc.create("Post", "post", _sample_questions(), "kb-cmp")
    await svc.submit(pre["id"], "cmp-user", {"q1": 3, "q2": 0})
    await svc.submit(post["id"], "cmp-user", {"q1": 0, "q2": 2})

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/assessments/compare/cmp-user",
            params={"knowledge_base_id": "kb-cmp"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["improvement_percentage"] == 100.0


@pytest.mark.asyncio
async def test_api_generate_returns_502_on_empty(client_with_pool):
    """When LLM returns no questions the endpoint should return 502."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        with patch.object(
            AssessmentService, "generate_questions", new_callable=AsyncMock, return_value=[]
        ):
            resp = await client.post(
                "/api/v1/assessments/generate",
                json={
                    "knowledge_base_id": "kb-gen",
                    "topic": "German",
                    "count": 3,
                    "difficulty": "easy",
                    "auto_create": True,
                },
            )
    assert resp.status_code == 502


@pytest.mark.asyncio
async def test_api_list_all(client_with_pool):
    pool = client_with_pool
    svc = AssessmentService(pool=pool)
    await svc.create("All-1", "pre", _sample_questions(), "kb-all-1")
    await svc.create("All-2", "post", _sample_questions(), "kb-all-2")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/assessments")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 2


@pytest.mark.asyncio
async def test_api_results(client_with_pool):
    pool = client_with_pool
    svc = AssessmentService(pool=pool)
    created = await svc.create("Hist", "quiz", _sample_questions(), "kb-hist")
    await svc.submit(created["id"], "hist-user", {"q1": 0, "q2": 2})

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/assessments/results/hist-user")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["results"]) == 1


@pytest.mark.asyncio
async def test_fetch_kb_context_fallback():
    """_fetch_kb_context falls back to DB query when RAG is unavailable."""
    pool = _InMemoryPool()
    # Add a fake document row that the fallback DB query would return
    pool._documents = [{"content_text": "Hallo means Hello in German"}]

    original_fetch = pool.fetch

    async def patched_fetch(sql, *args):
        if "documents" in sql:
            return pool._documents
        return await original_fetch(sql, *args)

    pool.fetch = patched_fetch
    svc = AssessmentService(pool=pool)

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post.side_effect = Exception("no RAG")
        context = await svc._fetch_kb_context("kb-fallback", "German vocabulary")

    # Should return text from the fallback DB path or the default
    assert isinstance(context, str)
    assert len(context) > 0


class _MockHttpxClient:
    """Minimal async context manager that mimics httpx.AsyncClient."""
    def __init__(self, status_code: int = 200, payload: dict | None = None, raise_exc: Exception | None = None):
        self._status_code = status_code
        self._payload = payload or {}
        self._raise_exc = raise_exc

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass

    async def post(self, *args, **kwargs):
        if self._raise_exc:
            raise self._raise_exc
        return _MockResponse(self._status_code, self._payload)

    async def get(self, *args, **kwargs):
        if self._raise_exc:
            raise self._raise_exc
        return _MockResponse(self._status_code, self._payload)


class _MockResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


@pytest.mark.asyncio
async def test_call_llm_json_parsing():
    """_call_llm parses plain JSON responses from the LLM gateway."""
    pool = _InMemoryPool()
    svc = AssessmentService(pool=pool)

    questions_json = json.dumps([
        {
            "id": "q1", "text": "What is 2+2?",
            "question_type": "multiple_choice",
            "options": ["3", "4", "5", "6"], "correct_index": 1,
        }
    ])

    with patch("src.service.httpx.AsyncClient", return_value=_MockHttpxClient(200, {"content": questions_json})):
        result = await svc._call_llm("generate a question")

    assert len(result) == 1
    assert result[0]["text"] == "What is 2+2?"


@pytest.mark.asyncio
async def test_call_llm_markdown_fenced_json():
    """_call_llm strips markdown code fences before parsing."""
    pool = _InMemoryPool()
    svc = AssessmentService(pool=pool)

    questions_json = json.dumps([
        {"id": "q1", "text": "Q?", "question_type": "multiple_choice",
         "options": ["A", "B"], "correct_index": 0}
    ])
    fenced = f"```json\n{questions_json}\n```"

    with patch("src.service.httpx.AsyncClient", return_value=_MockHttpxClient(200, {"content": fenced})):
        result = await svc._call_llm("generate")

    assert len(result) == 1


@pytest.mark.asyncio
async def test_call_llm_exception_returns_empty():
    """_call_llm returns [] on any HTTP error."""
    pool = _InMemoryPool()
    svc = AssessmentService(pool=pool)

    with patch("src.service.httpx.AsyncClient", return_value=_MockHttpxClient(raise_exc=Exception("timeout"))):
        result = await svc._call_llm("generate")

    assert result == []


@pytest.mark.asyncio
async def test_api_generate_creates_assessment(client_with_pool):
    """When LLM returns questions /generate should auto-create the assessment."""
    generated_qs = [
        {
            "id": str(uuid.uuid4()),
            "text": "Was ist Hallo?",
            "question_type": "multiple_choice",
            "options": ["Hello", "Goodbye", "Please", "Thanks"],
            "correct_index": 0,
        }
    ]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        with patch.object(
            AssessmentService, "generate_questions",
            new_callable=AsyncMock, return_value=generated_qs,
        ):
            resp = await client.post(
                "/api/v1/assessments/generate",
                json={
                    "knowledge_base_id": "kb-gen-2",
                    "topic": "German basics",
                    "count": 1,
                    "difficulty": "easy",
                    "auto_create": True,
                },
            )
    assert resp.status_code == 201
    data = resp.json()
    assert "id" in data
    assert data["question_count"] == 1
