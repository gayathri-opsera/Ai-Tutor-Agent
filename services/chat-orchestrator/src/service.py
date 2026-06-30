"""Chat orchestrator service."""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Protocol


@dataclass
class Message:
    role: str
    content: str
    sources: list[dict] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class Session:
    id: str
    user_id: str
    knowledge_base_id: str | None = None
    messages: list[Message] = field(default_factory=list)
    title: str = "New Chat"


class SessionCache(Protocol):
    async def get(self, session_id: str) -> Session | None: ...
    async def set(self, session: Session) -> None: ...


class SessionRepository(Protocol):
    async def save_session(self, session: Session) -> None: ...
    async def save_message(self, session_id: str, message: Message) -> None: ...
    async def get_history(self, session_id: str) -> list[Message]: ...


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
        session = self.sessions.setdefault(session_id, Session(id=session_id, user_id=""))
        session.messages.append(message)

    async def get_history(self, session_id: str) -> list[Message]:
        return self.sessions.get(session_id, Session(id=session_id, user_id="")).messages


class ChatOrchestratorService:
    def __init__(
        self,
        cache: SessionCache,
        repository: SessionRepository,
        rag_url: str = "http://localhost:8010",
    ) -> None:
        self.cache = cache
        self.repository = repository
        self.rag_url = rag_url

    async def create_session(self, user_id: str, knowledge_base_id: str | None = None) -> Session:
        session = Session(id=str(uuid.uuid4()), user_id=user_id, knowledge_base_id=knowledge_base_id)
        await self.cache.set(session)
        await self.repository.save_session(session)
        return session

    def build_prompt(self, session: Session, rag_context: str) -> str:
        history = "\n".join(f"{m.role}: {m.content}" for m in session.messages[-10:])
        return f"Context:\n{rag_context}\n\nHistory:\n{history}\n\nAssistant:"

    async def stream_response(
        self,
        session_id: str,
        user_message: str,
        rag_chunks: list[dict] | None = None,
    ) -> AsyncIterator[str]:
        session = await self.cache.get(session_id)
        if not session:
            session = Session(id=session_id, user_id="unknown")
        session.messages.append(Message(role="user", content=user_message))
        context = "\n".join(c.get("text", "") for c in (rag_chunks or []))
        prompt = self.build_prompt(session, context)
        answer = f"Based on the provided context: {user_message[:50]}..."
        sources = rag_chunks or []
        for token in answer.split():
            yield f"event: token\ndata: {json.dumps({'token': token + ' '})}\n\n"
        yield f"event: sources\ndata: {json.dumps({'sources': sources})}\n\n"
        yield f"event: done\ndata: {json.dumps({'message_id': str(uuid.uuid4())})}\n\n"
        session.messages.append(Message(role="assistant", content=answer, sources=sources))
        await self.cache.set(session)
        await self.repository.save_message(session_id, session.messages[-1])
