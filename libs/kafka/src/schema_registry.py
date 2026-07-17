"""Kafka Topic Schema Registry.

Maps every topic name to the canonical Pydantic model from
``src.schemas.events``.  Producers call ``validate_payload`` before emitting;
consumers call it before processing.  This gives Kafka a *memory* — a durable,
centralised contract between producers and consumers that CI can enforce.

All schema definitions live in ``src/schemas/events.py`` as the single source
of truth.  The registry here is just the mapping + validation helper.

Usage::

    from libs.kafka.src.schema_registry import registry, validate_payload

    # Produce side — raises SchemaValidationError if payload is wrong shape
    clean = validate_payload("audit-events", raw_dict)

    # Consume side — same call; guarantees the handler receives typed data
    event = validate_payload("audit-events", msg)
"""
from __future__ import annotations

from typing import Any, Type

from pydantic import BaseModel

from src.schemas.events import (
    AdminConfigChangeEvent,
    AnalyticsEvent,
    AuditEvent,
    CacheMetricsEvent,
    ContentIngestionEvent,
    ContentUpdateEvent,
    CourseApprovalCompletedEvent,
    CourseApprovalRequestedEvent,
    LLMUsageEvent,
    UserApprovalCompletedEvent,
    UserApprovalRequestedEvent,
)


# ── Registry ────────────────────────────────────────────────────────────────

TopicSchemaRegistry = dict[str, Type[BaseModel]]

registry: TopicSchemaRegistry = {
    "content-ingestion-events": ContentIngestionEvent,
    "content-update-events":    ContentUpdateEvent,
    "llm-usage-events":         LLMUsageEvent,
    "cache-metrics":            CacheMetricsEvent,
    "audit-events":             AuditEvent,
    "analytics-events":         AnalyticsEvent,
    "admin-config-changes":     AdminConfigChangeEvent,
    "user-approval-events":     UserApprovalRequestedEvent,    # most common producer shape
    "course-approval-events":   CourseApprovalRequestedEvent,  # most common producer shape
}


# ── Validation helper ────────────────────────────────────────────────────────

class SchemaValidationError(ValueError):
    """Raised when a Kafka message doesn't match the registered schema."""

    def __init__(self, topic: str, errors: list) -> None:
        self.topic = topic
        self.errors = errors
        super().__init__(
            f"Message for topic {topic!r} failed schema validation: {errors}"
        )


def validate_payload(topic: str, payload: dict[str, Any]) -> BaseModel:
    """Validate *payload* against the registered schema for *topic*.

    Returns the parsed model instance if valid; raises ``SchemaValidationError``
    otherwise.  If the topic is not in the registry the payload is passed
    through wrapped in an open model so callers always receive a ``BaseModel``.
    """
    schema_cls = registry.get(topic)
    if schema_cls is None:
        # Unknown topic — pass through without strict validation.
        class _Open(BaseModel):
            model_config = {"extra": "allow"}

        return _Open(**payload)

    from pydantic import ValidationError as PydanticValidationError

    try:
        return schema_cls(**payload)
    except PydanticValidationError as exc:
        raise SchemaValidationError(topic, exc.errors()) from exc


# Re-export canonical event types for convenience
__all__ = [
    "registry",
    "validate_payload",
    "SchemaValidationError",
    "TopicSchemaRegistry",
    "ContentIngestionEvent",
    "ContentUpdateEvent",
    "LLMUsageEvent",
    "CacheMetricsEvent",
    "AuditEvent",
    "AnalyticsEvent",
    "AdminConfigChangeEvent",
    "UserApprovalRequestedEvent",
    "UserApprovalCompletedEvent",
    "CourseApprovalRequestedEvent",
    "CourseApprovalCompletedEvent",
]
