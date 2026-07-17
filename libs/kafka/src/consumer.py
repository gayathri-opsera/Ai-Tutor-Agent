"""Shared async Kafka consumer with at-least-once delivery and DLQ routing."""
from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from src.signing import SignatureError, verify_signature

logger = logging.getLogger(__name__)

_MAX_HANDLER_RETRIES = 3
_RETRY_BACKOFF_BASE = 1.0

# Set KAFKA_VERIFY_SIGNATURES=false to disable in migration period (default: true).
import os as _os
_VERIFY_SIGNATURES = _os.getenv("KAFKA_VERIFY_SIGNATURES", "true").lower() not in ("0", "false", "no")


MessageHandler = Callable[[dict], Awaitable[None]]


class ConsumerError(Exception):
    """Raised when a message handler fails after all retries and DLQ routing."""


class KafkaConsumer:
    """Async Kafka consumer with manual offset commit and DLQ routing.

    Delivery semantics: at-least-once. Offsets are committed only after the
    handler coroutine returns successfully. Messages that fail after
    ``max_handler_retries`` attempts are routed to the DLQ topic.

    Parameters
    ----------
    bootstrap_servers:
        Comma-separated broker address list.
    group_id:
        Consumer group identifier.
    dlq_suffix:
        Suffix for dead-letter queue topic names.
    max_handler_retries:
        Retry budget before DLQ routing.
    _aiokafka_consumer:
        Injectable aiokafka consumer (used in tests).
    _dlq_producer:
        Injectable producer for DLQ messages (used in tests).
    """

    def __init__(
        self,
        bootstrap_servers: str = "localhost:9092",
        group_id: str = "default-group",
        dlq_suffix: str = ".dlq",
        max_handler_retries: int = _MAX_HANDLER_RETRIES,
        _aiokafka_consumer: Any = None,
        _dlq_producer: Any = None,
    ) -> None:
        self._bootstrap_servers = bootstrap_servers
        self._group_id = group_id
        self._dlq_suffix = dlq_suffix
        self._max_handler_retries = max_handler_retries
        self._consumer = _aiokafka_consumer
        self._dlq_producer = _dlq_producer
        self._running = False

    async def consume(
        self,
        topic: str,
        handler: MessageHandler,
        *,
        max_messages: int | None = None,
    ) -> None:
        """Consume messages from *topic*, calling *handler* for each.

        Commits offsets only after successful handler execution.
        Failed messages (after retries) are sent to the DLQ topic.

        Parameters
        ----------
        topic:
            The Kafka topic to subscribe to.
        handler:
            Async callable that processes a single message payload dict.
        max_messages:
            Optional limit — used in tests to consume a finite batch.
        """
        consumer = await self._get_consumer(topic)
        self._running = True
        count = 0
        try:
            async for msg in consumer:
                if not self._running:
                    break
                try:
                    payload = json.loads(msg.value) if isinstance(msg.value, bytes) else msg.value
                except (json.JSONDecodeError, TypeError) as exc:
                    logger.error("Failed to deserialise message from %s: %s", topic, exc)
                    await consumer.commit()
                    continue

                # Verify HMAC signature and extract inner payload when signatures are enabled.
                if _VERIFY_SIGNATURES:
                    try:
                        payload = verify_signature(payload)
                    except SignatureError as exc:
                        logger.warning(
                            "Dropping message from %s — signature verification failed: %s",
                            topic, exc,
                        )
                        await consumer.commit()
                        continue

                # Schema version check — warn on unknown versions but still process.
                schema_version = payload.get("schema_version")
                if schema_version and schema_version != "1.0":
                    logger.warning(
                        "Unexpected schema_version %r on topic %s — expected '1.0'. "
                        "Consumer may need updating.",
                        schema_version, topic,
                    )

                # Validate payload against the topic schema registry (non-blocking — warns only).
                try:
                    from src.schema_registry import SchemaValidationError, validate_payload
                    validate_payload(topic, payload)
                except Exception as exc:
                    logger.warning(
                        "Schema registry validation warning for topic %s: %s — processing anyway",
                        topic, exc,
                    )

                await self._handle_with_retry(topic, payload, handler)
                await consumer.commit()

                count += 1
                if max_messages is not None and count >= max_messages:
                    break
        finally:
            await consumer.stop()
            self._running = False

    async def stop(self) -> None:
        self._running = False

    async def _handle_with_retry(
        self,
        topic: str,
        payload: dict,
        handler: MessageHandler,
    ) -> None:
        last_exc: Exception | None = None
        for attempt in range(self._max_handler_retries):
            try:
                await handler(payload)
                return
            except Exception as exc:
                last_exc = exc
                wait = _RETRY_BACKOFF_BASE * (2 ** attempt)
                logger.warning(
                    "Handler failed (attempt %d/%d) for topic %s: %s — retrying in %.1fs",
                    attempt + 1,
                    self._max_handler_retries,
                    topic,
                    exc,
                    wait,
                )
                await asyncio.sleep(wait)

        dlq_topic = topic + self._dlq_suffix
        dlq_payload = {"original_topic": topic, "payload": payload, "error": str(last_exc)}
        logger.error("Handler exhausted retries — routing to DLQ %s", dlq_topic)
        await self._send_to_dlq(dlq_topic, dlq_payload)

    async def _send_to_dlq(self, dlq_topic: str, payload: dict) -> None:
        if self._dlq_producer is not None:
            await self._dlq_producer.produce(dlq_topic, payload)
        else:
            logger.error("DLQ_FALLBACK [%s] %s", dlq_topic, json.dumps(payload))

    async def _get_consumer(self, topic: str) -> Any:
        if self._consumer is not None:
            return self._consumer
        try:
            from aiokafka import AIOKafkaConsumer  # type: ignore

            consumer = AIOKafkaConsumer(
                topic,
                bootstrap_servers=self._bootstrap_servers,
                group_id=self._group_id,
                enable_auto_commit=False,
                auto_offset_reset="earliest",
                value_deserializer=lambda v: v,
            )
            await consumer.start()
            return consumer
        except Exception as exc:
            logger.warning("Kafka consumer failed to start: %s", exc)
            raise
