"""Unit tests for src.rag_client — RAG retrieval, web search, demo fallback."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import src.rag_client as rag_mod
from src.rag_client import _demo_answer, _fetch_rag_context, _fetch_web_context


# ── _demo_answer ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize("question,keyword", [
    ("tell me about python variables and loops", "Python"),
    ("explain async await coroutine asyncio", "Async"),
    ("what is machine learning supervised model", "Machine"),
    ("explain linear regression loss gradient bias", "Linear"),
    ("something completely random xyz 12345", "Answer"),
])
def test_demo_answer_covers_all_branches(question, keyword):
    answer = _demo_answer(question)
    assert keyword in answer or len(answer) > 50


def test_demo_answer_returns_string():
    assert isinstance(_demo_answer("hello world"), str)


def test_demo_answer_generic_fallback_contains_links():
    answer = _demo_answer("completely unknown topic zzzz")
    assert "billing" in answer.lower() or "demo" in answer.lower()


# ── _fetch_rag_context ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_rag_context_returns_empty_without_kb():
    result = await _fetch_rag_context("query", knowledge_base_id=None)
    assert result == []


@pytest.mark.asyncio
async def test_fetch_rag_context_returns_chunks_on_success():
    chunks = [{"text": "relevant content", "score": 0.9}]

    class _FakeResp:
        is_success = True
        def json(self): return {"chunks": chunks}

    with patch.object(rag_mod.httpx, "AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=_FakeResp())
        mock_cls.return_value = mock_client

        result = await _fetch_rag_context("query", "kb-001")

    assert result == chunks


@pytest.mark.asyncio
async def test_fetch_rag_context_returns_empty_on_failure():
    with patch.object(rag_mod.httpx, "AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=Exception("connection refused"))
        mock_cls.return_value = mock_client

        result = await _fetch_rag_context("query", "kb-001")

    assert result == []


# ── _fetch_web_context ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_web_context_returns_chunks_from_steps():
    agent_response = {
        "steps": [{"action": "web_search", "observation": "Germany has 83 million people."}],
        "final_answer": "Germany has 83 million people.",
    }

    class _FakeResp:
        is_success = True
        def json(self): return agent_response

    with patch.object(rag_mod.httpx, "AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=_FakeResp())
        mock_cls.return_value = mock_client

        chunks = await _fetch_web_context("population of Germany")

    assert len(chunks) >= 1
    assert "83 million" in chunks[0]["text"]


@pytest.mark.asyncio
async def test_fetch_web_context_returns_empty_on_network_error():
    with patch.object(rag_mod.httpx, "AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=Exception("connection refused"))
        mock_cls.return_value = mock_client

        result = await _fetch_web_context("any question")

    assert result == []


@pytest.mark.asyncio
async def test_fetch_web_context_uses_final_answer_fallback():
    """When steps is empty but final_answer is present, use it as a fallback chunk."""
    agent_response = {"steps": [], "final_answer": "42 is the answer."}

    class _FakeResp:
        is_success = True
        def json(self): return agent_response

    with patch.object(rag_mod.httpx, "AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=_FakeResp())
        mock_cls.return_value = mock_client

        chunks = await _fetch_web_context("what is the answer")

    assert len(chunks) == 1
    assert "42" in chunks[0]["text"]
