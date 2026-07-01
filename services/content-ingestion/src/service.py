"""Content ingestion service — extract text, persist to PostgreSQL."""
from __future__ import annotations

import io
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Callable, Awaitable

import asyncpg
import httpx

from src.chunking import chunk_text

logger = logging.getLogger(__name__)

DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "postgresql://ai_tutor:ai_tutor_local_password@postgres:5432/ai_tutor",
)
RAG_SERVICE_URL: str = os.getenv("RAG_SERVICE_URL", "http://rag-pipeline:8002")


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
    content_text: str = ""
    error: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


EventPublisher = Callable[[str, dict], Awaitable[None]]


def _extract_text(filename: str, content_type: str, file_bytes: bytes) -> str:
    """Extract plain text from PDF, DOCX, or plain text bytes."""
    name_lower = filename.lower()
    try:
        if name_lower.endswith(".pdf") or "pdf" in content_type:
            import pypdf
            reader = pypdf.PdfReader(io.BytesIO(file_bytes))
            return "\n\n".join(page.extract_text() or "" for page in reader.pages)
        if name_lower.endswith(".docx") or "word" in content_type:
            import docx
            doc = docx.Document(io.BytesIO(file_bytes))
            return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
        if name_lower.endswith((".txt", ".md")):
            return file_bytes.decode("utf-8", errors="replace")
    except Exception:
        pass
    # Fallback: try raw UTF-8
    try:
        return file_bytes.decode("utf-8", errors="replace")
    except Exception:
        return ""


def _content_type_enum(filename: str, mime: str) -> str:
    name = filename.lower()
    if name.endswith(".pdf") or "pdf" in mime:
        return "pdf"
    if name.endswith(".docx") or "word" in mime:
        return "docx"
    if name.endswith(".mp4"):
        return "mp4"
    if name.endswith((".mp3", ".wav")):
        return "mp3"
    return "text"


class ContentIngestionService:
    def __init__(
        self,
        pool: asyncpg.Pool,
        store: dict[str, DocumentRecord] | None = None,
        publish_event: EventPublisher | None = None,
        s3_bucket: str = "ai-tutor-content",
    ) -> None:
        self._pool = pool
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

        # 1. Extract text
        extracted_text = _extract_text(filename, content_type, file_bytes)
        chunks = chunk_text(extracted_text) if extracted_text.strip() else []

        # 2. Determine DB enum value
        ct_enum = _content_type_enum(filename, content_type)

        # 3. Persist to documents table
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO documents
                    (id, knowledge_base_id, title, content_type, status, chunk_count, content_text)
                VALUES
                    ($1, $2, $3, $4::content_type_enum, 'active'::document_status_enum, $5, $6)
                ON CONFLICT (id) DO NOTHING
                """,
                doc_id,
                knowledge_base_id,
                filename,
                ct_enum,
                len(chunks),
                extracted_text or None,
            )

        record = DocumentRecord(
            id=doc_id,
            filename=filename,
            content_type=content_type,
            knowledge_base_id=knowledge_base_id,
            s3_key=s3_key,
            status=DocumentStatus.ACTIVE,
            chunks=chunks,
            content_text=extracted_text,
        )
        self._store[doc_id] = record

        if self._publish:
            await self._publish("content-ingestion-events", {
                "event_type": "document.uploaded",
                "document_id": doc_id,
                "knowledge_base_id": knowledge_base_id,
                "chunk_count": len(chunks),
            })

        # Fire-and-forget: index chunks into RAG vector store
        if chunks:
            try:
                await self._index_chunks(
                    doc_id=doc_id,
                    knowledge_base_id=knowledge_base_id,
                    document_title=filename,
                    chunks=chunks,
                )
            except Exception as exc:
                logger.warning("RAG indexing failed (non-fatal): %s", exc)

        return record

    async def _index_chunks(
        self,
        doc_id: str,
        knowledge_base_id: str,
        document_title: str,
        chunks: list[str],
    ) -> None:
        """Send chunks to the RAG pipeline for embedding + vector store upsert."""
        payload = {
            "document_id": doc_id,
            "knowledge_base_id": knowledge_base_id,
            "document_title": document_title,
            "chunks": [
                {"text": text, "chunk_index": i}
                for i, text in enumerate(chunks)
            ],
        }
        async with httpx.AsyncClient(timeout=600.0) as client:  # 10 min for large docs
            resp = await client.post(
                f"{RAG_SERVICE_URL}/api/internal/rag/ingest",
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            logger.info(
                "Indexed %d chunks for document %s into RAG",
                data.get("indexed", 0), doc_id
            )

    async def get_content(self, doc_id: str) -> str | None:
        """Return extracted text, checking in-memory cache first then DB."""
        rec = self._store.get(doc_id)
        if rec and rec.content_text:
            return rec.content_text
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT content_text, title FROM documents WHERE id = $1", doc_id
            )
        if not row:
            return None
        text = row["content_text"] or ""
        if not text.strip():
            return f"# {row['title']}\n\nDocument uploaded successfully. Content is being processed."
        return text

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
