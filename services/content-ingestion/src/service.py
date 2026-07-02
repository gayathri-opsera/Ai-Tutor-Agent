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

import asyncio

import asyncpg
import httpx

from src.chunking import chunk_text

logger = logging.getLogger(__name__)

DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "postgresql://ai_tutor:ai_tutor_local_password@postgres:5432/ai_tutor",
)
RAG_SERVICE_URL: str = os.getenv("RAG_SERVICE_URL", "http://rag-pipeline:8002")

# MinIO / S3 settings — used to store raw media files so learners can play them back
S3_ENDPOINT  = os.getenv("S3_ENDPOINT",  "http://minio:9000")
S3_ACCESS_KEY = os.getenv("S3_ACCESS_KEY", "minioadmin")
S3_SECRET_KEY = os.getenv("S3_SECRET_KEY", "minioadmin")
S3_BUCKET    = os.getenv("S3_BUCKET",    "ai-tutor-content")


def _get_minio_client():
    """Return a lazily-created MinIO client (best-effort; returns None if unavailable)."""
    try:
        from minio import Minio
        endpoint = S3_ENDPOINT.replace("http://", "").replace("https://", "")
        secure = S3_ENDPOINT.startswith("https://")
        client = Minio(endpoint, access_key=S3_ACCESS_KEY, secret_key=S3_SECRET_KEY, secure=secure)
        # Ensure bucket exists
        if not client.bucket_exists(S3_BUCKET):
            client.make_bucket(S3_BUCKET)
        return client
    except Exception as exc:
        logger.warning("MinIO unavailable — media files will not be stored: %s", exc)
        return None


def _upload_to_minio(s3_key: str, file_bytes: bytes, content_type: str) -> bool:
    """Upload raw bytes to MinIO. Returns True on success."""
    client = _get_minio_client()
    if client is None:
        return False
    try:
        import io
        client.put_object(
            S3_BUCKET, s3_key,
            data=io.BytesIO(file_bytes),
            length=len(file_bytes),
            content_type=content_type,
        )
        return True
    except Exception as exc:
        logger.warning("MinIO upload failed for %s: %s", s3_key, exc)
        return False


def get_minio_url(s3_key: str, expires_seconds: int = 3600) -> str | None:
    """Generate a presigned GET URL for a stored media object."""
    client = _get_minio_client()
    if client is None:
        return None
    try:
        from datetime import timedelta
        url = client.presigned_get_object(S3_BUCKET, s3_key, expires=timedelta(seconds=expires_seconds))
        return url
    except Exception as exc:
        logger.warning("Failed to generate presigned URL for %s: %s", s3_key, exc)
        return None


class DocumentStatus(str, Enum):
    UPLOADING = "uploading"
    PROCESSING = "processing"
    ACTIVE = "active"
    ERROR = "error"
    PENDING_REVIEW = "pending_review"   # low-quality transcription awaiting creator approval


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
    # Transcription metadata (set for audio/video documents)
    transcription_segments: list[dict] = field(default_factory=list)
    transcription_quality: float | None = None


EventPublisher = Callable[[str, dict], Awaitable[None]]


MEDIA_EXTENSIONS = {".mp4", ".mp3", ".wav", ".webm", ".m4a", ".ogg"}


def _is_media(filename: str) -> bool:
    return any(filename.lower().endswith(ext) for ext in MEDIA_EXTENSIONS)


def _sanitize_text(text: str) -> str:
    """Remove null bytes and other characters PostgreSQL UTF-8 rejects."""
    # \x00 is rejected by PostgreSQL's UTF-8 codec
    return text.replace("\x00", "")


def _extract_text(filename: str, content_type: str, file_bytes: bytes) -> str:
    """Extract plain text from PDF, DOCX, or plain-text bytes. Media files return empty string (handled separately by transcriber)."""
    if _is_media(filename):
        return ""   # transcription handled asynchronously in create_upload
    name_lower = filename.lower()
    try:
        if name_lower.endswith(".pdf") or "pdf" in content_type:
            import pypdf
            reader = pypdf.PdfReader(io.BytesIO(file_bytes))
            raw = "\n\n".join(page.extract_text() or "" for page in reader.pages)
            return _sanitize_text(raw)
        if name_lower.endswith(".docx") or "word" in content_type:
            import docx
            doc = docx.Document(io.BytesIO(file_bytes))
            raw = "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
            return _sanitize_text(raw)
        if name_lower.endswith((".txt", ".md")):
            return _sanitize_text(file_bytes.decode("utf-8", errors="replace"))
    except Exception:
        pass
    # Fallback: try raw UTF-8
    try:
        return _sanitize_text(file_bytes.decode("utf-8", errors="replace"))
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
    if name.endswith((".mp3", ".m4a")):
        return "mp3"
    if name.endswith((".wav", ".ogg")):
        return "mp3"
    if name.endswith(".webm"):
        return "mp4"
    return "text"


class ContentIngestionService:
    def __init__(
        self,
        pool: asyncpg.Pool,
        store: dict[str, DocumentRecord] | None = None,
        publish_event: EventPublisher | None = None,
        s3_bucket: str = "ai-tutor-content",
        transcriber=None,
    ) -> None:
        self._pool = pool
        self._store = store if store is not None else {}
        self._publish = publish_event
        self.s3_bucket = s3_bucket
        self._transcriber = transcriber  # injected; defaults to WhisperTranscriber on first use

    def _get_transcriber(self):
        if self._transcriber is None:
            from src.transcription import WhisperTranscriber
            self._transcriber = WhisperTranscriber()
        return self._transcriber

    async def create_upload(
        self,
        filename: str,
        content_type: str,
        knowledge_base_id: str,
        file_bytes: bytes,
    ) -> DocumentRecord:
        doc_id = str(uuid.uuid4())
        s3_key = f"{knowledge_base_id}/{doc_id}/{filename}"

        is_media = _is_media(filename)
        ct_enum = _content_type_enum(filename, content_type)

        # 1. Extract text (text docs) or transcribe (media)
        extracted_text = ""
        transcription_segments: list[dict] = []
        transcription_quality: float | None = None
        initial_status = DocumentStatus.ACTIVE

        if is_media:
            # Store raw media bytes in MinIO so learners can play them back
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, _upload_to_minio, s3_key, file_bytes, content_type)

            try:
                result = await self._get_transcriber().transcribe_bytes(file_bytes, filename)
                extracted_text = result.full_text
                transcription_quality = result.avg_quality
                transcription_segments = [
                    {
                        "start": s.start,
                        "end": s.end,
                        "text": s.text,
                        "confidence": s.confidence,
                        "avg_logprob": s.avg_logprob,
                    }
                    for s in result.segments
                ]
                # Flag low-quality transcriptions for creator review
                if result.is_low_quality:
                    initial_status = DocumentStatus.PENDING_REVIEW
                    logger.warning(
                        "Low-quality transcription for %s (avg_logprob=%.3f) — set to pending_review",
                        filename, result.avg_quality,
                    )
            except Exception as exc:
                logger.error("Transcription failed for %s: %s", filename, exc)
                initial_status = DocumentStatus.ERROR
                extracted_text = ""
        else:
            extracted_text = _extract_text(filename, content_type, file_bytes)

        chunks = chunk_text(extracted_text) if extracted_text.strip() else []

        # 2. Persist to documents table
        db_status = (
            "pending_review" if initial_status == DocumentStatus.PENDING_REVIEW
            else ("error" if initial_status == DocumentStatus.ERROR else "active")
        )
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO documents
                    (id, knowledge_base_id, title, content_type, status, chunk_count, content_text, s3_key)
                VALUES
                    ($1, $2, $3, $4::content_type_enum, $5::document_status_enum, $6, $7, $8)
                ON CONFLICT (id) DO NOTHING
                """,
                doc_id,
                knowledge_base_id,
                filename,
                ct_enum,
                db_status,
                len(chunks),
                extracted_text or None,
                s3_key if is_media else None,
            )

        record = DocumentRecord(
            id=doc_id,
            filename=filename,
            content_type=content_type,
            knowledge_base_id=knowledge_base_id,
            s3_key=s3_key,
            status=initial_status,
            chunks=chunks,
            content_text=extracted_text,
            transcription_segments=transcription_segments,
            transcription_quality=transcription_quality,
        )
        self._store[doc_id] = record

        if self._publish:
            await self._publish("content-ingestion-events", {
                "event_type": "document.uploaded",
                "document_id": doc_id,
                "knowledge_base_id": knowledge_base_id,
                "chunk_count": len(chunks),
                "status": db_status,
            })

        # Only index into RAG when active (not pending_review or error)
        if chunks and initial_status == DocumentStatus.ACTIVE:
            try:
                await self._index_chunks(
                    doc_id=doc_id,
                    knowledge_base_id=knowledge_base_id,
                    document_title=filename,
                    chunks=chunks,
                    segment_metadata=transcription_segments,
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
        segment_metadata: list[dict] | None = None,
    ) -> None:
        """Send chunks to the RAG pipeline for embedding + vector store upsert."""
        chunk_items = []
        for i, text in enumerate(chunks):
            item: dict = {"text": text, "chunk_index": i}
            # Attach timestamp metadata for media chunks
            if segment_metadata and i < len(segment_metadata):
                seg = segment_metadata[i]
                item["start_time"] = seg.get("start")
                item["end_time"] = seg.get("end")
            chunk_items.append(item)

        payload = {
            "document_id": doc_id,
            "knowledge_base_id": knowledge_base_id,
            "document_title": document_title,
            "chunks": chunk_items,
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

    async def get_media_url(self, doc_id: str) -> str | None:
        """Return a presigned MinIO URL for a media document, or None if not stored."""
        # Check in-memory store first (fast path for recently-uploaded files)
        rec = self._store.get(doc_id)
        if rec and _is_media(rec.filename):
            url = get_minio_url(rec.s3_key)
            if url:
                return url

        # Fall back to DB lookup
        try:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT s3_key FROM documents WHERE id = $1", doc_id
                )
            if row and row["s3_key"]:
                return get_minio_url(row["s3_key"])
        except Exception as exc:
            logger.warning("get_media_url DB lookup failed for %s: %s", doc_id, exc)
        return None

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
