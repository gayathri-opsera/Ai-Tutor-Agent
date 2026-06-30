"""Shared async Kafka producer with retry, DLQ routing, and schema validation."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_RETRY_BACKOFF_BASE = 0.5   # seconds; doubles each attempt


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
    _aiokafka_producer:
        Injectable aiokafka producer (used in tests to avoid real brokers).
    """

    def __init__(
        self,
        bootstrap_servers: str = "localhost:9092",
        dlq_suffix: str = ".dlq",
        max_retries: int = _MAX_RETRIES,
        _aiokafka_producer: Any = None,
    ) -> None:
        self._bootstrap_servers = bootstrap_servers
        self._dlq_suffix = dlq_suffix
        self._max_retries = max_retries
        self._producer = _aiokafka_producer
        self._started = False

    async def start(self) -> None:
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
        """Publish a message, retrying up to max_retries times.

        On persistent failure, routes to the DLQ topic instead.
        Raises ProduceError only if the DLQ delivery also fails.
        """
        if isinstance(value, BaseModel):
            payload = value.model_dump()
        else:
            payload = dict(value)

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
