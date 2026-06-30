"""URL content ingestion with robots.txt respect."""
from __future__ import annotations

import httpx
from bs4 import BeautifulSoup

from src.chunking import chunk_text


class URLIngestionService:
    def __init__(self, http_client: httpx.AsyncClient | None = None) -> None:
        self._http = http_client

    async def fetch_and_chunk(self, url: str) -> list[str]:
        client = self._http or httpx.AsyncClient(follow_redirects=True)
        close = self._http is None
        try:
            if not await self._allowed_by_robots(client, url):
                raise PermissionError(f"Blocked by robots.txt: {url}")
            resp = await client.get(url, timeout=30.0)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            for tag in soup(["script", "style", "nav", "footer"]):
                tag.decompose()
            text = soup.get_text(separator="\n", strip=True)
            return chunk_text(text)
        finally:
            if close:
                await client.aclose()

    async def _allowed_by_robots(self, client: httpx.AsyncClient, url: str) -> bool:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        try:
            resp = await client.get(robots_url, timeout=5.0)
            if resp.status_code != 200:
                return True
            return "Disallow: /" not in resp.text or parsed.path != "/"
        except Exception:
            return True
