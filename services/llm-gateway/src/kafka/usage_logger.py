"""Kafka producer for LLM usage telemetry (topic: llm-usage-events).

Every completion or streaming request publishes a structured event so the
LLM Operations dashboard can track cost, latency, and provider health.

Required fields per event (per acceptance criterion):
  - request_id
  - provider
  - model_used
  - token_count_input
  - token_count_output
  - estimated_cost_usd
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from src.config import settings

logger = logging.getLogger(__name__)


class UsageEvent:
    """Structured usage event schema."""

    __slots__ = (
        "request_id",
        "provider",
        "model_used",
        "token_count_input",
        "token_count_output",
        "estimated_cost_usd",
        "timestamp_ms",
        "extra",
    )

    def __init__(
        self,
        *,
        request_id: str,
        provider: str,
        model_used: str,
        token_count_input: int,
        token_count_output: int,
        estimated_cost_usd: float,
        extra: dict[str, Any] | None = None,
    ) -> None:
        self.request_id = request_id
        self.provider = provider
        self.model_used = model_used
        self.token_count_input = token_count_input
        self.token_count_output = token_count_output
        self.estimated_cost_usd = estimated_cost_usd
        self.timestamp_ms = int(time.time() * 1000)
        self.extra = extra or {}

    def to_dict(self) -> dict:
        return {
            "request_id": self.request_id,
            "provider": self.provider,
            "model_used": self.model_used,
            "token_count_input": self.token_count_input,
            "token_count_output": self.token_count_output,
            "estimated_cost_usd": self.estimated_cost_usd,
            "timestamp_ms": self.timestamp_ms,
            **self.extra,
        }


class KafkaUsageLogger:
    """Async Kafka producer for usage events.

    Gracefully degrades to a warning log when Kafka is unavailable or
    disabled (kafka_enabled = false) so that the gateway never fails
    a user request due to telemetry infrastructure issues.
    """

    def __init__(self) -> None:
        self._producer: Any = None  # aiokafka.AIOKafkaProducer

    async def start(self) -> None:
        if not settings.kafka_enabled:
            logger.info("Kafka usage logging disabled via config.")
            return
        producer = None
        try:
            from aiokafka import AIOKafkaProducer  # type: ignore[import]

            producer = AIOKafkaProducer(
                bootstrap_servers=settings.kafka_bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            )
            await producer.start()
            self._producer = producer
            logger.info(
                "Kafka producer started (servers=%s, topic=%s)",
                settings.kafka_bootstrap_servers,
                settings.kafka_usage_topic,
            )
        except Exception as exc:  # pragma: no cover
            logger.warning("Failed to start Kafka producer: %s — events will be logged locally.", exc)
            if producer is not None:
                try:
                    await producer.stop()
                except Exception:
                    pass
            self._producer = None

    async def stop(self) -> None:
        if self._producer:
            try:
                await self._producer.stop()
            except Exception as exc:  # pragma: no cover
                logger.warning("Error stopping Kafka producer: %s", exc)

    async def log_usage(self, event: UsageEvent) -> None:
        """Publish the event to Kafka asynchronously.

        Failures are logged but never propagate to the caller.
        """
        event_dict = event.to_dict()
        if self._producer:
            try:
                await self._producer.send_and_wait(
                    settings.kafka_usage_topic,
                    value=event_dict,
                    key=event.request_id.encode("utf-8"),
                )
            except Exception as exc:
                logger.warning("Kafka publish failed for request %s: %s", event.request_id, exc)
        else:
            # Structured local log — useful when Kafka is not available in dev
            logger.info("LLM_USAGE_EVENT %s", json.dumps(event_dict))


# Application-scoped singleton created at startup
_logger_instance: KafkaUsageLogger | None = None


def get_usage_logger() -> KafkaUsageLogger:
    global _logger_instance
    if _logger_instance is None:
        _logger_instance = KafkaUsageLogger()
    return _logger_instance
