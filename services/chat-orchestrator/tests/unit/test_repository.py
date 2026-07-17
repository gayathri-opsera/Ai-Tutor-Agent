"""Unit tests for src.repository — SessionCache and SessionRepository implementations."""
from __future__ import annotations

import pytest

from src.models import Message, Session
from src.repository import (
    DatabaseSessionRepository,
    InMemorySessionCache,
    MockSessionRepository,
)


# ── InMemorySessionCache ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cache_get_returns_none_for_missing():
    cache = InMemorySessionCache()
    result = await cache.get("nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_cache_set_and_get():
    cache = InMemorySessionCache()
    session = Session(id="s1", user_id="u1")
    await cache.set(session)
    retrieved = await cache.get("s1")
    assert retrieved is session


@pytest.mark.asyncio
async def test_cache_set_overwrites():
    cache = InMemorySessionCache()
    s1 = Session(id="s1", user_id="u1", title="Old")
    s2 = Session(id="s1", user_id="u1", title="New")
    await cache.set(s1)
    await cache.set(s2)
    result = await cache.get("s1")
    assert result.title == "New"


@pytest.mark.asyncio
async def test_cache_independent_sessions():
    cache = InMemorySessionCache()
    a = Session(id="a", user_id="u1")
    b = Session(id="b", user_id="u2")
    await cache.set(a)
    await cache.set(b)
    assert await cache.get("a") is a
    assert await cache.get("b") is b


# ── MockSessionRepository ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_mock_repo_save_and_get_history():
    repo = MockSessionRepository()
    await repo.save_message("s1", Message(role="user", content="hello"))
    history = await repo.get_history("s1")
    assert len(history) == 1
    assert history[0].content == "hello"


@pytest.mark.asyncio
async def test_mock_repo_get_history_empty():
    repo = MockSessionRepository()
    history = await repo.get_history("nonexistent")
    assert history == []


@pytest.mark.asyncio
async def test_mock_repo_save_session():
    repo = MockSessionRepository()
    s = Session(id="s1", user_id="u1", title="Chat 1")
    await repo.save_session(s)
    assert repo.sessions["s1"].title == "Chat 1"


@pytest.mark.asyncio
async def test_mock_repo_list_sessions_filters_by_user():
    repo = MockSessionRepository()
    s1 = Session(id="s1", user_id="alice")
    s2 = Session(id="s2", user_id="bob")
    await repo.save_session(s1)
    await repo.save_session(s2)
    alice_sessions = await repo.list_sessions("alice")
    assert len(alice_sessions) == 1
    assert alice_sessions[0]["id"] == "s1"
    bob_sessions = await repo.list_sessions("bob")
    assert len(bob_sessions) == 1
    assert bob_sessions[0]["id"] == "s2"


@pytest.mark.asyncio
async def test_mock_repo_list_sessions_empty_user():
    repo = MockSessionRepository()
    result = await repo.list_sessions("nobody")
    assert result == []


@pytest.mark.asyncio
async def test_mock_repo_rename_session_success():
    repo = MockSessionRepository()
    s = Session(id="s1", user_id="u1", title="Old")
    await repo.save_session(s)
    ok = await repo.rename_session("s1", "New Title")
    assert ok is True
    assert repo.sessions["s1"].title == "New Title"


@pytest.mark.asyncio
async def test_mock_repo_rename_session_not_found():
    repo = MockSessionRepository()
    ok = await repo.rename_session("ghost", "title")
    assert ok is False


@pytest.mark.asyncio
async def test_mock_repo_multiple_messages():
    repo = MockSessionRepository()
    for i in range(5):
        await repo.save_message("s1", Message(role="user", content=f"msg {i}"))
    history = await repo.get_history("s1")
    assert len(history) == 5
    assert history[4].content == "msg 4"


# ── DatabaseSessionRepository (mocked pool) ──────────────────────────────────


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


class _BrokenPool:
    def acquire(self): return self
    async def __aenter__(self): return self
    async def __aexit__(self, *_): pass
    async def execute(self, *_, **__): raise Exception("DB down")
    async def fetch(self, *_, **__): raise Exception("DB down")


@pytest.mark.asyncio
async def test_db_repo_save_session_no_raise():
    repo = DatabaseSessionRepository(_MockPool())
    await repo.save_session(Session(id="s1", user_id="u1", title="Test"))


@pytest.mark.asyncio
async def test_db_repo_save_message_no_raise():
    repo = DatabaseSessionRepository(_MockPool())
    await repo.save_message("s1", Message(role="user", content="hello"))


@pytest.mark.asyncio
async def test_db_repo_get_history_empty():
    repo = DatabaseSessionRepository(_MockPool(rows=[]))
    history = await repo.get_history("s1")
    assert history == []


@pytest.mark.asyncio
async def test_db_repo_list_sessions_empty():
    repo = DatabaseSessionRepository(_MockPool(rows=[]))
    sessions = await repo.list_sessions("u1")
    assert sessions == []


@pytest.mark.asyncio
async def test_db_repo_handles_db_errors_gracefully():
    repo = DatabaseSessionRepository(_BrokenPool())
    await repo.save_session(Session(id="s1", user_id="u1", title="Test"))
    await repo.save_message("s1", Message(role="user", content="hi"))
    assert await repo.get_history("s1") == []
    assert await repo.list_sessions("u1") == []
    assert await repo.rename_session("s1", "New") is False
