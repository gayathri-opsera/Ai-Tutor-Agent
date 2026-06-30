"""LocalEventBus — in-process async pub/sub for Kafka-free local development.

When KAFKA_SYNC_MODE=true the KafkaProducer dispatches events here instead of
sending to a broker. Services register their topic handlers at startup and the
bus calls them inline, making the full processing pipeline work on a laptop
with zero infrastructure.

Fallback chain (evaluated in order):
  1. Real Kafka broker    — when KAFKA_SYNC_MODE=false and broker is reachable
  2. LocalEventBus        — when KAFKA_SYNC_MODE=true (handler registered)
  3. stdout JSON log      — when KAFKA_SYNC_MODE=true but no handler registered
                            (or when broker is unreachable and sync mode is off)
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)

TopicHandler = Callable[[dict], Awaitable[None]]


class LocalEventBus:
    """Singleton in-process event bus.

    Usage
    -----
    Register a handler at service startup::

        from libs.kafka.src.local_bus import local_bus
        local_bus.subscribe("content-ingestion-events", my_handler)

    The handler receives the same dict payload the Kafka consumer would receive.
    Multiple handlers per topic are supported and called sequentially.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[TopicHandler]] = defaultdict(list)

    def subscribe(self, topic: str, handler: TopicHandler) -> None:
        """Register *handler* to be called for every event on *topic*."""
        self._handlers[topic].append(handler)
        logger.debug("LocalEventBus: registered handler for topic '%s'", topic)

    def unsubscribe(self, topic: str, handler: TopicHandler) -> None:
        """Remove a previously registered handler."""
        self._handlers[topic] = [h for h in self._handlers[topic] if h is not handler]

    def clear(self, topic: str | None = None) -> None:
        """Remove all handlers, optionally scoped to a single topic."""
        if topic:
            self._handlers[topic] = []
        else:
            self._handlers.clear()

    async def publish(self, topic: str, payload: dict, key: str | None = None) -> None:
        """Dispatch *payload* to all handlers subscribed to *topic*.

        Errors in individual handlers are logged but do not prevent other
        handlers from running, mirroring Kafka's at-least-once semantics.
        """
        handlers = self._handlers.get(topic, [])
        if not handlers:
            logger.info(
                "LocalEventBus: no handler for topic '%s' — event dropped. "
                "Register one with local_bus.subscribe('%s', handler). "
                "Payload: %s",
                topic,
                topic,
                payload,
            )
            return

        for handler in handlers:
            try:
                await handler(payload)
            except Exception as exc:
                logger.error(
                    "LocalEventBus: handler %s failed for topic '%s': %s",
                    getattr(handler, "__name__", repr(handler)),
                    topic,
                    exc,
                )

    @property
    def subscribed_topics(self) -> list[str]:
        return [t for t, handlers in self._handlers.items() if handlers]


# Module-level singleton shared by all services in the same process
local_bus = LocalEventBus()
