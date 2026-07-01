from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/content-mgmt", tags=["content-mgmt"])


class CreateKB(BaseModel):
    name: str
    organization_id: str
    description: str = ""


class CreateDoc(BaseModel):
    title: str
    content_type: str = "text"


@router.post("/knowledge-bases", status_code=201)
async def create_kb(body: CreateKB, request: Request):
    svc = request.app.state.cms
    kb = await svc.create_kb(body.name, body.organization_id, body.description)
    return {"id": kb.id, "name": kb.name, "description": kb.description, "is_active": True}


@router.get("/knowledge-bases")
async def list_kbs(organization_id: str = "default", request: Request = None):
    svc = request.app.state.cms
    items = await svc.list_kbs(organization_id)
    return {"items": [
        {"id": kb.id, "name": kb.name, "description": kb.description, "is_active": kb.is_active}
        for kb in items
    ]}


@router.get("/knowledge-bases/{kb_id}")
async def get_kb(kb_id: str, request: Request):
    svc = request.app.state.cms
    kb = await svc.get_kb(kb_id)
    if not kb:
        raise HTTPException(404, "Knowledge base not found")
    return {"id": kb.id, "name": kb.name, "description": kb.description, "is_active": kb.is_active}


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
            "status": "active" if d.is_active else "archived",
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
    doc = await svc.retire_document(doc_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    return {"id": doc.id, "is_active": doc.is_active, "retired_at": doc.retired_at.isoformat() if doc.retired_at else None}
