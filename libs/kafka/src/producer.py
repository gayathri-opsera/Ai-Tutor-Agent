"""Shared async Kafka producer with retry, DLQ routing, and schema validation.

Fallback chain (evaluated per produce() call):
  1. Real Kafka broker    — when sync_mode=False and broker connected
  2. LocalEventBus        — when sync_mode=True (dispatches to in-process handlers)
  3. stdout JSON log      — when broker unreachable and no local handler registered
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Imported at module level so tests can patch src.producer.local_bus
from src.local_bus import local_bus  # noqa: E402

_MAX_RETRIES = 3
_RETRY_BACKOFF_BASE = 0.5   # seconds; doubles each attempt


def _sync_mode_enabled() -> bool:
    return os.getenv("KAFKA_SYNC_MODE", "false").lower() in ("1", "true", "yes")


class ProduceError(Exception):
    """Raised when a message cannot be delivered after all retries."""


class KafkaProducer:
    """Async Kafka producer wrapping aiokafka with retry + DLQ routing.

    Parameters
    ----------
    bootstrap_servers:
        Comma-separated list of broker addresses.
    dlq_suffix:
        Suffix appended to a topic name to form the DLQ topic name.
    max_retries:
        Number of delivery retries before routing to the DLQ.
    sync_mode:
        When True, bypasses the Kafka broker entirely and dispatches events to
        the LocalEventBus. Defaults to the KAFKA_SYNC_MODE env var.
    _aiokafka_producer:
        Injectable aiokafka producer (used in tests to avoid real brokers).
    """

    def __init__(
        self,
        bootstrap_servers: str = "localhost:9092",
        dlq_suffix: str = ".dlq",
        max_retries: int = _MAX_RETRIES,
        sync_mode: bool | None = None,
        _aiokafka_producer: Any = None,
    ) -> None:
        self._bootstrap_servers = bootstrap_servers
        self._dlq_suffix = dlq_suffix
        self._max_retries = max_retries
        self._sync_mode = sync_mode if sync_mode is not None else _sync_mode_enabled()
        self._producer = _aiokafka_producer
        self._started = False

    @property
    def sync_mode(self) -> bool:
        return self._sync_mode

    async def start(self) -> None:
        if self._sync_mode:
            logger.info(
                "KafkaProducer: KAFKA_SYNC_MODE=true — events will be dispatched "
                "to LocalEventBus instead of a broker. Register handlers with "
                "local_bus.subscribe(topic, handler) at service startup."
            )
            self._started = True
            return

        if self._producer is None:
            try:
                from aiokafka import AIOKafkaProducer  # type: ignore
                self._producer = AIOKafkaProducer(
                    bootstrap_servers=self._bootstrap_servers,
                    value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                    key_serializer=lambda k: k.encode("utf-8") if k else None,
                )
                await self._producer.start()
            except Exception as exc:
                logger.warning("Kafka producer failed to start: %s", exc)
                self._producer = None
        self._started = True

    async def stop(self) -> None:
        if self._producer is not None:
            try:
                await self._producer.stop()
            except Exception as exc:
                logger.warning("Kafka producer stop error: %s", exc)
        self._started = False

    async def produce(
        self,
        topic: str,
        value: dict | BaseModel,
        key: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        """Publish a message via the active transport.

        When sync_mode is True, dispatches directly to LocalEventBus.
        Otherwise retries up to max_retries times against the Kafka broker,
        then routes to the DLQ on persistent failure.
        """
        if isinstance(value, BaseModel):
            payload = value.model_dump()
        else:
            payload = dict(value)

        # Validate payload against the topic schema registry before emitting.
        import os as _os
        if _os.getenv("KAFKA_VALIDATE_SCHEMA", "true").lower() not in ("0", "false", "no"):
            from src.schema_registry import SchemaValidationError, validate_payload
            try:
                validate_payload(topic, payload)
            except SchemaValidationError as exc:
                logger.error("Schema validation failed for topic %s: %s — message dropped", topic, exc)
                raise

        # Sign the payload so consumers can verify authenticity (KAFKA_VERIFY_SIGNATURES).
        if _os.getenv("KAFKA_SIGN_MESSAGES", "true").lower() not in ("0", "false", "no"):
            from src.signing import sign_payload
            signed = sign_payload(payload)
            payload = signed.model_dump()

        if self._sync_mode:
            await local_bus.publish(topic, payload, key=key)
            return

        kafka_headers = (
            [(k, v.encode()) for k, v in headers.items()] if headers else None
        )

        last_exc: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                await self._send(topic, payload, key, kafka_headers)
                return
            except Exception as exc:
                last_exc = exc
                wait = _RETRY_BACKOFF_BASE * (2 ** attempt)
                logger.warning(
                    "Kafka produce attempt %d/%d failed for topic %s: %s — retrying in %.1fs",
                    attempt + 1,
                    self._max_retries,
                    topic,
                    exc,
                    wait,
                )
                await asyncio.sleep(wait)

        # All retries exhausted — route to DLQ
        dlq_topic = topic + self._dlq_suffix
        dlq_payload = {"original_topic": topic, "original_key": key, "payload": payload, "error": str(last_exc)}
        logger.error("Routing message to DLQ %s after %d failed attempts", dlq_topic, self._max_retries)
        try:
            await self._send(dlq_topic, dlq_payload, key, kafka_headers)
        except Exception as dlq_exc:
            raise ProduceError(
                f"DLQ delivery also failed for {dlq_topic}: {dlq_exc}"
            ) from last_exc

    async def _send(
        self,
        topic: str,
        value: dict,
        key: str | None,
        headers: list | None,
    ) -> None:
        if self._producer is not None:
            await self._producer.send_and_wait(topic, value=value, key=key, headers=headers)
        else:
            logger.info("KAFKA_LOCAL [%s] key=%s payload=%s", topic, key, json.dumps(value))
