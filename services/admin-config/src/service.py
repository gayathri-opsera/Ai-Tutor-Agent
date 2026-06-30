"""Admin configuration service."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class ConfigEntry:
    key: str
    value: Any
    organization_id: str
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class AdminConfigService:
    def __init__(self, store: dict[str, ConfigEntry] | None = None) -> None:
        self._store = store if store is not None else {}

    def _composite_key(self, org_id: str, key: str) -> str:
        return f"{org_id}:{key}"

    def get(self, org_id: str, key: str) -> ConfigEntry | None:
        return self._store.get(self._composite_key(org_id, key))

    def set(self, org_id: str, key: str, value: Any) -> ConfigEntry:
        entry = ConfigEntry(key=key, value=value, organization_id=org_id)
        self._store[self._composite_key(org_id, key)] = entry
        return entry

    def list_all(self, org_id: str) -> list[ConfigEntry]:
        prefix = f"{org_id}:"
        return [v for k, v in self._store.items() if k.startswith(prefix)]

    def delete(self, org_id: str, key: str) -> bool:
        ck = self._composite_key(org_id, key)
        if ck in self._store:
            del self._store[ck]
            return True
        return False
