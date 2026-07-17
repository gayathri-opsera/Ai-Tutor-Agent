"""Kafka Topic Schema Registry.

Maps every topic name to a versioned Pydantic model.  Producers call
``validate_payload`` before emitting; consumers call it before processing.
This gives Kafka a *memory* — a durable, centralised contract between
producers and consumers that CI can enforce.

Usage::

    from libs.kafka.src.schema_registry import registry, validate_payload

    # Produce side — will raise SchemaValidationError if payload is wrong shape
    clean = validate_payload("audit-events", raw_dict)

    # Consume side — same call; guarantees the handler receives typed data
    event = validate_payload("audit-events", msg)
"""
from __future__ import annotations

from typing import Any, Type

from pydantic import BaseModel, Field, field_validator


# ── Canonical event schemas (one per topic) ─────────────────────────────────

class ContentIngestionEvent(BaseModel):
    """Emitted when a new document chunk is ingested into the system."""
    schema_version: str = "1.0"
    document_id: str
    chunk_id: str
    knowledge_base_id: str
    ingested_at: str                           # ISO-8601


class ContentUpdateEvent(BaseModel):
    """Emitted when an existing document is updated."""
    schema_version: str = "1.0"
    document_id: str
    knowledge_base_id: str
    updated_at: str                            # ISO-8601


class LLMUsageEvent(BaseModel):
    """Emitted after every LLM completion for cost tracking."""
    schema_version: str = "1.0"
    model: str
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    session_id: str
    user_id: str


class CacheMetricsEvent(BaseModel):
    """Periodic cache hit/miss statistics."""
    schema_version: str = "1.0"
    cache_type: str
    hits: int = Field(ge=0)
    misses: int = Field(ge=0)
    evictions: int = Field(ge=0)
    window_seconds: int = Field(ge=1)


class AuditEvent(BaseModel):
    """Emitted by any service for compliance audit logging."""
    schema_version: str = "1.0"
    actor_id: str
    action: str
    resource_type: str
    resource_id: str
    outcome: str = "success"
    metadata: dict[str, Any] = {}


class AnalyticsEvent(BaseModel):
    """Generic analytics / behavioural event."""
    schema_version: str = "1.0"
    event_type: str = Field(min_length=1, max_length=100)
    user_id: str
    properties: dict[str, Any] = {}

    @field_validator("event_type")
    @classmethod
    def _validate_event_type(cls, v: str) -> str:
        if not v.replace(".", "_").replace("-", "_").isidentifier():
            raise ValueError(f"event_type {v!r} must be a dotted identifier")
        return v


class AdminConfigChangeEvent(BaseModel):
    """Emitted when an admin mutates configuration."""
    schema_version: str = "1.0"
    admin_id: str
    setting_key: str
    old_value: Any
    new_value: Any
    changed_at: str                            # ISO-8601


class UserApprovalEvent(BaseModel):
    """Emitted when a user account is approved or rejected."""
    schema_version: str = "1.0"
    user_id: str
    decision: str                              # "approved" | "rejected"
    decided_by: str
    decided_at: str                            # ISO-8601

    @field_validator("decision")
    @classmethod
    def _valid_decision(cls, v: str) -> str:
        if v not in {"approved", "rejected"}:
            raise ValueError("decision must be 'approved' or 'rejected'")
        return v


class CourseApprovalEvent(BaseModel):
    """Emitted when a course is approved or rejected for publication."""
    schema_version: str = "1.0"
    course_id: str
    knowledge_base_id: str
    decision: str                              # "approved" | "rejected"
    decided_by: str
    decided_at: str                            # ISO-8601

    @field_validator("decision")
    @classmethod
    def _valid_decision(cls, v: str) -> str:
        if v not in {"approved", "rejected"}:
            raise ValueError("decision must be 'approved' or 'rejected'")
        return v


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
    "user-approval-events":     UserApprovalEvent,
    "course-approval-events":   CourseApprovalEvent,
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
    otherwise.  If the topic is not in the registry the payload is returned as-is
    (dict) wrapped in a ``dict`` to remain a known type.
    """
    schema_cls = registry.get(topic)
    if schema_cls is None:
        # Unknown topic — pass through without validation.
        # Use an unconstrained open model so callers always get a BaseModel.
        class _Open(BaseModel):
            model_config = {"extra": "allow"}

        return _Open(**payload)

    from pydantic import ValidationError as PydanticValidationError

    try:
        return schema_cls(**payload)
    except PydanticValidationError as exc:
        raise SchemaValidationError(topic, exc.errors()) from exc
