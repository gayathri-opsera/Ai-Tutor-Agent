"""Semantic cache with cosine similarity matching."""
from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any, Protocol


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(y * y for y in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


@dataclass
class CacheEntry:
    query: str
    embedding: list[float]
    response: Any
    expires_at: float


class SemanticCache(Protocol):
    async def check(self, embedding: list[float]) -> tuple[bool, Any | None, float]: ...
    async def store(self, query: str, embedding: list[float], response: Any, ttl_seconds: int) -> None: ...


class InMemorySemanticCache:
    """In-memory semantic cache for tests and local dev."""

    def __init__(self, similarity_threshold: float = 0.92) -> None:
        self.similarity_threshold = similarity_threshold
        self._entries: list[CacheEntry] = []

    async def check(self, embedding: list[float]) -> tuple[bool, Any | None, float]:
        now = time.time()
        best_score = 0.0
        best_response = None
        for entry in self._entries:
            if entry.expires_at <= now:
                continue
            score = cosine_similarity(embedding, entry.embedding)
            if score > best_score:
                best_score = score
                best_response = entry.response
        if best_score >= self.similarity_threshold:
            return True, best_response, best_score
        return False, None, best_score

    async def store(
        self,
        query: str,
        embedding: list[float],
        response: Any,
        ttl_seconds: int = 3600,
    ) -> None:
        self._entries.append(
            CacheEntry(
                query=query,
                embedding=embedding,
                response=response,
                expires_at=time.time() + ttl_seconds,
            )
        )

    def purge_expired(self) -> int:
        now = time.time()
        before = len(self._entries)
        self._entries = [e for e in self._entries if e.expires_at > now]
        return before - len(self._entries)
