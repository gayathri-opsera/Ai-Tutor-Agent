"""Content ingestion API."""
from __future__ import annotations

import json

import httpx as _httpx
from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel

from src.service import DocumentStatus

router = APIRouter(prefix="/api/v1/content", tags=["content"])

ALLOWED_EXTENSIONS = (
    ".pdf", ".docx", ".txt", ".md",
    ".mp4", ".mp3", ".wav", ".webm", ".m4a", ".ogg",
)


class StatusResponse(BaseModel):
    id: str
    status: str
    chunk_count: int = 0
    error: str | None = None


class TranscriptionEditRequest(BaseModel):
    text: str           # corrected full transcription text
    approve: bool = True


@router.post("/upload", status_code=202)
async def upload_content(
    request: Request,
    file: UploadFile = File(...),
    knowledge_base_id: str = Form(...),
):
    svc = request.app.state.ingestion_service
    content = await file.read()
    ct = file.content_type or "application/octet-stream"
    if not any(file.filename.lower().endswith(e) for e in ALLOWED_EXTENSIONS):
        raise HTTPException(
            400,
            f"Unsupported file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )
    record = await svc.create_upload(file.filename, ct, knowledge_base_id, content)
    return {
        "id": record.id,
        "document_id": record.id,
        "status": record.status.value,
        "chunk_count": len(record.chunks),
        "title": record.filename,
    }


@router.post("/documents/{doc_id}/reindex", status_code=202)
async def reindex_document(doc_id: str, background_tasks: BackgroundTasks, request: Request):
    """Re-chunk and re-index an existing document into the RAG vector store."""
    svc = request.app.state.ingestion_service
    text = await svc.get_content(doc_id)
    if not text:
        raise HTTPException(404, "Document not found or has no extracted text")

    async def _do_reindex():
        from src.chunking import chunk_text as _chunk
        chunks = _chunk(text)
        if not chunks:
            return
        async with svc._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT knowledge_base_id, title FROM documents WHERE id=$1", doc_id
            )
        if not row:
            return
        try:
            await svc._index_chunks(
                doc_id=doc_id,
                knowledge_base_id=str(row["knowledge_base_id"]),
                document_title=row["title"],
                chunks=chunks,
            )
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("Re-index failed for %s: %s", doc_id, exc)

    background_tasks.add_task(_do_reindex)
    return {"status": "reindex_queued", "document_id": doc_id}


@router.get("/documents/{doc_id}/content")
async def get_document_content(doc_id: str, request: Request):
    svc = request.app.state.ingestion_service
    text = await svc.get_content(doc_id)
    if text is None:
        raise HTTPException(404, "Document not found")
    return {"id": doc_id, "content": text}


@router.get("/{doc_id}/transcription")
async def get_transcription(doc_id: str, request: Request):
    """WO-024: Return full transcription with per-segment quality scores for creator review."""
    svc = request.app.state.ingestion_service
    record = svc.get_status(doc_id)
    if record:
        if not record.transcription_segments:
            raise HTTPException(404, "No transcription available for this document")
        return {
            "id": doc_id,
            "full_text": record.content_text,
            "avg_quality": record.transcription_quality,
            "status": record.status.value,
            "segments": record.transcription_segments,
        }
    # Fall back to DB
    try:
        async with svc._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, status, content_text FROM documents WHERE id = $1", doc_id
            )
        if row:
            return {
                "id": str(row["id"]),
                "full_text": row["content_text"] or "",
                "avg_quality": None,
                "status": str(row["status"]),
                "segments": [],
            }
    except Exception:
        pass
    raise HTTPException(404, "Document not found")


@router.put("/{doc_id}/transcription")
async def update_transcription(doc_id: str, body: TranscriptionEditRequest, request: Request):
    """WO-024: Creator edits and approves a pending_review transcription, triggering re-indexing."""
    svc = request.app.state.ingestion_service
    record = svc.get_status(doc_id)
    if record is None:
        raise HTTPException(404, "Document not found")
    if record.status not in (DocumentStatus.PENDING_REVIEW, DocumentStatus.ACTIVE):
        raise HTTPException(
            400,
            f"Cannot edit transcription for document in status '{record.status.value}'",
        )

    # Update in-memory record with corrected text
    record.content_text = body.text
    from src.chunking import chunk_text
    record.chunks = chunk_text(body.text) if body.text.strip() else []

    new_status = DocumentStatus.ACTIVE if body.approve else DocumentStatus.PENDING_REVIEW
    record.status = new_status

    # Persist to DB
    try:
        async with svc._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE documents
                   SET content_text = $1,
                       chunk_count  = $2,
                       status       = $3::document_status_enum
                 WHERE id = $4
                """,
                body.text, len(record.chunks), new_status.value, doc_id,
            )
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("Failed to persist transcription update: %s", exc)

    # Re-index now that the creator approved it
    if body.approve and record.chunks:
        try:
            async with svc._pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT knowledge_base_id, title FROM documents WHERE id=$1", doc_id
                )
            if row:
                await svc._index_chunks(
                    doc_id=doc_id,
                    knowledge_base_id=str(row["knowledge_base_id"]),
                    document_title=row["title"],
                    chunks=record.chunks,
                )
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("Re-index after approval failed: %s", exc)

    return {
        "id": doc_id,
        "status": new_status.value,
        "chunk_count": len(record.chunks),
        "message": "Transcription updated and re-indexed" if body.approve else "Transcription saved — not yet approved",
    }


@router.get("/{doc_id}/media")
async def get_media(doc_id: str, request: Request):
    """Stream the raw media file (video/audio) for a document from MinIO.

    Proxies through the API so the browser doesn't need direct MinIO access.
    Supports HTTP Range requests so HTML5 <video> seek works correctly.
    """
    from fastapi.responses import Response

    svc = request.app.state.ingestion_service
    url = await svc.get_media_url(doc_id)
    if url is None:
        raise HTTPException(404, "Media not found or not a media document")

    # Determine content-type from the document record / DB
    content_type = "application/octet-stream"
    rec = svc.get_status(doc_id)
    if rec:
        fname = rec.filename.lower()
        if fname.endswith(".mp4"):   content_type = "video/mp4"
        elif fname.endswith(".webm"): content_type = "video/webm"
        elif fname.endswith(".mp3"):  content_type = "audio/mpeg"
        elif fname.endswith(".wav"):  content_type = "audio/wav"
        elif fname.endswith(".m4a"):  content_type = "audio/mp4"
        elif fname.endswith(".ogg"):  content_type = "audio/ogg"
    else:
        # Fall back to DB lookup
        try:
            async with svc._pool.acquire() as conn:
                row = await conn.fetchrow("SELECT title FROM documents WHERE id=$1", doc_id)
            if row:
                fname = (row["title"] or "").lower()
                if fname.endswith(".mp4"):   content_type = "video/mp4"
                elif fname.endswith(".webm"): content_type = "video/webm"
                elif fname.endswith(".mp3"):  content_type = "audio/mpeg"
                elif fname.endswith(".wav"):  content_type = "audio/wav"
                elif fname.endswith(".m4a"):  content_type = "audio/mp4"
                elif fname.endswith(".ogg"):  content_type = "audio/ogg"
        except Exception:
            pass

    # Forward Range header if the browser sent one (needed for video seeking)
    headers: dict = {}
    range_header = request.headers.get("Range")
    if range_header:
        headers["Range"] = range_header

    try:
        async with _httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            body = resp.content
            status_code = resp.status_code  # 200 or 206
            resp_headers = {
                "Content-Type": content_type,
                "Accept-Ranges": "bytes",
            }
            if "Content-Range" in resp.headers:
                resp_headers["Content-Range"] = resp.headers["Content-Range"]
            if "Content-Length" in resp.headers:
                resp_headers["Content-Length"] = resp.headers["Content-Length"]
            return Response(content=body, status_code=status_code, headers=resp_headers)
    except Exception as exc:
        raise HTTPException(502, f"Failed to fetch media from storage: {exc}")


@router.get("/{doc_id}/status", response_model=StatusResponse)
async def get_status(doc_id: str, request: Request):
    svc = request.app.state.ingestion_service
    # Try in-memory cache first (fast path for recent uploads)
    record = svc.get_status(doc_id)
    if record:
        return StatusResponse(
            id=record.id,
            status=record.status.value,
            chunk_count=len(record.chunks),
            error=record.error,
        )
    # Fall back to DB so status survives service restarts
    try:
        async with svc._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, status, chunk_count FROM documents WHERE id = $1", doc_id
            )
        if row:
            return StatusResponse(
                id=str(row["id"]),
                status=str(row["status"]),
                chunk_count=row["chunk_count"] or 0,
            )
    except Exception:
        pass
    raise HTTPException(404, "Document not found")
