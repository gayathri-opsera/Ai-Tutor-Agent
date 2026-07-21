"""Session cache and repository abstractions and implementations."""
from __future__ import annotations

import json
import logging
import uuid
from typing import Protocol

from src.models import Message, Session

logger = logging.getLogger(__name__)


# ── Protocols ─────────────────────────────────────────────────────────────────


class SessionCache(Protocol):
    async def get(self, session_id: str) -> Session | None: ...
    async def set(self, session: Session) -> None: ...


class SessionRepository(Protocol):
    async def save_session(self, session: Session) -> None: ...
    async def save_message(self, session_id: str, message: Message) -> None: ...
    async def get_history(self, session_id: str) -> list[Message]: ...
    async def list_sessions(self, user_id: str) -> list[dict]: ...
    async def rename_session(self, session_id: str, title: str) -> bool: ...
    async def delete_session(self, session_id: str) -> bool: ...


# ── In-memory implementations ─────────────────────────────────────────────────


class InMemorySessionCache:
    def __init__(self) -> None:
        self._data: dict[str, Session] = {}

    async def get(self, session_id: str) -> Session | None:
        return self._data.get(session_id)

    async def set(self, session: Session) -> None:
        self._data[session.id] = session


class MockSessionRepository:
    def __init__(self) -> None:
        self.sessions: dict[str, Session] = {}

    async def save_session(self, session: Session) -> None:
        self.sessions[session.id] = session

    async def save_message(self, session_id: str, message: Message) -> None:
        s = self.sessions.setdefault(session_id, Session(id=session_id, user_id=""))
        s.messages.append(message)

    async def get_history(self, session_id: str) -> list[Message]:
        return self.sessions.get(session_id, Session(id=session_id, user_id="")).messages

    async def list_sessions(self, user_id: str) -> list[dict]:
        return [
            {"id": s.id, "title": s.title, "knowledge_base_id": s.knowledge_base_id}
            for s in self.sessions.values()
            if s.user_id == user_id
        ]

    async def rename_session(self, session_id: str, title: str) -> bool:
        s = self.sessions.get(session_id)
        if not s:
            return False
        s.title = title
        return True

    async def delete_session(self, session_id: str) -> bool:
        return self.sessions.pop(session_id, None) is not None


class DatabaseSessionRepository:
    """Persists chat sessions and messages to PostgreSQL."""

    def __init__(self, pool) -> None:
        self._pool = pool

    async def save_session(self, session: Session) -> None:
        try:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO chat_sessions (id, user_id, knowledge_base_id, title)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (id) DO UPDATE
                         SET title = EXCLUDED.title,
                          knowledge_base_id = EXCLUDED.knowledge_base_id
                    """,
                    session.id, session.user_id, session.knowledge_base_id, session.title,
                )
        except Exception as exc:
            logger.warning("Failed to persist session %s: %s", session.id, exc)

    async def save_message(self, session_id: str, message: Message) -> None:
        try:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO chat_messages (id, session_id, role, content, sources_json)
                    VALUES ($1, $2, $3, $4, $5::jsonb)
                    ON CONFLICT (id) DO NOTHING
                    """,
                    str(uuid.uuid4()), session_id, message.role, message.content,
                    json.dumps(message.sources),
                )
        except Exception as exc:
            logger.warning("Failed to persist message for session %s: %s", session_id, exc)

    async def get_history(self, session_id: str) -> list[Message]:
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT role, content, sources_json
                    FROM chat_messages
                    WHERE session_id = $1
                    ORDER BY created_at ASC
                    """,
                    session_id,
                )
            return [
                Message(
                    role=row["role"],
                    content=row["content"],
                    sources=row["sources_json"] or [],
                )
                for row in rows
            ]
        except Exception as exc:
            logger.warning("Failed to load history for session %s: %s", session_id, exc)
            return []

    async def list_sessions(self, user_id: str) -> list[dict]:
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT id, title, knowledge_base_id, created_at
                    FROM chat_sessions
                    WHERE user_id = $1
                    ORDER BY created_at DESC
                    LIMIT 50
                    """,
                    user_id,
                )
            return [
                {
                    "id": str(row["id"]),
                    "title": row["title"],
                    "knowledge_base_id": str(row["knowledge_base_id"]) if row["knowledge_base_id"] else None,
                }
                for row in rows
            ]
        except Exception as exc:
            logger.warning("Failed to list sessions for user %s: %s", user_id, exc)
            return []

    async def rename_session(self, session_id: str, title: str) -> bool:
        try:
            async with self._pool.acquire() as conn:
                result = await conn.execute(
                    "UPDATE chat_sessions SET title = $1 WHERE id = $2",
                    title, session_id,
                )
            return result == "UPDATE 1"
        except Exception as exc:
            logger.warning("Failed to rename session %s: %s", session_id, exc)
            return False

    async def delete_session(self, session_id: str) -> bool:
        """Hard-delete a session and its messages (CASCADE handles messages)."""
        try:
            async with self._pool.acquire() as conn:
                result = await conn.execute(
                    "DELETE FROM chat_sessions WHERE id = $1",
                    session_id,
                )
            return result == "DELETE 1"
        except Exception as exc:
            logger.warning("Failed to delete session %s: %s", session_id, exc)
            return False

    async def purge_old_sessions(self, retention_days: int = 7) -> int:
        """Delete chat sessions (and their messages via CASCADE) older than retention_days.

        Returns the number of sessions deleted.
        """
        try:
            async with self._pool.acquire() as conn:
                result = await conn.execute(
                    """
                    DELETE FROM chat_sessions
                    WHERE created_at < NOW() - ($1 || ' days')::INTERVAL
                    """,
                    str(retention_days),
                )
            deleted = int(result.split()[-1]) if result else 0
            if deleted:
                logger.info("Purged %d chat sessions older than %d days", deleted, retention_days)
            return deleted
        except Exception as exc:
            logger.warning("Failed to purge old sessions: %s", exc)
            return 0
