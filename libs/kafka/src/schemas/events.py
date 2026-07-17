"""Event schema definitions for all Kafka topics.

Pydantic models serve as the single source of truth for event shapes.
Both the producer and consumer validate against these models.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uuid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

class BaseEvent(BaseModel):
    event_id: str = Field(default_factory=_uuid)
    event_type: str
    timestamp: str = Field(default_factory=_now)
    schema_version: str = "1.0"
    source_service: str = ""


# ---------------------------------------------------------------------------
# content-ingestion-events
# ---------------------------------------------------------------------------

class ContentIngestionEvent(BaseEvent):
    event_type: str = "content.ingestion.requested"
    content_id: str
    tenant_id: str
    s3_bucket: str
    s3_key: str
    file_format: str        # pdf | docx | mp4 | url | …
    file_size_bytes: int
    requested_by: str = ""


class ContentIngestionCompletedEvent(BaseEvent):
    event_type: str = "content.ingestion.completed"
    content_id: str
    tenant_id: str
    chunk_count: int
    embedding_count: int
    elapsed_ms: int


# ---------------------------------------------------------------------------
# content-update-events
# ---------------------------------------------------------------------------

class ContentUpdateEvent(BaseEvent):
    event_type: str = "content.updated"
    content_id: str
    tenant_id: str
    change_type: str        # created | updated | deleted


# ---------------------------------------------------------------------------
# llm-usage-events
# ---------------------------------------------------------------------------

class LLMUsageEvent(BaseEvent):
    event_type: str = "llm.usage"
    request_id: str
    tenant_id: str = ""
    provider: str
    model_used: str
    token_count_input: int
    token_count_output: int
    total_tokens: int
    estimated_cost_usd: float
    latency_ms: int = 0


# ---------------------------------------------------------------------------
# cache-metrics
# ---------------------------------------------------------------------------

class CacheMetricsEvent(BaseEvent):
    event_type: str = "cache.metrics"
    cache_type: str         # semantic | response
    hit: bool
    latency_ms: int
    key_hash: str = ""


# ---------------------------------------------------------------------------
# audit-events
# ---------------------------------------------------------------------------

class AuditEvent(BaseEvent):
    event_type: str = "audit.action"
    actor_id: str
    actor_role: str
    action: str
    resource_type: str
    resource_id: str
    outcome: str            # success | failure
    ip_address: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# analytics-events
# ---------------------------------------------------------------------------

class AnalyticsEvent(BaseEvent):
    event_type: str = "analytics.learner"
    session_id: str
    learner_id: str
    tenant_id: str
    action: str             # query | answer_rated | module_completed | …
    payload: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# admin-config-changes
# ---------------------------------------------------------------------------

class AdminConfigChangeEvent(BaseEvent):
    event_type: str = "admin.config.changed"
    admin_id: str
    config_key: str
    old_value: Any = None
    new_value: Any = None
    tenant_id: str = ""


# ---------------------------------------------------------------------------
# user-approval-events
# ---------------------------------------------------------------------------

class UserApprovalCompletedEvent(BaseEvent):
    """Emitted when an admin approves or rejects a user registration request."""
    event_type: str = "user.approval.completed"
    actor_id: str                    # Admin's keycloak_id who performed the action
    user_id: str                     # Target user's database UUID
    keycloak_id: str                 # Target user's keycloak_id
    outcome: str                     # "approved" | "rejected"
    roles_assigned: list[str] = Field(default_factory=list)  # populated on approval
