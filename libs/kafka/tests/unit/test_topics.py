"""Unit tests for topic definitions."""
import pytest

from src.topics import (
    ALL_TOPICS,
    ADMIN_CONFIG_CHANGES,
    ANALYTICS_EVENTS,
    AUDIT_EVENTS,
    CACHE_METRICS,
    CONTENT_INGESTION_EVENTS,
    CONTENT_UPDATE_EVENTS,
    LLM_USAGE_EVENTS,
    TopicSpec,
)


class TestTopicSpec:
    def test_dlq_name_derived(self):
        spec = TopicSpec(name="my-topic", partitions=4, retention_ms=1000)
        assert spec.dlq_name == "my-topic.dlq"

    def test_immutable(self):
        spec = TopicSpec(name="my-topic", partitions=4, retention_ms=1000)
        with pytest.raises((AttributeError, TypeError)):
            spec.name = "other"  # type: ignore[misc]

    def test_all_topics_have_required_fields(self):
        for spec in ALL_TOPICS:
            assert spec.name
            assert spec.partitions > 0
            assert spec.replication_factor >= 1

    def test_audit_events_long_retention(self):
        one_year_ms = 365 * 24 * 60 * 60 * 1000
        assert AUDIT_EVENTS.retention_ms >= one_year_ms

    def test_admin_config_infinite_retention(self):
        assert ADMIN_CONFIG_CHANGES.retention_ms == -1

    def test_llm_usage_topic_name(self):
        assert LLM_USAGE_EVENTS.name == "llm-usage-events"

    def test_all_seven_topics_defined(self):
        assert len(ALL_TOPICS) == 7

    def test_dlq_names_unique(self):
        dlq_names = [t.dlq_name for t in ALL_TOPICS]
        assert len(dlq_names) == len(set(dlq_names))
