"""Unit tests for the audit Kafka consumer's handle_event function (WO-182)."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.kafka_consumer import handle_event


def _pool_mock():
    """Return a mock asyncpg pool that tracks execute() calls."""
    conn = AsyncMock()
    conn.__aenter__ = AsyncMock(return_value=conn)
    conn.__aexit__ = AsyncMock(return_value=False)
    pool = MagicMock()
    pool.acquire.return_value = conn
    return pool, conn


@pytest.mark.asyncio
async def test_user_approval_completed_creates_audit_log():
    pool, conn = _pool_mock()
    payload = {
        "event_id":   "uuid-1",
        "event_type": "user.approval.completed",
        "timestamp":  "2026-07-17T00:00:00Z",
        "actor_id":   "admin-1",
        "user_id":    "user-uuid-1",
        "keycloak_id": "kc-user-1",
        "outcome":    "approved",
        "resource_type": "user",
        "roles_assigned": ["Learner"],
    }

    await handle_event(pool, json.dumps(payload).encode())

    conn.execute.assert_called_once()
    call_args = conn.execute.call_args
    # First positional arg is the SQL; remaining are the $1..$N values
    sql, log_id, action, actor_id, resource_id, resource_type, outcome, *_ = call_args.args
    assert action == "user.approval.completed"
    assert actor_id == "admin-1"
    assert resource_id == "user-uuid-1"
    assert resource_type == "user"
    assert outcome == "approved"


@pytest.mark.asyncio
async def test_course_approval_completed_creates_audit_log():
    pool, conn = _pool_mock()
    payload = {
        "event_type":    "course.approval.completed",
        "actor_id":      "admin-2",
        "kb_id":         "kb-uuid-1",
        "outcome":       "rejected",
        "reason":        "Policy violation",
        "resource_type": "course",
    }

    await handle_event(pool, json.dumps(payload).encode())

    conn.execute.assert_called_once()
    _, _, action, actor_id, resource_id, resource_type, outcome, *_ = conn.execute.call_args.args
    assert action == "course.approval.completed"
    assert actor_id == "admin-2"
    assert resource_id == "kb-uuid-1"
    assert outcome == "rejected"


@pytest.mark.asyncio
async def test_malformed_json_does_not_raise():
    pool, conn = _pool_mock()
    # Should log warning and return gracefully
    await handle_event(pool, b"{invalid json}")
    conn.execute.assert_not_called()


@pytest.mark.asyncio
async def test_missing_actor_defaults_to_system():
    pool, conn = _pool_mock()
    payload = {
        "event_type":    "user.approval.requested",
        "user_id":       "u-1",
        "keycloak_id":   "kc-1",
        "email_hash":    "abc",
        "resource_type": "user",
    }

    await handle_event(pool, json.dumps(payload).encode())

    _, _, action, actor_id, *_ = conn.execute.call_args.args
    assert actor_id == "system"
