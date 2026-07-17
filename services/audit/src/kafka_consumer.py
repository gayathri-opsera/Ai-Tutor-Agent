"""Kafka consumer for approval events — creates audit_logs entries.

Subscribes to:
  - user-approval-events   (UserApprovalRequestedEvent, UserApprovalCompletedEvent)
  - course-approval-events (CourseApprovalRequestedEvent, CourseApprovalCompletedEvent)

Each consumed event is written to the audit_logs table for compliance trail.
Run with:
    python -m src.kafka_consumer
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timezone

import asyncpg

log = logging.getLogger(__name__)
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"),
                    format="%(asctime)s %(levelname)s %(message)s")

DB_DSN              = os.getenv("DATABASE_URL",
                                "postgresql://ai_tutor:ai_tutor_local_password@postgres:5432/ai_tutor")
KAFKA_SERVERS       = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
KAFKA_GROUP_ID      = "audit-approval-consumer"
KAFKA_ENABLED       = os.getenv("KAFKA_ENABLED", "false").lower() == "true"
APPROVAL_TOPICS     = ["user-approval-events", "course-approval-events"]


# ── DB helper ─────────────────────────────────────────────────────────────────

async def _insert_audit_log(
    conn: asyncpg.Connection,
    *,
    event_type: str,
    actor_id: str,
    resource_id: str,
    resource_type: str,
    outcome: str,
    metadata: dict,
) -> None:
    log_id = str(uuid.uuid4())
    await conn.execute(
        """
        INSERT INTO audit_logs (id, action, actor_id, resource_id, resource_type,
                                outcome, metadata, created_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8)
        ON CONFLICT (id) DO NOTHING
        """,
        log_id,
        event_type,
        actor_id,
        resource_id,
        resource_type,
        outcome,
        json.dumps(metadata),
        datetime.now(timezone.utc),
    )


# ── Event handler ─────────────────────────────────────────────────────────────

async def handle_event(pool: asyncpg.Pool, raw: bytes) -> None:
    try:
        payload = json.loads(raw.decode())
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        log.warning("Undecodable event payload: %s", exc)
        return

    event_type   = payload.get("event_type", "unknown")
    actor_id     = payload.get("actor_id", "system")
    resource_id  = (
        payload.get("user_id")
        or payload.get("kb_id")
        or payload.get("resource_id", "")
    )
    resource_type = payload.get("resource_type", "unknown")
    outcome       = payload.get("outcome", "info")

    metadata = {k: v for k, v in payload.items()
                if k not in {"event_id", "event_type", "timestamp", "source_service",
                             "schema_version", "actor_id", "resource_id", "resource_type"}}

    async with pool.acquire() as conn:
        await _insert_audit_log(
            conn,
            event_type=event_type,
            actor_id=actor_id,
            resource_id=resource_id,
            resource_type=resource_type,
            outcome=outcome,
            metadata=metadata,
        )
    log.info("Audit log created: %s actor=%s resource=%s", event_type, actor_id, resource_id)


# ── Consumer loop ─────────────────────────────────────────────────────────────

async def run_consumer(pool: asyncpg.Pool) -> None:
    if not KAFKA_ENABLED:
        log.info("KAFKA_ENABLED=false — consumer is in no-op mode")
        while True:
            await asyncio.sleep(3600)

    from kafka import KafkaConsumer as _KafkaConsumer  # type: ignore[import]

    consumer = _KafkaConsumer(
        *APPROVAL_TOPICS,
        bootstrap_servers=KAFKA_SERVERS,
        group_id=KAFKA_GROUP_ID,
        auto_offset_reset="earliest",
        enable_auto_commit=True,
        value_deserializer=lambda v: v,  # raw bytes — we decode in handle_event
    )
    log.info("Kafka consumer started — topics: %s", APPROVAL_TOPICS)
    try:
        for message in consumer:
            await handle_event(pool, message.value)
    finally:
        consumer.close()


async def main() -> None:
    pool = await asyncpg.create_pool(DB_DSN, min_size=1, max_size=3)
    try:
        await run_consumer(pool)
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
