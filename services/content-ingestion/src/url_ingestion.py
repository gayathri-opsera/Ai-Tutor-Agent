"""URL content ingestion with robots.txt respect."""
from __future__ import annotations

from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from src.chunking import chunk_text

# Mimic a real browser so sites don't reject bot requests
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

_MIN_CONTENT_LENGTH = 200  # chars — pages with less are likely JS-gated

# File extensions that must be downloaded and uploaded as files, not fetched as web pages
_BINARY_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".mp3", ".mp4", ".wav", ".m4a", ".ogg", ".webm", ".flac",
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg",
    ".zip", ".tar", ".gz", ".rar",
}

# Content-Type prefixes/values that indicate binary/non-HTML responses
_BINARY_CONTENT_TYPE_PREFIXES = (
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats",
    "application/vnd.ms-",
    "application/octet-stream",
    "audio/",
    "video/",
    "image/",
)


def _is_binary_url(url: str) -> bool:
    """Return True if the URL path ends with a known binary file extension."""
    path = urlparse(url).path.lower().split("?")[0]
    return any(path.endswith(ext) for ext in _BINARY_EXTENSIONS)


def _is_binary_content_type(content_type: str) -> bool:
    """Return True if the response Content-Type indicates binary/non-text content."""
    ct = content_type.lower().split(";")[0].strip()
    return any(ct.startswith(prefix) for prefix in _BINARY_CONTENT_TYPE_PREFIXES)


_BINARY_HINT = (
    "This URL points to a binary file (PDF, audio, video, etc.). "
    "Please download the file and upload it using the File Upload tab instead."
)


class URLIngestionService:
    def __init__(self, http_client: httpx.AsyncClient | None = None) -> None:
        self._http = http_client

    async def fetch_and_chunk(self, url: str) -> list[str]:
        # Reject binary file URLs immediately — no network call needed
        if _is_binary_url(url):
            raise ValueError(_BINARY_HINT)

        client = self._http or httpx.AsyncClient(
            follow_redirects=True,
            headers=_BROWSER_HEADERS,
        )
        close = self._http is None
        try:
            if not await self._allowed_by_robots(client, url):
                raise PermissionError(f"Blocked by robots.txt: {url}")
            resp = await client.get(url, timeout=30.0)
            resp.raise_for_status()

            # Guard against servers that return binary content despite a clean URL
            content_type = resp.headers.get("content-type", "")
            if _is_binary_content_type(content_type):
                raise ValueError(_BINARY_HINT)

            soup = BeautifulSoup(resp.text, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()
            text = soup.get_text(separator="\n", strip=True)
            if len(text) < _MIN_CONTENT_LENGTH:
                raise ValueError(
                    "Page returned too little text — it may require JavaScript "
                    "rendering (SPA) or login. Try downloading the content "
                    "directly (e.g. PDF or MP3) and uploading as a file instead."
                )
            return chunk_text(text)
        finally:
            if close:
                await client.aclose()

    async def _allowed_by_robots(self, client: httpx.AsyncClient, url: str) -> bool:
        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        try:
            resp = await client.get(robots_url, timeout=5.0)
            if resp.status_code != 200:
                return True
            return "Disallow: /" not in resp.text or parsed.path != "/"
        except Exception:
            return True
