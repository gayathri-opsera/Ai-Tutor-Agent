from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1", tags=["content-mgmt"])


class CreateKB(BaseModel):
    name: str
    organization_id: str
    description: str = ""


class UpdateKB(BaseModel):
    name: str | None = None
    description: str | None = None


class CreateDoc(BaseModel):
    title: str
    content_type: str = "text"


# ── Knowledge Bases ────────────────────────────────────────────────────────────

@router.post("/knowledge-bases", status_code=201)
async def create_kb(body: CreateKB, request: Request):
    svc = request.app.state.cms
    kb = await svc.create_kb(body.name, body.organization_id, body.description)
    return {"id": kb.id, "name": kb.name, "description": kb.description, "is_active": True}


@router.get("/knowledge-bases")
async def list_kbs(
    organization_id: str = "default",
    include_archived: bool = False,
    request: Request = None,
):
    svc = request.app.state.cms
    items = await svc.list_kbs(organization_id, include_archived=include_archived)
    return {"items": [
        {"id": kb.id, "name": kb.name, "description": kb.description, "is_active": kb.is_active}
        for kb in items
    ]}


@router.get("/knowledge-bases/{kb_id}")
async def get_kb(kb_id: str, request: Request):
    svc = request.app.state.cms
    try:
        kb = await svc.get_kb(kb_id)
    except Exception:
        raise HTTPException(404, "Knowledge base not found")
    if not kb:
        raise HTTPException(404, "Knowledge base not found")
    return {"id": kb.id, "name": kb.name, "description": kb.description, "is_active": kb.is_active}


@router.put("/knowledge-bases/{kb_id}")
async def update_kb(kb_id: str, body: UpdateKB, request: Request):
    svc = request.app.state.cms
    kb = await svc.update_kb(kb_id, name=body.name, description=body.description)
    if not kb:
        raise HTTPException(404, "Knowledge base not found")
    return {"id": kb.id, "name": kb.name, "description": kb.description, "is_active": kb.is_active}


@router.post("/knowledge-bases/{kb_id}/archive")
async def archive_kb(kb_id: str, request: Request):
    svc = request.app.state.cms
    kb = await svc.archive_kb(kb_id)
    if not kb:
        raise HTTPException(404, "Knowledge base not found")
    return {"id": kb.id, "name": kb.name, "is_active": kb.is_active}


@router.post("/knowledge-bases/{kb_id}/unarchive")
async def unarchive_kb(kb_id: str, request: Request):
    svc = request.app.state.cms
    kb = await svc.unarchive_kb(kb_id)
    if not kb:
        raise HTTPException(404, "Knowledge base not found")
    return {"id": kb.id, "name": kb.name, "is_active": kb.is_active}


@router.delete("/knowledge-bases/{kb_id}", status_code=204)
async def delete_kb(kb_id: str, request: Request):
    """Permanently delete a KB and all its documents, chunks, sessions, and assessments."""
    svc = request.app.state.cms
    deleted = await svc.hard_delete_kb(kb_id)
    if not deleted:
        raise HTTPException(404, "Knowledge base not found")


# ── Documents ──────────────────────────────────────────────────────────────────

@router.get("/knowledge-bases/{kb_id}/documents")
async def list_documents(kb_id: str, request: Request):
    svc = request.app.state.cms
    kb = await svc.get_kb(kb_id)
    if not kb:
        raise HTTPException(404, "Knowledge base not found")
    docs = await svc.list_documents(kb_id)
    return {"items": [
        {
            "id": d.id,
            "title": d.title,
            "status": d.metadata.get("status", "active" if d.is_active else "retired"),
            "chunk_count": d.chunk_count,
            "content_type": d.content_type,
            "is_active": d.is_active,
        }
        for d in docs
    ]}


@router.post("/knowledge-bases/{kb_id}/documents", status_code=201)
async def create_doc(kb_id: str, body: CreateDoc, request: Request):
    svc = request.app.state.cms
    kb = await svc.get_kb(kb_id)
    if not kb:
        raise HTTPException(404, "Knowledge base not found")
    doc = await svc.create_document(kb_id, body.title, body.content_type)
    return {"id": doc.id, "title": doc.title, "content_type": doc.content_type}


@router.post("/documents/{doc_id}/retire")
async def retire_doc(doc_id: str, request: Request):
    svc = request.app.state.cms
    try:
        doc = await svc.retire_document(doc_id)
    except Exception:
        raise HTTPException(404, "Document not found")
    if not doc:
        raise HTTPException(404, "Document not found")
    return {"id": doc.id, "is_active": doc.is_active, "retired_at": doc.retired_at.isoformat() if doc.retired_at else None}
