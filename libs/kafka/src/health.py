"""Kafka health check utility."""
from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


async def check_kafka_health(bootstrap_servers: str = "localhost:9092", timeout: float = 5.0) -> dict:
    """Attempt to connect to Kafka and return a health status dict."""
    try:
        from aiokafka import AIOKafkaProducer  # type: ignore

        producer = AIOKafkaProducer(bootstrap_servers=bootstrap_servers)
        await asyncio.wait_for(producer.start(), timeout=timeout)
        await producer.stop()
        return {"status": "healthy", "bootstrap_servers": bootstrap_servers}
    except asyncio.TimeoutError:
        return {"status": "unhealthy", "reason": "connection timeout", "bootstrap_servers": bootstrap_servers}
    except Exception as exc:
        return {"status": "unhealthy", "reason": str(exc), "bootstrap_servers": bootstrap_servers}
