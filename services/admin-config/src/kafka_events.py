"""Kafka event emission helpers for the admin-config service."""
from __future__ import annotations

import logging
import os
import sys

logger = logging.getLogger(__name__)

# libs/kafka is installed as a package; add the monorepo root to sys.path so
# local imports resolve correctly in the container (PYTHONPATH=/app/libs/... set by Dockerfile).
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../../"))
_KAFKA_SRC = os.path.join(_REPO_ROOT, "libs", "kafka", "src")
if _KAFKA_SRC not in sys.path:
    sys.path.insert(0, _KAFKA_SRC)

try:
    from producer import KafkaProducer
    from topics import USER_APPROVAL_EVENTS
    from schemas.events import UserApprovalCompletedEvent

    _producer = KafkaProducer(
        bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092"),
        sync_mode=os.getenv("KAFKA_SYNC_MODE", "false").lower() in ("1", "true", "yes"),
    )
    _kafka_available = True
except ImportError:
    _kafka_available = False


async def emit_approval_event(
    actor_id: str,
    user_id: str,
    keycloak_id: str,
    outcome: str,
    roles_assigned: list[str],
) -> None:
    """Emit a UserApprovalCompleted event.  Fails gracefully if Kafka unavailable."""
    if not _kafka_available:
        logger.info(
            "Kafka not available — skipping UserApprovalCompleted event "
            "(actor=%s, user=%s, outcome=%s)",
            actor_id,
            user_id,
            outcome,
        )
        return

    event = UserApprovalCompletedEvent(
        actor_id=actor_id,
        user_id=user_id,
        keycloak_id=keycloak_id,
        outcome=outcome,
        roles_assigned=roles_assigned,
        source_service="admin-config",
    )

    try:
        await _producer.produce(
            topic=USER_APPROVAL_EVENTS.name,
            event=event,
        )
    except Exception as exc:
        logger.error("Failed to emit UserApprovalCompleted event: %s", exc)
