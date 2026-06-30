"""Reciprocal rank fusion for re-ranking."""
from __future__ import annotations

from typing import Any


def reciprocal_rank_fusion(
    ranked_lists: list[list[dict[str, Any]]],
    k: int = 60,
) -> list[dict[str, Any]]:
    """Combine multiple ranked result lists using RRF."""
    scores: dict[str, float] = {}
    items: dict[str, dict[str, Any]] = {}
    for ranked in ranked_lists:
        for rank, item in enumerate(ranked, start=1):
            item_id = item.get("chunk_id") or item.get("id", str(rank))
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (k + rank)
            items[item_id] = item
    sorted_ids = sorted(scores, key=lambda x: scores[x], reverse=True)
    return [{**items[i], "score": scores[i]} for i in sorted_ids]
