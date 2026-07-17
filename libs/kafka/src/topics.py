"""Canonical Kafka topic definitions for the AI Tutor Agent platform.

Defines topic names, partition counts, retention periods, and DLQ counterparts
for every event bus topic used across all services.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TopicSpec:
    name: str
    partitions: int
    retention_ms: int      # -1 means infinite
    replication_factor: int = 3
    dlq_name: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "dlq_name", f"{self.name}.dlq")


# ---------------------------------------------------------------------------
# Topic registry
# ---------------------------------------------------------------------------

CONTENT_INGESTION_EVENTS = TopicSpec(
    name="content-ingestion-events",
    partitions=12,
    retention_ms=7 * 24 * 60 * 60 * 1000,   # 7 days
)

CONTENT_UPDATE_EVENTS = TopicSpec(
    name="content-update-events",
    partitions=6,
    retention_ms=7 * 24 * 60 * 60 * 1000,
)

LLM_USAGE_EVENTS = TopicSpec(
    name="llm-usage-events",
    partitions=12,
    retention_ms=30 * 24 * 60 * 60 * 1000,   # 30 days
)

CACHE_METRICS = TopicSpec(
    name="cache-metrics",
    partitions=4,
    retention_ms=3 * 24 * 60 * 60 * 1000,    # 3 days
)

AUDIT_EVENTS = TopicSpec(
    name="audit-events",
    partitions=12,
    retention_ms=365 * 24 * 60 * 60 * 1000,  # 1 year
)

ANALYTICS_EVENTS = TopicSpec(
    name="analytics-events",
    partitions=24,
    retention_ms=90 * 24 * 60 * 60 * 1000,   # 90 days
)

ADMIN_CONFIG_CHANGES = TopicSpec(
    name="admin-config-changes",
    partitions=2,
    retention_ms=-1,                           # infinite — config history
)

USER_APPROVAL_EVENTS = TopicSpec(
    name="user-approval-events",
    partitions=4,
    retention_ms=365 * 24 * 60 * 60 * 1000,  # 1 year — compliance requirement
)

ALL_TOPICS: list[TopicSpec] = [
    CONTENT_INGESTION_EVENTS,
    CONTENT_UPDATE_EVENTS,
    LLM_USAGE_EVENTS,
    CACHE_METRICS,
    AUDIT_EVENTS,
    ANALYTICS_EVENTS,
    ADMIN_CONFIG_CHANGES,
    USER_APPROVAL_EVENTS,
]
