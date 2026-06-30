"""BM25 + vector hybrid search with RRF."""
from __future__ import annotations

import math
import re
from typing import Any

from src.reranker import reciprocal_rank_fusion


def _tokenize(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())


def bm25_score(query_tokens: list[str], doc_tokens: list[str], avg_dl: float, k1: float = 1.5, b: float = 0.75) -> float:
    if not doc_tokens:
        return 0.0
    dl = len(doc_tokens)
    tf_map: dict[str, int] = {}
    for t in doc_tokens:
        tf_map[t] = tf_map.get(t, 0) + 1
    score = 0.0
    for term in query_tokens:
        tf = tf_map.get(term, 0)
        if tf == 0:
            continue
        idf = math.log(1 + 1.0)  # simplified IDF for in-memory corpus
        denom = tf + k1 * (1 - b + b * dl / max(avg_dl, 1))
        score += idf * (tf * (k1 + 1)) / denom
    return score


def hybrid_search(
    query: str,
    vector_results: list[dict[str, Any]],
    *,
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """Combine BM25 and vector scores via reciprocal rank fusion."""
    query_tokens = _tokenize(query)
    corpus = [_tokenize(r.get("text", "")) for r in vector_results]
    avg_dl = sum(len(c) for c in corpus) / max(len(corpus), 1)

    bm25_ranked = sorted(
        [
            {**r, "bm25_score": bm25_score(query_tokens, _tokenize(r.get("text", "")), avg_dl)}
            for r in vector_results
        ],
        key=lambda x: x["bm25_score"],
        reverse=True,
    )
    vector_ranked = sorted(vector_results, key=lambda x: x.get("score", 0), reverse=True)
    fused = reciprocal_rank_fusion([bm25_ranked, vector_ranked])
    return fused[:top_k]
