"""MinHash near-duplicate detection."""
from __future__ import annotations

from datasketch import MinHash


def _shingles(text: str, n: int = 3) -> set[str]:
    words = text.lower().split()
    if len(words) < n:
        return {" ".join(words)} if words else set()
    return {" ".join(words[i : i + n]) for i in range(len(words) - n + 1)}


def compute_minhash(text: str, num_perm: int = 128) -> MinHash:
    mh = MinHash(num_perm=num_perm)
    for shingle in _shingles(text):
        mh.update(shingle.encode("utf-8"))
    return mh


def find_duplicate(
    chunk_texts: list[str],
    existing_signatures: list[tuple[str, MinHash]],
    threshold: float = 0.85,
) -> str | None:
    """Return document_id of duplicate if similarity exceeds threshold."""
    for text in chunk_texts:
        candidate = compute_minhash(text)
        for doc_id, existing in existing_signatures:
            if candidate.jaccard(existing) >= threshold:
                return doc_id
    return None
