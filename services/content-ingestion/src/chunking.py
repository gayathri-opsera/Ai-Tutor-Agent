"""Text chunking with paragraph awareness."""
from __future__ import annotations

import re


def chunk_text(
    text: str,
    min_words: int = 200,
    max_words: int = 500,
    overlap_words: int = 50,
) -> list[str]:
    """Split text into overlapping word-based chunks, respecting paragraphs."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    current: list[str] = []
    current_words = 0

    def flush(with_overlap: bool = False) -> None:
        nonlocal current, current_words
        if not current:
            return
        chunk = "\n\n".join(current)
        chunks.append(chunk)
        if with_overlap and overlap_words > 0:
            words = chunk.split()
            overlap = " ".join(words[-overlap_words:]) if len(words) > overlap_words else chunk
            current = [overlap]
            current_words = len(overlap.split())
        else:
            current = []
            current_words = 0

    for para in paragraphs:
        para_words = len(para.split())
        if current_words + para_words > max_words and current_words >= min_words:
            flush(with_overlap=True)
        current.append(para)
        current_words += para_words
        if current_words >= max_words:
            flush(with_overlap=True)

    if current:
        flush(with_overlap=False)
    return chunks if chunks else ([text] if text.strip() else [])
