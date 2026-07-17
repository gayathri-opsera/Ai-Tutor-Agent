"""Audit logging utility — in-process logger with optional Kafka publishing.

Uses ``actor_id`` consistently to match the database column and API contract,
eliminating the ``user_id`` / ``actor_id`` semantic split.
"""
from __future__ import annotations

import functools
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Awaitable


@dataclass
class AuditLogEntry:
    id: str
    action: str
    actor_id: str           # canonical name — matches DB column and AuditLogResponse
    resource_id: str
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


EventPublisher = Callable[[str, dict], Awaitable[None]]


class AuditLogger:
    def __init__(
        self,
        store: list[AuditLogEntry] | None = None,
        publish: EventPublisher | None = None,
    ) -> None:
        self._store = store if store is not None else []
        self._publish = publish

    async def log(
        self,
        action: str,
        actor_id: str,
        resource_id: str,
        metadata: dict | None = None,
    ) -> AuditLogEntry:
        entry = AuditLogEntry(
            id=str(uuid.uuid4()),
            action=action,
            actor_id=actor_id,
            resource_id=resource_id,
            metadata=metadata or {},
        )
        self._store.append(entry)
        if self._publish:
            await self._publish("audit-events", {
                "action": action,
                "actor_id": actor_id,
                "resource_id": resource_id,
                "metadata": metadata or {},
            })
        return entry


def audit_action(action: str) -> Callable:
    """Decorator for auto-logging service actions."""

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            result = await func(*args, **kwargs)
            logger: AuditLogger | None = kwargs.get("audit_logger")
            if logger:
                actor_id = kwargs.get("actor_id", kwargs.get("user_id", "system"))
                resource_id = kwargs.get("resource_id", "")
                await logger.log(action, actor_id, resource_id)
            return result
        return wrapper
    return decorator
