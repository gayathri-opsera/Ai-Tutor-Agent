"""Kafka library configuration loaded from environment variables.

All services that import this library read their Kafka settings from here.
Set these in a .env file or export them in the shell before starting services.

Quick-start for a laptop with no Kafka:
    export KAFKA_SYNC_MODE=true

Quick-start with a local Docker broker:
    export KAFKA_BOOTSTRAP_SERVERS=localhost:9092
    export KAFKA_SYNC_MODE=false
"""
from __future__ import annotations

import os


def _bool(key: str, default: bool) -> bool:
    raw = os.getenv(key, str(default)).lower()
    return raw in ("1", "true", "yes")


class KafkaSettings:
    """Reads Kafka configuration from environment variables at access time.

    Using properties (rather than class-level constants) ensures that tests can
    set env vars after import and still see the correct values.
    """

    @property
    def bootstrap_servers(self) -> str:
        return os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")

    @property
    def sync_mode(self) -> bool:
        """When True, the producer dispatches to LocalEventBus instead of a broker.

        Set KAFKA_SYNC_MODE=true for local development without a running broker.
        The content ingestion pipeline and other async consumers will still
        execute — they just run in-process instead of across a broker.
        """
        return _bool("KAFKA_SYNC_MODE", False)

    @property
    def usage_topic(self) -> str:
        return os.getenv("KAFKA_USAGE_TOPIC", "llm-usage-events")

    @property
    def enabled(self) -> bool:
        """Master switch. When False, the producer silently drops all events."""
        return _bool("KAFKA_ENABLED", True)

    @property
    def dlq_suffix(self) -> str:
        return os.getenv("KAFKA_DLQ_SUFFIX", ".dlq")

    @property
    def max_retries(self) -> int:
        return int(os.getenv("KAFKA_MAX_RETRIES", "3"))

    @property
    def consumer_group_prefix(self) -> str:
        return os.getenv("KAFKA_CONSUMER_GROUP_PREFIX", "ai-tutor")

    def summary(self) -> dict:
        return {
            "bootstrap_servers": self.bootstrap_servers,
            "sync_mode": self.sync_mode,
            "enabled": self.enabled,
            "dlq_suffix": self.dlq_suffix,
            "max_retries": self.max_retries,
        }


kafka_settings = KafkaSettings()
