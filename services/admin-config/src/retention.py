"""Data retention and purge."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable


@dataclass
class AuditEntry:
    action: str
    record_count: int
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class RetentionService:
    def __init__(
        self,
        store: list[dict[str, Any]] | None = None,
        audit_log: list[AuditEntry] | None = None,
    ) -> None:
        self._store = store if store is not None else []
        self._audit = audit_log if audit_log is not None else []

    def purge(self, retention_days: int, sensitive_fields: list[str] | None = None) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        purged = 0
        sensitive_fields = sensitive_fields or ["email", "phone", "ssn"]
        remaining = []
        for record in self._store:
            created = record.get("created_at")
            if isinstance(created, str):
                created = datetime.fromisoformat(created)
            if created and created < cutoff:
                for field in sensitive_fields:
                    if field in record:
                        record[field] = self._crypto_erase(str(record[field]))
                purged += 1
            else:
                remaining.append(record)
        self._store.clear()
        self._store.extend(remaining)
        self._audit.append(AuditEntry(action="retention.purge", record_count=purged))
        return purged

    @staticmethod
    def _crypto_erase(value: str) -> str:
        return hashlib.sha256(value.encode()).hexdigest()[:16] + "-ERASED"

    @property
    def audit_entries(self) -> list[AuditEntry]:
        return self._audit
