"""Chat orchestrator service — connects sessions to LLM Gateway + RAG pipeline."""
from __future__ import annotations

import json
import logging
import uuid
from typing import AsyncIterator

import httpx

from agent import ReasonRequest  # shared contract from libs/contracts (WO-015)
from grader import EvaluateRequest  # shared contract from libs/contracts (WO-015)
from llm import CompletionRequest, Message as LLMMessage, MessageRole, ModelTier  # shared contracts (WO-014)
from src.models import (
    ANALYTICS_SERVICE_URL,
    GRADER_SERVICE_URL,
    KB_SYSTEM_PROMPT,
    LEARNER_PROFILE_URL,
    LLM_GATEWAY_URL,
    SYSTEM_PROMPT,
    _GROUNDING_THRESHOLD,
    _NO_EVIDENCE_RESPONSE,
    Message,
    Session,
)
from src.rag_client import _demo_answer, _fetch_rag_context, _fetch_web_context
from src.repository import (
    DatabaseSessionRepository,
    InMemorySessionCache,
    MockSessionRepository,
    SessionCache,
    SessionRepository,
)

logger = logging.getLogger(__name__)


class ChatOrchestratorService:
    def __init__(
        self,
        cache: SessionCache,
        repository: SessionRepository,
        llm_gateway_url: str = LLM_GATEWAY_URL,
    ) -> None:
        self._cache = cache
        self._repository = repository
        self.llm_gateway_url = llm_gateway_url.rstrip("/")

    # ── Public session management API ─────────────────────────────────────────

    async def create_session(
        self, user_id: str, knowledge_base_id: str | None = None
    ) -> Session:
        session = Session(id=str(uuid.uuid4()), user_id=user_id, knowledge_base_id=knowledge_base_id)
        await self._cache.set(session)
        await self._repository.save_session(session)
        await self._fire_analytics("session.created", user_id, {"session_id": session.id, "knowledge_base_id": knowledge_base_id})
        await self._post_best_effort(f"{LEARNER_PROFILE_URL}/api/v1/learner/session", params={"user_id": user_id})
        return session

    async def _fire_analytics(self, event_type: str, user_id: str, metadata: dict) -> None:
        await self._post_best_effort(
            f"{ANALYTICS_SERVICE_URL}/api/v1/analytics/events",
            json={"event_type": event_type, "user_id": user_id, "metadata": metadata},
        )

    @staticmethod
    async def _post_best_effort(url: str, **kwargs) -> None:
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                await client.post(url, **kwargs)
        except Exception:
            pass

    async def get_session(self, session_id: str) -> Session | None:
        """Return a session from cache, loading history from DB if not found."""
        session = await self._cache.get(session_id)
        if session:
            return session
        history = await self._repository.get_history(session_id)
        if history:
            session = Session(id=session_id, user_id="", messages=history)
            await self._cache.set(session)
            return session
        return None

    async def update_session(self, session: Session) -> None:
        """Persist session state to cache."""
        await self._cache.set(session)

    async def list_sessions(self, user_id: str) -> list[dict]:
        """Return all sessions for a user from the repository."""
        return await self._repository.list_sessions(user_id)

    async def rename_session(self, session_id: str, title: str) -> bool:
        """Rename a session in the repository. Returns False if not found."""
        return await self._repository.rename_session(session_id, title)

    async def get_history(self, session_id: str) -> list[Message]:
        """Return full message history for a session from the repository."""
        return await self._repository.get_history(session_id)

    # ── Prompt helpers ─────────────────────────────────────────────────────────

    def build_prompt(self, session: Session, rag_context: str) -> str:
        """Return a single string prompt combining history and RAG context (used in tests)."""
        last_user = next(
            (m.content for m in reversed(session.messages) if m.role == "user"), ""
        )
        parts = []
        if rag_context:
            parts.append(f"Context:\n{rag_context}")
        if last_user:
            parts.append(f"Question: {last_user}")
        return "\n\n".join(parts)

    @staticmethod
    def _chunk_has_grounding(rag_chunks: list[dict]) -> bool:
        """Return True if at least one chunk meets the minimum grounding threshold."""
        return any(float(c.get("score", 0.0)) >= _GROUNDING_THRESHOLD for c in rag_chunks)

    def _build_llm_messages(
        self,
        session: Session,
        user_message: str,
        rag_context: str,
        has_grounding: bool = True,
    ) -> list[dict]:
        """Build the messages list for the LLM gateway request."""
        kb_scoped = bool(session.knowledge_base_id)
        if kb_scoped:
            system_content = KB_SYSTEM_PROMPT
            if rag_context:
                system_content += f"\n\n## Course Materials\n\n{rag_context}"
        else:
            system_content = SYSTEM_PROMPT
            if rag_context:
                system_content += f"\n\n## Retrieved Context\n\n{rag_context}"

        msgs: list[dict] = [{"role": "system", "content": system_content}]
        for m in session.messages[-10:]:
            msgs.append({"role": m.role, "content": m.content})
        msgs.append({"role": "user", "content": user_message})
        return msgs

    # ── Streaming response ─────────────────────────────────────────────────────

    async def stream_response(
        self,
        session_id: str,
        user_message: str,
        rag_chunks: list[dict] | None = None,
    ) -> AsyncIterator[str]:
        """Stream a response from Claude via the LLM Gateway."""
        session = await self._cache.get(session_id)
        if not session:
            session = Session(id=session_id, user_id="unknown")

        if rag_chunks is None:
            rag_chunks = await _fetch_rag_context(user_message, session.knowledge_base_id)

        kb_scoped = bool(session.knowledge_base_id)
        if not rag_chunks and not kb_scoped:
            web_chunks = await _fetch_web_context(user_message)
            if web_chunks:
                rag_chunks = web_chunks
                logger.debug("Web search returned %d chunks for query: %.60s", len(web_chunks), user_message)

        has_grounding = self._chunk_has_grounding(rag_chunks)
        rag_context = "\n\n".join(
            c.get("chunk_text", c.get("text", c.get("content", "")))
            for c in rag_chunks
        )
        sources = [
            {
                "chunk_id":       c.get("id", c.get("chunk_id", "")),
                "document_title": c.get("document_title", c.get("title", "Source")),
            }
            for c in rag_chunks
        ]

        session.messages.append(Message(role="user", content=user_message))

        if session.title in ("New Chat", "") and len(session.messages) == 1:
            raw = user_message.strip()
            if len(raw) > 60:
                auto_title = raw[:60].rstrip(" ,.;-") + "…"
            else:
                auto_title = raw
            session.title = auto_title
            await self._repository.rename_session(session_id, auto_title)

        await self._cache.set(session)

        llm_messages = self._build_llm_messages(session, user_message, rag_context, has_grounding)
        full_answer = ""
        llm_error = False
        try:
            # Build typed CompletionRequest — uses shared LLM contract (WO-014)
            completion_req = CompletionRequest(
                messages=[LLMMessage(role=MessageRole(m["role"]), content=m["content"]) for m in llm_messages],
                model_tier=ModelTier.STANDARD,
                max_tokens=2048,
                temperature=0.3,
            )
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream(
                    "POST",
                    f"{self.llm_gateway_url}/api/internal/llm/completions/stream",
                    json=completion_req.model_dump(mode="json"),
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        raw = line[len("data:"):].strip()
                        if raw == "[DONE]":
                            break
                        try:
                            chunk = json.loads(raw)
                            if chunk.get("finish_reason") == "error":
                                llm_error = True
                                logger.warning("LLM gateway error chunk: %s", chunk.get("error", ""))
                                break
                            delta = chunk.get("delta", "")
                            if delta:
                                full_answer += delta
                                yield (
                                    f"event: token\n"
                                    f"data: {json.dumps({'token': delta})}\n\n"
                                )
                        except json.JSONDecodeError:
                            continue
        except httpx.HTTPStatusError as exc:
            logger.error("LLM Gateway returned %d: %s", exc.response.status_code, exc.response.text)
            llm_error = True
        except Exception as exc:
            logger.error("LLM Gateway call failed: %s", exc)
            llm_error = True

        if llm_error:
            fallback = _demo_answer(user_message)
            full_answer = fallback
            for token in fallback.split(" "):
                yield f"event: token\ndata: {json.dumps({'token': token + ' '})}\n\n"
            rag_chunks = []

        confidence_score = 0.0 if not has_grounding else 0.8
        source_type = "documents" if has_grounding else "ai_knowledge"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                grade_resp = await client.post(
                    f"{GRADER_SERVICE_URL}/api/internal/grader/evaluate",
                    json=EvaluateRequest(answer=full_answer, chunks=rag_chunks).model_dump(),
                )
                if grade_resp.status_code == 200:
                    grade_data = grade_resp.json()
                    confidence_score = grade_data.get("confidence", confidence_score)
                    source_type      = grade_data.get("source_type", source_type)
        except Exception:
            pass

        if rag_chunks:
            grounded_sources = sources
            source_type = "documents"
        else:
            grounded_sources = []
            source_type = "ai_knowledge"

        yield f"event: sources\ndata: {json.dumps({'sources': grounded_sources, 'source_type': source_type})}\n\n"
        message_id = str(uuid.uuid4())
        yield f"event: done\ndata: {json.dumps({'message_id': message_id, 'confidence_score': confidence_score, 'source_type': source_type})}\n\n"

        session.messages.append(
            Message(role="assistant", content=full_answer, sources=grounded_sources)
        )
        await self._cache.set(session)
        await self._repository.save_message(session_id, session.messages[-1])

        await self._fire_analytics(
            "query.submitted", session.user_id,
            {"session_id": session_id, "knowledge_base_id": session.knowledge_base_id,
             "confidence": confidence_score, "source_type": source_type, "source_count": len(grounded_sources)},
        )
        await self._post_best_effort(
            f"{LEARNER_PROFILE_URL}/api/v1/learner/topic",
            params={"user_id": session.user_id},
            json={"topic": user_message[:80], "level": "in_progress",
                  "score": min(float(confidence_score), 0.9), "knowledge_base_id": session.knowledge_base_id},
        )
