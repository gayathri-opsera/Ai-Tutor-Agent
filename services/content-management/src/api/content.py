from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/content-mgmt", tags=["content-mgmt"])

class CreateKB(BaseModel):
    name: str
    organization_id: str

class CreateDoc(BaseModel):
    title: str

@router.post("/knowledge-bases")
async def create_kb(body: CreateKB, request: Request):
    svc = request.app.state.cms
    kb = svc.create_kb(body.name, body.organization_id)
    return {"id": kb.id, "name": kb.name}

@router.get("/knowledge-bases")
async def list_kbs(organization_id: str, request: Request):
    svc = request.app.state.cms
    return {"items": [{"id": kb.id, "name": kb.name} for kb in svc.list_kbs(organization_id)]}

@router.post("/knowledge-bases/{kb_id}/documents")
async def create_doc(kb_id: str, body: CreateDoc, request: Request):
    svc = request.app.state.cms
    if not svc.get_kb(kb_id):
        raise HTTPException(404, "Knowledge base not found")
    doc = svc.create_document(kb_id, body.title)
    return {"id": doc.id, "title": doc.title}

@router.post("/documents/{doc_id}/retire")
async def retire_doc(doc_id: str, request: Request):
    svc = request.app.state.cms
    doc = svc.retire_document(doc_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    return {"id": doc.id, "is_active": doc.is_active, "retired_at": doc.retired_at.isoformat()}
