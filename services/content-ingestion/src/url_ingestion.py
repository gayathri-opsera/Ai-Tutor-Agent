"""URL content ingestion with robust extraction and robots.txt respect.

Extraction pipeline (in order):
  1. trafilatura  — purpose-built for article/blog/doc text, handles many SPAs
     that embed content in <script type="application/json"> or <template> tags.
  2. BeautifulSoup — plain HTML scraper, fallback when trafilatura yields nothing.

Both strategies use real browser headers to avoid bot-detection blocks.
"""
from __future__ import annotations

from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from src.chunking import chunk_text

# ── Browser headers ────────────────────────────────────────────────────────────
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# ── Binary-file guard ──────────────────────────────────────────────────────────
# Reject these before making any network call — they must be uploaded as files.
_BINARY_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".mp3", ".mp4", ".wav", ".m4a", ".ogg", ".webm", ".flac",
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg",
    ".zip", ".tar", ".gz", ".rar",
}
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
_BINARY_HINT = (
    "This URL points to a binary file (PDF, audio, video, etc.). "
    "Please download the file and upload it using the File Upload tab instead."
)

_MIN_CONTENT_LENGTH = 150  # chars — pages under this are likely gated or empty


def _is_binary_url(url: str) -> bool:
    path = urlparse(url).path.lower().split("?")[0]
    return any(path.endswith(ext) for ext in _BINARY_EXTENSIONS)


def _is_binary_content_type(content_type: str) -> bool:
    ct = content_type.lower().split(";")[0].strip()
    return any(ct.startswith(prefix) for prefix in _BINARY_CONTENT_TYPE_PREFIXES)


# ── Extraction helpers ─────────────────────────────────────────────────────────

def _extract_with_trafilatura(html: str, url: str) -> str:
    """Try trafilatura first — it handles SPAs and article-style pages well."""
    try:
        import trafilatura
        text = trafilatura.extract(
            html,
            url=url,
            include_comments=False,
            include_tables=True,
            no_fallback=False,       # allow internal fallback strategies
            favor_recall=True,       # prefer more content over precision
        )
        return (text or "").strip()
    except Exception:
        return ""


def _extract_with_bs4(html: str) -> str:
    """BeautifulSoup fallback — strips boilerplate and targets the main content zone."""
    import re as _re
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside",
                     "form", "button", "noscript"]):
        tag.decompose()

    # Prefer semantic content containers over the full document
    main = (
        soup.find("article")
        or soup.find("main")
        or soup.find(attrs={"role": "main"})
        or soup.find(id=_re.compile(r"(content|main|article|body)", _re.I))
        or soup.find(class_=_re.compile(
            r"(article|post|entry|content|body|blog)", _re.I
        ))
        or soup
    )

    raw = main.get_text(separator="\n", strip=True)
    return _clean_nav_artifacts(raw)


def _clean_nav_artifacts(text: str) -> str:
    """Remove navigation-style lines that survive tag-based stripping.

    Squarespace/Wix/Webflow sites often render menus as plain divs, so they
    survive <nav> removal.  A line is treated as a nav artifact when it is
    short (≤4 words) AND contains no sentence-ending punctuation — menu
    labels like "About", "My Gear Recommendations", "Skip to Content", "Back"
    all match this pattern while real sentences do not.
    Consecutive duplicate lines (menus repeated for mobile/desktop) are also
    removed.
    """
    lines = text.split("\n")
    seen: set[str] = set()
    cleaned: list[str] = []

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            if cleaned and cleaned[-1] != "":
                cleaned.append("")
            continue

        word_count = len(line.split())
        has_punctuation = any(c in line for c in ".,:;?!—()")

        # Skip short nav-like lines (≤4 words, no sentence punctuation)
        if word_count <= 4 and not has_punctuation:
            continue

        # Skip exact duplicates (mobile + desktop nav blocks are identical)
        if line in seen:
            continue

        seen.add(line)
        cleaned.append(line)

    return "\n".join(cleaned).strip()


# ── Main service ───────────────────────────────────────────────────────────────

class URLIngestionService:
    def __init__(self, http_client: httpx.AsyncClient | None = None) -> None:
        self._http = http_client

    async def fetch_and_chunk(self, url: str) -> list[str]:
        # Fast-path: reject obvious binary file URLs before any network call
        if _is_binary_url(url):
            raise ValueError(_BINARY_HINT)

        client = self._http or httpx.AsyncClient(
            follow_redirects=True,
            headers=_BROWSER_HEADERS,
            timeout=30.0,
        )
        close = self._http is None
        try:
            if not await self._allowed_by_robots(client, url):
                raise PermissionError(f"Blocked by robots.txt: {url}")

            resp = await client.get(url)

            # Translate HTTP errors into friendly messages
            if resp.status_code == 404:
                raise ValueError(
                    f"Page not found (404): {url}\n"
                    "Check the URL is correct and the page is publicly accessible."
                )
            if resp.status_code == 403:
                raise PermissionError(
                    f"Access denied (403): the site blocked automated access to {url}."
                )
            if resp.status_code >= 400:
                raise ValueError(
                    f"The page returned HTTP {resp.status_code}. "
                    "It may require login or have moved."
                )

            # Guard against binary responses (e.g. a PDF served without extension)
            content_type = resp.headers.get("content-type", "")
            if _is_binary_content_type(content_type):
                raise ValueError(_BINARY_HINT)

            html = resp.text

            # ── Strategy 1: trafilatura (best for articles, blogs, SPAs) ──────
            text = _extract_with_trafilatura(html, url)

            # ── Strategy 2: BeautifulSoup fallback ───────────────────────────
            if len(text) < _MIN_CONTENT_LENGTH:
                text = _extract_with_bs4(html)

            if len(text) < _MIN_CONTENT_LENGTH:
                raise ValueError(
                    "Could not extract readable text from this page.\n\n"
                    "This usually means the page requires JavaScript to render "
                    "(a React/Vue/Angular SPA) or needs a login to view content.\n\n"
                    "Try one of these alternatives:\n"
                    "• In Chrome: File → Save As → Webpage, Complete — then upload the saved HTML\n"
                    "• Copy and paste the text into a .txt file and upload it\n"
                    "• Use the PDF export option of the page if available"
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
