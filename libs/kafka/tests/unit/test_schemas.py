"""Unit tests for event schema validation."""
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.schemas.events import (
    AdminConfigChangeEvent,
    AnalyticsEvent,
    AuditEvent,
    CacheMetricsEvent,
    ContentIngestionEvent,
    ContentIngestionCompletedEvent,
    ContentUpdateEvent,
    LLMUsageEvent,
)

FIXTURES = Path(__file__).parent.parent / "fixtures"


class TestContentIngestionEvent:
    def test_valid_event_from_fixture(self):
        data = json.loads((FIXTURES / "content_ingestion_event.json").read_text())
        event = ContentIngestionEvent(**data)
        assert event.content_id == "cnt-001"
        assert event.file_format == "pdf"

    def test_missing_required_fields(self):
        with pytest.raises(ValidationError):
            ContentIngestionEvent()  # type: ignore[call-arg]

    def test_default_event_id_generated(self):
        event = ContentIngestionEvent(
            content_id="x",
            tenant_id="t",
            s3_bucket="b",
            s3_key="k",
            file_format="pdf",
            file_size_bytes=1024,
        )
        assert len(event.event_id) == 36  # UUID format

    def test_completed_event(self):
        event = ContentIngestionCompletedEvent(
            content_id="cnt-001",
            tenant_id="t",
            chunk_count=50,
            embedding_count=50,
            elapsed_ms=3200,
        )
        assert event.event_type == "content.ingestion.completed"


class TestLLMUsageEvent:
    def test_valid_event_from_fixture(self):
        data = json.loads((FIXTURES / "llm_usage_event.json").read_text())
        event = LLMUsageEvent(**data)
        assert event.provider == "openai"
        assert event.total_tokens == 768

    def test_invalid_cost_type(self):
        with pytest.raises(ValidationError):
            LLMUsageEvent(
                request_id="r",
                provider="openai",
                model_used="gpt-4o",
                token_count_input=10,
                token_count_output=5,
                total_tokens=15,
                estimated_cost_usd="not-a-number",  # type: ignore[arg-type]
            )


class TestAuditEvent:
    def test_valid_event_from_fixture(self):
        data = json.loads((FIXTURES / "audit_event.json").read_text())
        event = AuditEvent(**data)
        assert event.outcome == "success"
        assert event.metadata["reason"] == "stale content"

    def test_missing_actor_id(self):
        with pytest.raises(ValidationError):
            AuditEvent(  # type: ignore[call-arg]
                action="delete",
                resource_type="content",
                resource_id="x",
                outcome="success",
                actor_role="admin",
            )


class TestAnalyticsEvent:
    def test_valid_event_from_fixture(self):
        data = json.loads((FIXTURES / "analytics_event.json").read_text())
        event = AnalyticsEvent(**data)
        assert event.action == "query"

    def test_payload_defaults_to_empty_dict(self):
        event = AnalyticsEvent(
            session_id="s",
            learner_id="l",
            tenant_id="t",
            action="query",
        )
        assert event.payload == {}


class TestAdminConfigChangeEvent:
    def test_valid_event_from_fixture(self):
        data = json.loads((FIXTURES / "admin_config_event.json").read_text())
        event = AdminConfigChangeEvent(**data)
        assert event.config_key == "max_tokens_per_request"
        assert event.new_value == 2048


class TestCacheMetricsEvent:
    def test_hit_event(self):
        event = CacheMetricsEvent(cache_type="semantic", hit=True, latency_ms=5)
        assert event.hit is True

    def test_miss_event(self):
        event = CacheMetricsEvent(cache_type="response", hit=False, latency_ms=120)
        assert event.hit is False


class TestContentUpdateEvent:
    def test_valid(self):
        event = ContentUpdateEvent(
            content_id="c",
            tenant_id="t",
            change_type="deleted",
        )
        assert event.event_type == "content.updated"
