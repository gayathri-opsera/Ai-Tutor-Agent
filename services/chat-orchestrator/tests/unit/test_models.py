"""Unit tests for src.models — domain types and configuration constants."""
from __future__ import annotations

from datetime import datetime

import pytest

from src.models import (
    KB_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    Message,
    Session,
    _GROUNDING_THRESHOLD,
    _NO_EVIDENCE_RESPONSE,
)


# ── Message serialization ─────────────────────────────────────────────────────


def test_message_defaults():
    msg = Message(role="user", content="hello")
    assert msg.role == "user"
    assert msg.content == "hello"
    assert msg.sources == []
    assert isinstance(msg.created_at, datetime)


def test_message_with_sources():
    sources = [{"chunk_id": "c1", "document_title": "Chapter 1"}]
    msg = Message(role="assistant", content="answer", sources=sources)
    assert msg.sources == sources


def test_message_roles():
    for role in ("user", "assistant", "system"):
        msg = Message(role=role, content="text")
        assert msg.role == role


# ── Session serialization ─────────────────────────────────────────────────────


def test_session_defaults():
    s = Session(id="s1", user_id="u1")
    assert s.id == "s1"
    assert s.user_id == "u1"
    assert s.knowledge_base_id is None
    assert s.messages == []
    assert s.title == "New Chat"


def test_session_with_kb():
    s = Session(id="s2", user_id="u2", knowledge_base_id="kb-001")
    assert s.knowledge_base_id == "kb-001"


def test_session_messages_are_independent():
    s1 = Session(id="s1", user_id="u1")
    s2 = Session(id="s2", user_id="u2")
    s1.messages.append(Message(role="user", content="hello"))
    assert s2.messages == [], "Sessions must not share default messages list"


# ── Constants ─────────────────────────────────────────────────────────────────


def test_grounding_threshold_is_non_negative():
    assert _GROUNDING_THRESHOLD >= 0.0


def test_no_evidence_response_is_non_empty():
    assert len(_NO_EVIDENCE_RESPONSE) > 0


def test_system_prompt_non_empty():
    assert "tutor" in SYSTEM_PROMPT.lower()


def test_kb_system_prompt_non_empty():
    assert "course" in KB_SYSTEM_PROMPT.lower() or "materials" in KB_SYSTEM_PROMPT.lower()
