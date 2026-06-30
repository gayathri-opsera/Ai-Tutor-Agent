"""External web search fallback."""
from __future__ import annotations

from typing import Any, Protocol


class SearchClientProtocol(Protocol):
    async def search(self, query: str, num_results: int = 5) -> list[dict[str, Any]]: ...


class WebSearchService:
    """Calls Serper/Brave Search API (mockable)."""

    def __init__(
        self,
        client: SearchClientProtocol | None = None,
        confidence_threshold: float = 0.5,
    ) -> None:
        self._client = client
        self.confidence_threshold = confidence_threshold

    async def search_if_needed(
        self,
        query: str,
        confidence: float,
    ) -> list[dict[str, Any]]:
        if confidence >= self.confidence_threshold:
            return []
        if self._client is None:
            return [{
                "chunk_id": "web-1",
                "text": f"Web result for: {query}",
                "document_id": "web",
                "document_title": "Web Search",
                "score": 0.6,
                "metadata": {"source": "web"},
            }]
        results = await self._client.search(query)
        return [
            {
                "chunk_id": r.get("id", f"web-{i}"),
                "text": r.get("snippet", r.get("text", "")),
                "document_id": "web",
                "document_title": r.get("title", "Web"),
                "score": r.get("score", 0.5),
                "metadata": {"url": r.get("url", "")},
            }
            for i, r in enumerate(results)
        ]
