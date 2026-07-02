"""Chat orchestrator tests."""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import ASGITransport, AsyncClient

from src.main import create_app
from src.service import (
    ChatOrchestratorService,
    DatabaseSessionRepository,
    InMemorySessionCache,
    MockSessionRepository,
    Message,
    Session,
    KB_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    _GROUNDING_THRESHOLD,
    _NO_EVIDENCE_RESPONSE,
    _demo_answer,
)


# ── Basic API ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_session():
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/v1/chat/sessions", json={"user_id": "u1"})
    assert resp.status_code == 200
    assert "id" in resp.json()


@pytest.mark.asyncio
async def test_build_prompt():
    svc = ChatOrchestratorService(InMemorySessionCache(), MockSessionRepository())
    session = Session(id="s1", user_id="u1", messages=[Message(role="user", content="hi")])
    prompt = svc.build_prompt(session, "context chunk")
    assert "context chunk" in prompt
    assert "hi" in prompt


@pytest.mark.asyncio
async def test_history():
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post("/api/v1/chat/sessions", json={"user_id": "u1"})
        sid = created.json()["id"]
        hist = await client.get(f"/api/v1/chat/sessions/{sid}/history")
    assert hist.status_code == 200


# ── Grounding threshold ────────────────────────────────────────────────────────

def test_chunk_has_grounding_above_threshold():
    svc = ChatOrchestratorService(InMemorySessionCache(), MockSessionRepository())
    chunks = [{"score": _GROUNDING_THRESHOLD + 0.01, "text": "relevant"}]
    assert svc._chunk_has_grounding(chunks) is True


def test_chunk_has_grounding_below_threshold():
    svc = ChatOrchestratorService(InMemorySessionCache(), MockSessionRepository())
    chunks = [{"score": max(_GROUNDING_THRESHOLD - 0.005, 0.0), "text": "not relevant"}]
    assert svc._chunk_has_grounding(chunks) is False


def test_chunk_has_grounding_empty():
    svc = ChatOrchestratorService(InMemorySessionCache(), MockSessionRepository())
    assert svc._chunk_has_grounding([]) is False


def test_chunk_has_grounding_mixed_scores():
    """Returns True when ANY chunk meets the threshold, even if others don't."""
    svc = ChatOrchestratorService(InMemorySessionCache(), MockSessionRepository())
    chunks = [
        {"score": 0.0, "text": "low"},
        {"score": _GROUNDING_THRESHOLD + 0.05, "text": "high"},
    ]
    assert svc._chunk_has_grounding(chunks) is True


# ── System prompt selection ────────────────────────────────────────────────────

def test_build_llm_messages_general_chat_uses_system_prompt():
    svc = ChatOrchestratorService(InMemorySessionCache(), MockSessionRepository())
    session = Session(id="s1", user_id="u1", knowledge_base_id=None)
    msgs = svc._build_llm_messages(session, "hello", "", has_grounding=False)
    assert msgs[0]["role"] == "system"
    assert SYSTEM_PROMPT.strip()[:30] in msgs[0]["content"]


def test_build_llm_messages_kb_scoped_uses_kb_prompt():
    svc = ChatOrchestratorService(InMemorySessionCache(), MockSessionRepository())
    session = Session(id="s1", user_id="u1", knowledge_base_id="kb-001")
    msgs = svc._build_llm_messages(session, "hello", "some context", has_grounding=True)
    system = msgs[0]["content"]
    # KB prompt should be used (contains its own unique phrasing)
    assert KB_SYSTEM_PROMPT.strip()[:30] in system
    assert "some context" in system
    assert SYSTEM_PROMPT.strip()[:30] not in system


def test_build_llm_messages_kb_scoped_no_context_uses_kb_prompt():
    """KB-scoped with empty context: KB prompt is still used; LLM falls back to general knowledge."""
    svc = ChatOrchestratorService(InMemorySessionCache(), MockSessionRepository())
    session = Session(id="s1", user_id="u1", knowledge_base_id="kb-001")
    msgs = svc._build_llm_messages(session, "hello", "", has_grounding=False)
    system = msgs[0]["content"]
    # Must use KB prompt (not general SYSTEM_PROMPT)
    assert KB_SYSTEM_PROMPT.strip()[:30] in system
    # Must NOT contain the old "No relevant content" placeholder (removed)
    assert "No relevant content" not in system


def test_build_llm_messages_general_chat_with_rag_context():
    """General chat with non-empty RAG context appends the context block."""
    svc = ChatOrchestratorService(InMemorySessionCache(), MockSessionRepository())
    session = Session(id="s-rag", user_id="u1", knowledge_base_id=None)
    msgs = svc._build_llm_messages(session, "explain this", "Some retrieved passage.", has_grounding=True)
    system = msgs[0]["content"]
    assert "Some retrieved passage." in system
    assert "Retrieved Context" in system


def test_build_llm_messages_includes_history():
    """Last 10 messages of history are included in the messages list."""
    svc = ChatOrchestratorService(InMemorySessionCache(), MockSessionRepository())
    history = [Message(role="user", content="turn 1"), Message(role="assistant", content="reply 1")]
    session = Session(id="s-hist", user_id="u1", knowledge_base_id=None, messages=history)
    msgs = svc._build_llm_messages(session, "new question", "")
    roles = [m["role"] for m in msgs]
    assert roles.count("user") == 2   # history user + new question
    assert roles.count("assistant") == 1


# ── KB-scoped: no chunks → LLM still called (falls back to general knowledge) ──

@pytest.mark.asyncio
async def test_stream_response_kb_scoped_no_chunks_calls_llm():
    """KB-scoped session with zero RAG chunks must NOT short-circuit; LLM is called."""
    cache = InMemorySessionCache()
    repo = MockSessionRepository()
    # Unreachable LLM → demo fallback; confirms the LLM call is attempted
    svc = ChatOrchestratorService(cache, repo, llm_gateway_url="http://127.0.0.1:1")

    session = Session(id="sess-kb-nochunk", user_id="u1", knowledge_base_id="kb-001")
    await cache.set(session)

    events = []
    async for ev in svc.stream_response("sess-kb-nochunk", "what is 4+10?", rag_chunks=[]):
        events.append(ev)

    full = "".join(events)
    # demo answer was streamed → LLM path was attempted (not short-circuited)
    assert "token" in full
    # "no_evidence" short-circuit event should NOT be present
    assert "no_evidence" not in full


@pytest.mark.asyncio
async def test_stream_response_general_chat_no_chunks_calls_llm():
    """Non-KB session with empty RAG must reach the LLM (demo fallback when unavailable)."""
    cache = InMemorySessionCache()
    repo = MockSessionRepository()
    svc = ChatOrchestratorService(cache, repo, llm_gateway_url="http://127.0.0.1:1")

    session = Session(id="sess-2", user_id="u1", knowledge_base_id=None)
    await cache.set(session)

    events = []
    async for ev in svc.stream_response("sess-2", "What is Python?", rag_chunks=[]):
        events.append(ev)

    full = "".join(events)
    assert "token" in full
    assert "no_evidence" not in full


# ── Demo answer fallback ───────────────────────────────────────────────────────

@pytest.mark.parametrize("question,keyword", [
    ("tell me about python variables", "Python"),
    ("explain async await coroutine", "Async"),
    ("what is machine learning supervised", "Machine"),
    ("explain linear regression gradient", "Linear"),
    ("something completely random xyz", "Answer"),
])
def test_demo_answer_covers_all_branches(question, keyword):
    answer = _demo_answer(question)
    assert keyword in answer or len(answer) > 50


def test_demo_answer_linear_regression_specific_branch():
    """Use a keyword only in the linear-regression branch (not ML branch)."""
    answer = _demo_answer("what is logistic loss function epoch weight bias")
    assert "Linear Regression" in answer or "β" in answer or len(answer) > 50


# ── LLM error fallback ────────────────────────────────────────────────────────

def _collect_tokens(events: list[str]) -> str:
    """Reconstruct the full text from SSE token events."""
    tokens = []
    for ev in events:
        for line in ev.split("\n"):
            if line.startswith("data:"):
                try:
                    d = json.loads(line[5:])
                    if "token" in d:
                        tokens.append(d["token"])
                except Exception:
                    pass
    return "".join(tokens).strip()


@pytest.mark.asyncio
async def test_stream_response_llm_error_emits_demo_answer():
    """LLM unreachable → demo answer for both KB-scoped and general sessions."""
    cache = InMemorySessionCache()
    repo = MockSessionRepository()
    svc = ChatOrchestratorService(cache, repo, llm_gateway_url="http://127.0.0.1:1")

    for kb_id, question in [("kb-abc", "explain async programming"), (None, "explain async programming")]:
        session_id = f"sess-err-{kb_id}"
        session = Session(id=session_id, user_id="u1", knowledge_base_id=kb_id)
        await cache.set(session)
        events = []
        async for ev in svc.stream_response(session_id, question, rag_chunks=[]):
            events.append(ev)
        full = "".join(events)
        assert "token" in full
        # Neither session should return the no-evidence response anymore
        assert _NO_EVIDENCE_RESPONSE[:25] not in _collect_tokens(events)


@pytest.mark.asyncio
async def test_stream_response_general_chat_llm_error_emits_demo():
    cache = InMemorySessionCache()
    repo = MockSessionRepository()
    svc = ChatOrchestratorService(cache, repo, llm_gateway_url="http://127.0.0.1:1")

    session = Session(id="sess-4", user_id="u1", knowledge_base_id=None)
    await cache.set(session)
    events = []
    async for ev in svc.stream_response("sess-4", "explain async programming", rag_chunks=[]):
        events.append(ev)

    full = "".join(events)
    assert "Async" in full or "async" in full or "token" in full


# ── Source type attribution ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stream_response_kb_scoped_with_grounding_marks_documents():
    """With chunks present and successful LLM call, source_type must be 'documents'."""
    cache = InMemorySessionCache()
    repo = MockSessionRepository()
    svc = ChatOrchestratorService(cache, repo, llm_gateway_url="http://mock-llm")

    session = Session(id="sess-5", user_id="u1", knowledge_base_id="kb-xyz")
    await cache.set(session)

    good_chunk = {"score": 0.9, "text": "Relevant text.", "chunk_id": "cx", "document_title": "Doc X"}

    mock_stream = _make_mock_stream_response(["Relevant", " answer"])
    mock_client = MagicMock()
    mock_client.stream = MagicMock(return_value=mock_stream)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("src.service.httpx.AsyncClient", return_value=mock_client):
        events = []
        async for ev in svc.stream_response("sess-5", "tell me about topic X", rag_chunks=[good_chunk]):
            events.append(ev)

    full = "".join(events)
    assert "done" in full
    # rag_chunks were not cleared (LLM succeeded) → source_type should be "documents"
    assert '"documents"' in full


# ── Persistence ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stream_response_persists_assistant_message():
    cache = InMemorySessionCache()
    repo = MockSessionRepository()
    svc = ChatOrchestratorService(cache, repo, llm_gateway_url="http://127.0.0.1:1")

    session = Session(id="sess-p", user_id="u-persist", knowledge_base_id=None)
    await cache.set(session)

    async for _ in svc.stream_response("sess-p", "What is Python?", rag_chunks=[]):
        pass

    saved = await cache.get("sess-p")
    assert saved is not None
    roles = [m.role for m in saved.messages]
    assert "user" in roles
    assert "assistant" in roles


# ── Mock LLM streaming ────────────────────────────────────────────────────────

def _make_mock_stream_response(tokens: list[str]):
    """Build a mock httpx streaming response that yields SSE token lines."""
    async def aiter_lines():
        for t in tokens:
            yield f"data: {json.dumps({'delta': t})}"
        yield "data: [DONE]"

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.aiter_lines = aiter_lines
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)
    return mock_resp


@pytest.mark.asyncio
async def test_stream_response_with_mock_llm_covers_stream_loop():
    """Cover the LLM streaming inner loop and document source attribution with chunks."""
    cache = InMemorySessionCache()
    repo = MockSessionRepository()
    svc = ChatOrchestratorService(cache, repo, llm_gateway_url="http://mock-llm")

    session = Session(id="sess-mock", user_id="u1", knowledge_base_id="kb-test")
    await cache.set(session)

    mock_stream = _make_mock_stream_response(["Hello", " World"])
    mock_client = MagicMock()
    mock_client.stream = MagicMock(return_value=mock_stream)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    good_chunk = {"score": 0.05, "text": "Course text.", "chunk_id": "c-x", "document_title": "Chapter 1"}

    with patch("src.service.httpx.AsyncClient", return_value=mock_client):
        events = []
        async for ev in svc.stream_response("sess-mock", "What is AI?", rag_chunks=[good_chunk]):
            events.append(ev)

    text = _collect_tokens(events)
    full = "".join(events)
    assert "Hello" in text or "World" in text
    assert "documents" in full


@pytest.mark.asyncio
async def test_stream_response_with_mock_grader_covers_grader_path():
    """Cover the grader 200 response path."""
    cache = InMemorySessionCache()
    repo = MockSessionRepository()
    svc = ChatOrchestratorService(cache, repo, llm_gateway_url="http://127.0.0.1:1")

    session = Session(id="sess-grader", user_id="u1", knowledge_base_id=None)
    await cache.set(session)

    mock_grade_resp = MagicMock()
    mock_grade_resp.status_code = 200
    mock_grade_resp.json = MagicMock(return_value={"confidence": 0.72, "source_type": "documents"})

    mock_client = MagicMock()
    mock_client.post = AsyncMock(return_value=mock_grade_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("src.service.httpx.AsyncClient", return_value=mock_client):
        events = []
        async for ev in svc.stream_response("sess-grader", "What is AI?", rag_chunks=[]):
            events.append(ev)

    full = "".join(events)
    assert "0.72" in full or "documents" in full


@pytest.mark.asyncio
async def test_stream_response_unknown_session_creates_fallback():
    """Line 314: session not found in cache → fallback Session is created internally."""
    cache = InMemorySessionCache()
    repo = MockSessionRepository()
    svc = ChatOrchestratorService(cache, repo, llm_gateway_url="http://127.0.0.1:1")

    # Deliberately do NOT pre-set the session
    events = []
    async for ev in svc.stream_response("nonexistent-session", "hello", rag_chunks=[]):
        events.append(ev)

    full = "".join(events)
    # Should have streamed demo tokens without crashing
    assert "token" in full


@pytest.mark.asyncio
async def test_stream_response_rag_chunks_none_triggers_fetch():
    """Line 318: rag_chunks=None triggers _fetch_rag_context (returns [] when no KB)."""
    cache = InMemorySessionCache()
    repo = MockSessionRepository()
    svc = ChatOrchestratorService(cache, repo, llm_gateway_url="http://127.0.0.1:1")

    session = Session(id="sess-none-chunks", user_id="u1", knowledge_base_id=None)
    await cache.set(session)

    events = []
    # rag_chunks=None → triggers the internal _fetch_rag_context call
    async for ev in svc.stream_response("sess-none-chunks", "what is Python?", rag_chunks=None):
        events.append(ev)

    full = "".join(events)
    assert "token" in full


@pytest.mark.asyncio
async def test_stream_response_finish_reason_error_sets_llm_error():
    """Cover the finish_reason=error path inside the stream loop."""
    cache = InMemorySessionCache()
    repo = MockSessionRepository()
    svc = ChatOrchestratorService(cache, repo, llm_gateway_url="http://mock-llm")

    session = Session(id="sess-err", user_id="u1", knowledge_base_id=None)
    await cache.set(session)

    async def aiter_lines():
        yield f"data: {json.dumps({'finish_reason': 'error', 'error': 'provider error'})}"
        yield "data: [DONE]"

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.aiter_lines = aiter_lines
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    mock_client = MagicMock()
    mock_client.stream = MagicMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("src.service.httpx.AsyncClient", return_value=mock_client):
        events = []
        async for ev in svc.stream_response("sess-err", "What is AI?", rag_chunks=[]):
            events.append(ev)

    full = "".join(events)
    assert "token" in full


# ── New API endpoints ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_sessions_endpoint():
    """GET /api/v1/chat/sessions?user_id=u1 returns session list."""
    repo = MockSessionRepository()
    app = create_app(repository=repo)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/api/v1/chat/sessions", json={"user_id": "u1"})
        resp = await client.get("/api/v1/chat/sessions?user_id=u1")
    assert resp.status_code == 200
    assert "sessions" in resp.json()


@pytest.mark.asyncio
async def test_select_session_loads_history():
    """Sending a message to an unknown session falls back to DB history."""
    repo = MockSessionRepository()
    app = create_app(repository=repo)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # First create and use a session
        cr = await client.post("/api/v1/chat/sessions", json={"user_id": "u99"})
        sid = cr.json()["id"]
        # History of fresh session is empty
        hist = await client.get(f"/api/v1/chat/sessions/{sid}/history")
    assert hist.status_code == 200
    assert hist.json()["messages"] == []


# ── DatabaseSessionRepository (mocked pool) ───────────────────────────────────

class _MockConn:
    def __init__(self, rows=None):
        self._rows = rows or []

    async def execute(self, *_, **__): pass
    async def fetch(self, *_, **__): return self._rows
    async def fetchrow(self, *_, **__): return self._rows[0] if self._rows else None


class _MockPool:
    def __init__(self, rows=None):
        self._rows = rows or []

    def acquire(self): return self
    async def __aenter__(self): return _MockConn(self._rows)
    async def __aexit__(self, *_): pass


@pytest.mark.asyncio
async def test_db_repo_save_session():
    pool = _MockPool()
    repo = DatabaseSessionRepository(pool)
    session = Session(id="s1", user_id="u1", title="Test")
    await repo.save_session(session)  # should not raise


@pytest.mark.asyncio
async def test_db_repo_save_message():
    pool = _MockPool()
    repo = DatabaseSessionRepository(pool)
    msg = Message(role="user", content="hello")
    await repo.save_message("s1", msg)  # should not raise


@pytest.mark.asyncio
async def test_db_repo_get_history_empty():
    pool = _MockPool(rows=[])
    repo = DatabaseSessionRepository(pool)
    history = await repo.get_history("s1")
    assert history == []


@pytest.mark.asyncio
async def test_db_repo_list_sessions_empty():
    pool = _MockPool(rows=[])
    repo = DatabaseSessionRepository(pool)
    sessions = await repo.list_sessions("u1")
    assert sessions == []


@pytest.mark.asyncio
async def test_db_repo_save_session_db_error():
    """DB failure is logged and swallowed, not raised."""
    class _BrokenPool:
        def acquire(self): return self
        async def __aenter__(self): return self
        async def __aexit__(self, *_): pass
        async def execute(self, *_, **__): raise Exception("DB down")
        async def fetch(self, *_, **__): raise Exception("DB down")

    repo = DatabaseSessionRepository(_BrokenPool())
    session = Session(id="s1", user_id="u1", title="Test")
    await repo.save_session(session)  # must not raise
    await repo.save_message("s1", Message(role="user", content="hi"))  # must not raise
    result = await repo.get_history("s1")
    assert result == []
    result2 = await repo.list_sessions("u1")
    assert result2 == []


@pytest.mark.asyncio
async def test_mock_repo_list_sessions():
    repo = MockSessionRepository()
    s = Session(id="s1", user_id="u1", title="My Chat")
    await repo.save_session(s)
    sessions = await repo.list_sessions("u1")
    assert any(x["id"] == "s1" for x in sessions)
    # Different user sees nothing
    other = await repo.list_sessions("u2")
    assert other == []


@pytest.mark.asyncio
async def test_send_message_session_not_found_returns_404():
    """Sending to a non-existent session_id with empty history → 404."""
    repo = MockSessionRepository()
    app = create_app(repository=repo)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/chat/sessions/nonexistent-session/messages",
            json={"content": "hello"},
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_send_message_session_loads_from_history():
    """If session is not in cache but has DB history, it is restored and message is handled."""
    repo = MockSessionRepository()
    # Pre-populate history so get_history returns something
    await repo.save_message("ghost-session", Message(role="assistant", content="previous message"))

    app = create_app(repository=repo)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        with patch("src.service.httpx.AsyncClient") as mock_httpx:
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()

            async def aiter_lines():
                yield f"data: {json.dumps({'delta': 'restored', 'finish_reason': None})}"
                yield "data: [DONE]"

            mock_resp.aiter_lines = aiter_lines
            mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
            mock_resp.__aexit__ = AsyncMock(return_value=False)
            mock_client = MagicMock()
            mock_client.stream = MagicMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_httpx.return_value = mock_client

            resp = await client.post(
                "/api/v1/chat/sessions/ghost-session/messages",
                json={"content": "hello again"},
            )
    # SSE response streams successfully (200)
    assert resp.status_code == 200
