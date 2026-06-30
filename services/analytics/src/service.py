"""Analytics aggregation service."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AnalyticsEvent:
    event_type: str
    user_id: str
    topic: str = ""
    rating: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class AnalyticsService:
    def __init__(self) -> None:
        self.events: list[AnalyticsEvent] = []

    async def consume(self, payload: dict) -> None:
        self.events.append(AnalyticsEvent(
            event_type=payload.get("event_type", "unknown"),
            user_id=payload.get("user_id", ""),
            topic=payload.get("topic", ""),
            rating=payload.get("rating"),
            metadata=payload.get("metadata", {}),
        ))

    def summary(self) -> dict[str, Any]:
        session_events = [e for e in self.events if e.event_type == "session.created"]
        query_events = [e for e in self.events if e.event_type == "query.submitted"]
        ratings = [e.rating for e in self.events if e.rating is not None]
        topics = Counter(e.topic for e in self.events if e.topic)
        return {
            "session_count": len(session_events),
            "query_volume": len(query_events),
            "average_rating": sum(ratings) / len(ratings) if ratings else 0.0,
            "topic_distribution": dict(topics),
        }
