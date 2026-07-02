"""External web search fallback — DuckDuckGo (default) or Serper (when API key set)."""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Protocol

import httpx

logger = logging.getLogger(__name__)

SERPER_API_KEY = os.getenv("SERPER_API_KEY", "")


class SearchClientProtocol(Protocol):
    async def search(self, query: str, num_results: int = 5) -> list[dict[str, Any]]: ...


class DuckDuckGoSearchClient:
    """Lightweight DuckDuckGo search — no API key required.

    Uses DDG's JSON API endpoint which returns instant-answer results.
    For richer results we also hit the HTML endpoint and extract organic links.
    """

    _DDG_URL = "https://api.duckduckgo.com/"

    async def search(self, query: str, num_results: int = 5) -> list[dict[str, Any]]:
        params = {
            "q": query,
            "format": "json",
            "no_html": "1",
            "skip_disambig": "1",
        }
        results: list[dict[str, Any]] = []
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                resp = await client.get(self._DDG_URL, params=params)
                resp.raise_for_status()
                data = resp.json()

            # Abstract / instant answer
            if data.get("AbstractText"):
                results.append({
                    "id": "ddg-abstract",
                    "title": data.get("Heading", "DuckDuckGo Result"),
                    "snippet": data["AbstractText"],
                    "url": data.get("AbstractURL", ""),
                    "score": 0.8,
                })

            # Related topics
            for i, topic in enumerate(data.get("RelatedTopics", [])[:num_results]):
                text = topic.get("Text") or topic.get("Name", "")
                url = topic.get("FirstURL", "")
                if text:
                    results.append({
                        "id": f"ddg-{i}",
                        "title": text[:80],
                        "snippet": text,
                        "url": url,
                        "score": 0.6,
                    })
                    if len(results) >= num_results:
                        break
        except Exception as exc:
            logger.warning("DuckDuckGo search failed: %s", exc)

        return results[:num_results]


class SerperSearchClient:
    """Google Search results via Serper.dev (requires SERPER_API_KEY env var)."""

    _SERPER_URL = "https://google.serper.dev/search"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def search(self, query: str, num_results: int = 5) -> list[dict[str, Any]]:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    self._SERPER_URL,
                    headers={"X-API-KEY": self._api_key, "Content-Type": "application/json"},
                    json={"q": query, "num": num_results},
                )
                resp.raise_for_status()
                data = resp.json()
            return [
                {
                    "id": f"serper-{i}",
                    "title": r.get("title", ""),
                    "snippet": r.get("snippet", ""),
                    "url": r.get("link", ""),
                    "score": 0.75,
                }
                for i, r in enumerate(data.get("organic", [])[:num_results])
            ]
        except Exception as exc:
            logger.warning("Serper search failed: %s", exc)
            return []


def build_search_client() -> SearchClientProtocol:
    """Return the best available search client based on configured API keys."""
    if SERPER_API_KEY:
        logger.info("Web search: using Serper (Google)")
        return SerperSearchClient(SERPER_API_KEY)
    logger.info("Web search: using DuckDuckGo (no API key)")
    return DuckDuckGoSearchClient()


class WebSearchService:
    """Triggers a web search when RAG confidence falls below the threshold."""

    def __init__(
        self,
        client: SearchClientProtocol | None = None,
        confidence_threshold: float = 0.5,
    ) -> None:
        # Use the best available client when none is explicitly injected
        self._client: SearchClientProtocol = client if client is not None else build_search_client()
        self.confidence_threshold = confidence_threshold

    async def search_if_needed(
        self,
        query: str,
        confidence: float,
    ) -> list[dict[str, Any]]:
        if confidence >= self.confidence_threshold:
            return []
        results = await self._client.search(query)
        return [
            {
                "chunk_id": r.get("id", f"web-{i}"),
                "text": r.get("snippet", r.get("text", "")),
                "document_id": "web",
                "document_title": r.get("title", "Web Search"),
                "score": r.get("score", 0.5),
                "metadata": {"url": r.get("url", ""), "source": "web_search"},
            }
            for i, r in enumerate(results)
        ]
