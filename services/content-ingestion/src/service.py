"""Content ingestion service logic."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Awaitable


class DocumentStatus(str, Enum):
    UPLOADING = "uploading"
    PROCESSING = "processing"
    ACTIVE = "active"
    ERROR = "error"


@dataclass
class DocumentRecord:
    id: str
    filename: str
    content_type: str
    knowledge_base_id: str
    status: DocumentStatus = DocumentStatus.UPLOADING
    s3_key: str = ""
    chunks: list[str] = field(default_factory=list)
    error: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


EventPublisher = Callable[[str, dict], Awaitable[None]]


class ContentIngestionService:
    def __init__(
        self,
        store: dict[str, DocumentRecord] | None = None,
        publish_event: EventPublisher | None = None,
        s3_bucket: str = "ai-tutor-content",
    ) -> None:
        self._store = store if store is not None else {}
        self._publish = publish_event
        self.s3_bucket = s3_bucket

    async def create_upload(
        self,
        filename: str,
        content_type: str,
        knowledge_base_id: str,
        file_bytes: bytes,
    ) -> DocumentRecord:
        doc_id = str(uuid.uuid4())
        s3_key = f"{knowledge_base_id}/{doc_id}/{filename}"
        record = DocumentRecord(
            id=doc_id,
            filename=filename,
            content_type=content_type,
            knowledge_base_id=knowledge_base_id,
            s3_key=s3_key,
        )
        self._store[doc_id] = record
        if self._publish:
            await self._publish("content-ingestion-events", {
                "event_type": "document.uploaded",
                "document_id": doc_id,
                "s3_bucket": self.s3_bucket,
                "s3_key": s3_key,
                "knowledge_base_id": knowledge_base_id,
            })
        return record

    def get_status(self, doc_id: str) -> DocumentRecord | None:
        return self._store.get(doc_id)

    async def mark_processing(self, doc_id: str) -> None:
        rec = self._store.get(doc_id)
        if rec:
            rec.status = DocumentStatus.PROCESSING

    async def mark_active(self, doc_id: str, chunks: list[str]) -> None:
        rec = self._store.get(doc_id)
        if rec:
            rec.status = DocumentStatus.ACTIVE
            rec.chunks = chunks

    async def mark_error(self, doc_id: str, error: str) -> None:
        rec = self._store.get(doc_id)
        if rec:
            rec.status = DocumentStatus.ERROR
            rec.error = error
