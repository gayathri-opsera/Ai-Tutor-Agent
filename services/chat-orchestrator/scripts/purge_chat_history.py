#!/usr/bin/env python3
"""Nightly purge job — deletes chat sessions and messages older than RETENTION_DAYS.

Runs as a Kubernetes CronJob (see .opsera-ai-tutor/k8s/base/chat-history-purge-cronjob.yaml).
Emits a Kafka observability event with deletion counts.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timezone

import asyncpg

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

DATABASE_URL      = os.environ["DATABASE_URL"]
RETENTION_DAYS    = int(os.getenv("RETENTION_DAYS", "7"))
KAFKA_SERVERS     = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
KAFKA_TOPIC       = "chat-history-purge-events"
KAFKA_ENABLED     = os.getenv("KAFKA_ENABLED", "false").lower() == "true"


async def purge(conn: asyncpg.Connection) -> tuple[int, int]:
    """Delete expired sessions and their messages. Returns (sessions, messages) deleted."""
    result = await conn.fetchrow(
        """
        WITH deleted_sessions AS (
            DELETE FROM chat_sessions
            WHERE created_at < now() - ($1 || ' days')::interval
            RETURNING id
        ),
        deleted_messages AS (
            DELETE FROM chat_messages
            WHERE session_id IN (SELECT id FROM deleted_sessions)
            RETURNING id
        )
        SELECT
            (SELECT count(*) FROM deleted_sessions)  AS sessions_deleted,
            (SELECT count(*) FROM deleted_messages)  AS messages_deleted
        """,
        str(RETENTION_DAYS),
    )
    return int(result["sessions_deleted"]), int(result["messages_deleted"])


def emit_kafka_event(sessions_deleted: int, messages_deleted: int) -> None:
    if not KAFKA_ENABLED:
        log.info("Kafka disabled — skipping purge observability event")
        return
    try:
        from kafka import KafkaProducer  # type: ignore[import]
        producer = KafkaProducer(
            bootstrap_servers=KAFKA_SERVERS,
            value_serializer=lambda v: json.dumps(v).encode(),
        )
        producer.send(KAFKA_TOPIC, {
            "event_id":          str(uuid.uuid4()),
            "event_type":        "chat.history.purged",
            "timestamp":         datetime.now(timezone.utc).isoformat(),
            "retention_days":    RETENTION_DAYS,
            "sessions_deleted":  sessions_deleted,
            "messages_deleted":  messages_deleted,
        })
        producer.flush()
        log.info("Kafka event emitted to %s", KAFKA_TOPIC)
    except Exception as exc:
        log.warning("Kafka event delivery failed (non-blocking): %s", exc)


async def main() -> None:
    log.info(
        "Starting chat history purge — retention=%d days, database=%s",
        RETENTION_DAYS, DATABASE_URL.split("@")[-1],
    )
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=2)
    try:
        async with pool.acquire() as conn:
            sessions, messages = await purge(conn)
        log.info("Purge complete: %d sessions and %d messages deleted", sessions, messages)
        emit_kafka_event(sessions, messages)
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
