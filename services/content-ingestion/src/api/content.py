"""Content ingestion API."""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel

from src.service import DocumentStatus

router = APIRouter(prefix="/api/v1/content", tags=["content"])


class StatusResponse(BaseModel):
    id: str
    status: str
    chunk_count: int = 0
    error: str | None = None


@router.post("/upload", status_code=202)
async def upload_content(
    request: Request,
    file: UploadFile = File(...),
    knowledge_base_id: str = Form(...),
):
    svc = request.app.state.ingestion_service
    content = await file.read()
    ct = file.content_type or "application/octet-stream"
    allowed_ext = (".pdf", ".docx", ".txt", ".md")
    if not any(file.filename.lower().endswith(e) for e in allowed_ext):
        raise HTTPException(400, f"Only {', '.join(allowed_ext)} files are supported")
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
        # Get knowledge_base_id from DB
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


@router.get("/{doc_id}/status", response_model=StatusResponse)
async def get_status(doc_id: str, request: Request):
    svc = request.app.state.ingestion_service
    record = svc.get_status(doc_id)
    if not record:
        raise HTTPException(404, "Document not found")
    return StatusResponse(
        id=record.id,
        status=record.status.value,
        chunk_count=len(record.chunks),
        error=record.error,
    )
