"""Content ingestion API."""
from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
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
    if not (file.filename.endswith((".pdf", ".docx")) or "pdf" in ct or "word" in ct):
        raise HTTPException(400, "Only PDF and DOCX supported for upload")
    record = await svc.create_upload(file.filename, ct, knowledge_base_id, content)
    return {"id": record.id, "status": record.status.value}


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
