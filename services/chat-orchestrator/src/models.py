"""Chat orchestrator domain models and service configuration."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone

# ── Service URL configuration ─────────────────────────────────────────────────

LLM_GATEWAY_URL       = os.getenv("LLM_GATEWAY_URL",       "http://llm-gateway:8000")
RAG_SERVICE_URL       = os.getenv("RAG_SERVICE_URL",       "http://rag-pipeline:8002")
GRADER_SERVICE_URL    = os.getenv("GRADER_SERVICE_URL",    "http://confidence-grader:8006")
ANALYTICS_SERVICE_URL = os.getenv("ANALYTICS_SERVICE_URL", "http://analytics:8011")
LEARNER_PROFILE_URL   = os.getenv("LEARNER_PROFILE_URL",   "http://learner-profile:8008")
AGENT_REASONING_URL   = os.getenv("AGENT_REASONING_URL",   "http://agent-reasoning:8005")

# ── System prompts ────────────────────────────────────────────────────────────

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
KB_SYSTEM_PROMPT = """You are an AI tutor for a specific course.

Answer priority — follow these rules IN ORDER:
1. If the "Course Materials" section below contains relevant content, answer from it and cite the document title. Do NOT add any "general knowledge" disclaimer.
2. If course materials were provided but don't directly answer the question, you may supplement with your general knowledge (vocabulary definitions, grammar, translations, math, science, etc.) — but do NOT say the topic is "not covered in course materials" since the learner is actively studying this course.
3. If NO course materials were provided at all, answer from general knowledge and add a brief note: "Note: This answer is from general knowledge."
4. ONLY use "I don't know" for questions that are truly unanswerable (personal opinions, unknowable future events, or highly specific proprietary information).

Key rules:
- Never add "Note: This is general knowledge not covered in your course materials" when course content was provided — it confuses learners who ARE studying the material.
- Never refuse a question that has a well-known, reliable answer.
- Never fabricate facts or invent content from the course materials.
"""

# ── Grounding configuration ───────────────────────────────────────────────────

# Minimum cosine-similarity score for a chunk to be considered grounding evidence.
# Long document chunks score very low (~0.03-0.10) against short queries even when
# semantically relevant because the dense vector averages over many tokens.
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
