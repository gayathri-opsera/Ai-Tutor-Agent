"""Chat orchestrator service — connects sessions to LLM Gateway + RAG pipeline."""
from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import AsyncIterator, Protocol

import httpx

logger = logging.getLogger(__name__)


def _demo_answer(question: str) -> str:
    """Return a rich educational fallback when the LLM backend is unavailable."""
    q = question.lower()

    if any(w in q for w in ["python", "variable", "function", "class", "loop", "list", "dict", "tuple"]):
        return (
            "## Python Overview\n\n"
            "Python is a **high-level, dynamically typed** language favoured for its readable syntax.\n\n"
            "### Key concepts\n"
            "- **Variables** — no declaration needed: `x = 42`\n"
            "- **Functions** — `def greet(name): return f'Hello, {name}'`\n"
            "- **Classes** — `class Dog: def __init__(self, name): self.name = name`\n"
            "- **Lists** — mutable sequences: `nums = [1, 2, 3]`\n"
            "- **Dicts** — key-value pairs: `person = {'name': 'Alice', 'age': 30}`\n\n"
            "```python\n# Quick example\nfor i in range(5):\n    print(f'Step {i}')\n```\n\n"
            "> **Note:** The AI backend is currently unavailable (check Anthropic billing at console.anthropic.com). This is a built-in demo answer."
        )

    if any(w in q for w in ["async", "await", "coroutine", "asyncio", "event loop", "non-blocking"]):
        return (
            "## Async Programming in Python\n\n"
            "Async lets you run **non-blocking I/O** in a single thread using `asyncio`.\n\n"
            "```python\nimport asyncio\n\nasync def fetch(url):\n    # await pauses this coroutine without blocking the thread\n    await asyncio.sleep(1)\n    return f'Response from {url}'\n\nasync def main():\n    result = await fetch('https://api.example.com')\n    print(result)\n\nasyncio.run(main())\n```\n\n"
            "**Use async for:** HTTP requests, DB queries, file I/O\n"
            "**Avoid for:** CPU-heavy tasks (use `multiprocessing` instead)\n\n"
            "> **Note:** The AI backend is temporarily unavailable (Anthropic billing needed). This is a built-in demo answer."
        )

    if any(w in q for w in ["machine learning", "ml", "model", "regression", "classification", "neural", "train", "supervised", "unsupervised"]):
        return (
            "## Machine Learning Basics\n\n"
            "Machine learning teaches computers to learn patterns from data without being explicitly programmed.\n\n"
            "### Main types\n"
            "| Type | How it works | Example |\n"
            "|------|--------------|---------|\n"
            "| **Supervised** | Learns from labelled data | Spam detection |\n"
            "| **Unsupervised** | Finds hidden structure | Customer clustering |\n"
            "| **Reinforcement** | Learns by reward/penalty | Game-playing AI |\n\n"
            "```python\nfrom sklearn.linear_model import LinearRegression\nmodel = LinearRegression()\nmodel.fit(X_train, y_train)\npredictions = model.predict(X_test)\n```\n\n"
            "> **Note:** The AI backend is temporarily unavailable (Anthropic billing needed). This is a built-in demo answer."
        )

    if any(w in q for w in ["linear regression", "logistic", "gradient", "loss", "epoch", "weight", "bias", "feature"]):
        return (
            "## Linear Regression\n\n"
            "Fits a line `y = β₀ + β₁x` by minimising the **Sum of Squared Residuals**.\n\n"
            "```python\nfrom sklearn.linear_model import LinearRegression\nimport numpy as np\n\nX = np.array([[1],[2],[3],[4],[5]])\ny = np.array([2, 4, 5, 4, 5])\nmodel = LinearRegression().fit(X, y)\nprint(f'Slope: {model.coef_[0]:.2f}, Intercept: {model.intercept_:.2f}')\n```\n\n"
            "**Key assumptions:** Linearity, independence, normality of residuals, homoscedasticity.\n\n"
            "> **Note:** The AI backend is temporarily unavailable (Anthropic billing needed). This is a built-in demo answer."
        )

    # Generic fallback
    return (
        f"## Answer to: *{question[:80]}*\n\n"
        "I can help you understand this topic! However, the AI backend is temporarily unavailable.\n\n"
        "**To enable live AI answers:**\n"
        "1. Go to **console.anthropic.com → Settings → Billing**\n"
        "2. Add a payment method and purchase credits\n"
        "3. The chatbot will automatically start giving real answers\n\n"
        "In the meantime, try asking about:\n"
        "- Python variables, functions, classes, loops\n"
        "- Async programming with asyncio\n"
        "- Machine learning concepts\n"
        "- Linear regression and classification\n\n"
        "> Built-in demo mode — real AI responses activate once billing is configured."
    )

LLM_GATEWAY_URL      = os.getenv("LLM_GATEWAY_URL",      "http://llm-gateway:8000")
RAG_SERVICE_URL      = os.getenv("RAG_SERVICE_URL",      "http://rag-pipeline:8002")
GRADER_SERVICE_URL   = os.getenv("GRADER_SERVICE_URL",   "http://confidence-grader:8006")
ANALYTICS_SERVICE_URL = os.getenv("ANALYTICS_SERVICE_URL", "http://analytics:8011")
LEARNER_PROFILE_URL  = os.getenv("LEARNER_PROFILE_URL",  "http://learner-profile:8008")

SYSTEM_PROMPT = """You are an expert AI tutor. You help learners understand complex topics clearly and concisely.

Guidelines:
- Give accurate, well-structured answers using Markdown formatting
- Use code examples when relevant (wrap in triple backticks with language tag)
- Use bullet points and headers to organise longer answers
- Cite the source document when you use retrieved context
- If you don't know something, say so rather than making things up
- Keep answers focused and educational
"""

# Used when the session is scoped to a knowledge base.
# Prefers course materials when relevant context is retrieved; falls back to
# general knowledge for factual/deterministic questions outside the KB scope.
# "I don't know" is reserved for questions that are genuinely unanswerable by
# either the course content OR general knowledge.
KB_SYSTEM_PROMPT = """You are an AI tutor for a specific course.

Answer priority — follow these rules IN ORDER:
1. If the "Course Materials" section below contains relevant content, answer from it and cite the document title.
2. ALWAYS answer from general knowledge for ANY factual, deterministic question you can reliably answer — this includes vocabulary, grammar, translation, mathematics, science, history, geography, and well-known facts — even if the course materials do not mention it. Add a brief note like "Note: This is general knowledge not covered in your course materials."
3. ONLY use "I don't know" for questions that are truly unanswerable even with general knowledge (e.g. personal opinions, unknowable future events, or highly specific proprietary information).

Key rule: Never refuse a question that has a well-known, reliable answer. When in doubt, answer from general knowledge and note the source.

Always be accurate. Never fabricate facts or invent content from the course materials.
"""

# Minimum cosine-similarity score for a chunk to be considered grounding evidence.
# Long document chunks score very low (~0.03-0.10) against short queries even when
# semantically relevant because the dense vector averages over many tokens.
# We set a very low floor here so that ANY retrieved chunk counts as grounding.
_GROUNDING_THRESHOLD = 0.01

# Kept for backwards-compat with tests; no longer used in the main flow.
_NO_EVIDENCE_RESPONSE = (
    "I don't know — this question doesn't appear to be covered by the course materials "
    "or my general knowledge."
)


# ── Domain types ──────────────────────────────────────────────────────────────

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


# ── Protocols ─────────────────────────────────────────────────────────────────

class SessionCache(Protocol):
    async def get(self, session_id: str) -> Session | None: ...
    async def set(self, session: Session) -> None: ...


class SessionRepository(Protocol):
    async def save_session(self, session: Session) -> None: ...
    async def save_message(self, session_id: str, message: Message) -> None: ...
    async def get_history(self, session_id: str) -> list[Message]: ...


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


# ── RAG retrieval (best-effort) ───────────────────────────────────────────────

async def _fetch_rag_context(
    query: str, knowledge_base_id: str | None, top_k: int = 5
) -> list[dict]:
    """Call the RAG pipeline to get relevant chunks. Returns [] on any failure."""
    if not knowledge_base_id:
        return []
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{RAG_SERVICE_URL}/api/internal/rag/retrieve",
                json={"query": query, "knowledge_base_id": knowledge_base_id, "top_k": top_k},
            )
            if resp.is_success:
                data = resp.json()
                return data.get("chunks", data.get("results", []))
    except Exception as exc:
        logger.debug("RAG retrieval skipped: %s", exc)
    return []


# ── Main service ──────────────────────────────────────────────────────────────

class ChatOrchestratorService:
    def __init__(
        self,
        cache: SessionCache,
        repository: SessionRepository,
        llm_gateway_url: str = LLM_GATEWAY_URL,
    ) -> None:
        self.cache = cache
        self.repository = repository
        self.llm_gateway_url = llm_gateway_url.rstrip("/")

    async def create_session(
        self, user_id: str, knowledge_base_id: str | None = None
    ) -> Session:
        session = Session(
            id=str(uuid.uuid4()),
            user_id=user_id,
            knowledge_base_id=knowledge_base_id,
        )
        await self.cache.set(session)
        await self.repository.save_session(session)
        # fire analytics (best-effort)
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                await client.post(
                    f"{ANALYTICS_SERVICE_URL}/api/v1/analytics/events",
                    json={
                        "event_type": "session.created",
                        "user_id": user_id,
                        "metadata": {"session_id": session.id, "knowledge_base_id": knowledge_base_id},
                    },
                )
        except Exception:
            pass
        return session

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
        """Build the messages list for the LLM gateway request.

        When the session is KB-scoped we use a strict grounding prompt so the
        LLM cannot answer from its training data.  When evidence is present we
        include the retrieved text; when it is absent the KB prompt's rule #3
        instructs the model to emit the 'I don't know' message.
        """
        kb_scoped = bool(session.knowledge_base_id)

        if kb_scoped:
            system_content = KB_SYSTEM_PROMPT
            if rag_context:
                system_content += f"\n\n## Course Materials\n\n{rag_context}"
            # When no chunks were retrieved the LLM falls back to general knowledge
            # per priority rule #2 in KB_SYSTEM_PROMPT.
        else:
            # General chat — allow the LLM to use its knowledge freely
            system_content = SYSTEM_PROMPT
            if rag_context:
                system_content += f"\n\n## Retrieved Context\n\n{rag_context}"

        msgs: list[dict] = [{"role": "system", "content": system_content}]

        # Include last 10 turns of history for context
        for m in session.messages[-10:]:
            msgs.append({"role": m.role, "content": m.content})

        msgs.append({"role": "user", "content": user_message})
        return msgs

    async def stream_response(
        self,
        session_id: str,
        user_message: str,
        rag_chunks: list[dict] | None = None,
    ) -> AsyncIterator[str]:
        """Stream a response from Claude via the LLM Gateway."""
        # 1. Load/create session
        session = await self.cache.get(session_id)
        if not session:
            session = Session(id=session_id, user_id="unknown")

        # 2. Fetch RAG context (use passed-in chunks first, then try live retrieval)
        if rag_chunks is None:
            rag_chunks = await _fetch_rag_context(user_message, session.knowledge_base_id)

        # 3. Pre-flight grounding check — must happen before the LLM call so we
        #    can short-circuit when evidence is absent in a KB-scoped session.
        has_grounding = self._chunk_has_grounding(rag_chunks)
        kb_scoped = bool(session.knowledge_base_id)

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

        # 4. Record user message
        session.messages.append(Message(role="user", content=user_message))
        await self.cache.set(session)

        # 5. Call LLM Gateway — streaming
        llm_messages = self._build_llm_messages(session, user_message, rag_context, has_grounding)
        full_answer = ""

        llm_error = False
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream(
                    "POST",
                    f"{self.llm_gateway_url}/api/internal/llm/completions/stream",
                    json={
                        "messages":    llm_messages,
                        "model_tier":  "standard",
                        "max_tokens":  2048,
                        # Lower temperature enforces closer adherence to context
                        "temperature": 0.3,
                    },
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
                            # Gateway signals a provider error (e.g. 429, 401) via finish_reason
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
            rag_chunks = []  # no document grounding for fallback answers

        # 7. Call confidence grader
        confidence_score = 0.0 if not has_grounding else 0.8
        source_type = "documents" if has_grounding else "ai_knowledge"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                grade_resp = await client.post(
                    f"{GRADER_SERVICE_URL}/api/internal/grader/evaluate",
                    json={"answer": full_answer, "chunks": rag_chunks},
                )
                if grade_resp.status_code == 200:
                    grade_data = grade_resp.json()
                    confidence_score = grade_data.get("confidence", confidence_score)
                    source_type      = grade_data.get("source_type", source_type)
        except Exception:
            pass

        # Attribute source_type based on whether RAG returned ANY chunks.
        # If the LLM received document context (rag_chunks non-empty), the answer
        # is document-grounded regardless of the cosine score — long chunks naturally
        # score low (~0.03-0.10) against short queries due to embedding averaging.
        if rag_chunks:
            # Include all retrieved sources; deduplicate in the frontend
            grounded_sources = sources
            source_type = "documents"
        else:
            grounded_sources = []
            source_type = "ai_knowledge"

        # 8. Emit sources + done (with confidence + source_type)
        yield f"event: sources\ndata: {json.dumps({'sources': grounded_sources, 'source_type': source_type})}\n\n"
        message_id = str(uuid.uuid4())
        yield f"event: done\ndata: {json.dumps({'message_id': message_id, 'confidence_score': confidence_score, 'source_type': source_type})}\n\n"

        # 9. Persist assistant message
        session.messages.append(
            Message(role="assistant", content=full_answer, sources=grounded_sources)
        )
        await self.cache.set(session)
        await self.repository.save_message(session_id, session.messages[-1])

        # 10. Fire analytics event (best-effort, don't await)
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                await client.post(
                    f"{ANALYTICS_SERVICE_URL}/api/v1/analytics/events",
                    json={
                        "event_type": "query.submitted",
                        "user_id": session.user_id,
                        "topic": user_message[:80],
                        "metadata": {
                            "session_id": session_id,
                            "knowledge_base_id": session.knowledge_base_id,
                            "confidence": confidence_score,
                            "source_type": source_type,
                            "source_count": len(grounded_sources),
                        },
                    },
                )
        except Exception:
            pass
