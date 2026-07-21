from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Literal

router = APIRouter(prefix="/api/v1", tags=["content-mgmt"])


class CreateKB(BaseModel):
    name: str
    organization_id: str
    description: str = ""
    age_group: str | None = None


class UpdateKB(BaseModel):
    name: str | None = None
    description: str | None = None
    age_group: str | None = None


class CreateDoc(BaseModel):
    title: str
    content_type: str = "text"


# ── Platform stats (home page) ────────────────────────────────────────────────

@router.get("/stats")
async def platform_stats(request: Request):
    """Live KB / document / chunk counts for the home-page stats strip."""
    svc = request.app.state.cms
    return await svc.platform_stats()


# ── Knowledge Bases ────────────────────────────────────────────────────────────

@router.post("/knowledge-bases", status_code=201)
async def create_kb(body: CreateKB, request: Request):
    svc = request.app.state.cms
    user = getattr(getattr(request, "state", None), "user", None)
    creator_keycloak_id = getattr(user, "sub", None) if user else None
    # Admins may publish immediately; all other roles enter the approval queue.
    is_admin = user and any(r in {"Admin", "SuperAdmin"} for r in getattr(user, "roles", []))
    initial_status = "approved" if is_admin else "pending_review"
    kb = await svc.create_kb(
        body.name, body.organization_id, body.description,
        age_group=body.age_group,
        created_by_keycloak_id=creator_keycloak_id,
        approval_status=initial_status,
    )
    return {
        "id": kb.id, "name": kb.name, "description": kb.description,
        "is_active": True, "age_group": kb.age_group,
        "approval_status": kb.approval_status,
        "created_by_keycloak_id": kb.created_by_keycloak_id,
    }


@router.get("/knowledge-bases")
async def list_kbs(
    organization_id: str = "default",
    include_archived: bool = False,
    request: Request = None,
):
    svc = request.app.state.cms
    # Admins see all statuses; regular users only see approved KBs
    # *plus* their own KBs (so creators can manage drafts/pending ones).
    user = getattr(getattr(request, "state", None), "user", None)
    is_admin = user and any(r in {"Admin", "SuperAdmin"} for r in getattr(user, "roles", []))
    caller_keycloak_id = getattr(user, "sub", None) if user else None
    items = await svc.list_kbs(
        organization_id,
        include_archived=include_archived,
        approved_only=not is_admin,
        caller_keycloak_id=caller_keycloak_id,
    )
    return {"items": [
        {
            "id": kb.id, "name": kb.name, "description": kb.description,
            "is_active": kb.is_active, "age_group": kb.age_group,
            "approval_status": kb.approval_status,
            "created_by_keycloak_id": kb.created_by_keycloak_id,
            "doc_count": kb.doc_count,
        }
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
    return {
        "id": kb.id, "name": kb.name, "description": kb.description,
        "is_active": kb.is_active, "age_group": kb.age_group,
        "approval_status": kb.approval_status,
        "created_by_keycloak_id": kb.created_by_keycloak_id,
    }


@router.put("/knowledge-bases/{kb_id}")
async def update_kb(kb_id: str, body: UpdateKB, request: Request):
    svc = request.app.state.cms
    # Ownership check: only the creator or an admin may update.
    user = getattr(getattr(request, "state", None), "user", None)
    is_admin = user and any(r in {"Admin", "SuperAdmin"} for r in getattr(user, "roles", []))
    if not is_admin:
        kb_row = await svc.get_kb_raw(kb_id)
        if kb_row and kb_row.get("created_by_keycloak_id") and \
                kb_row["created_by_keycloak_id"] != getattr(user, "sub", None):
            raise HTTPException(status_code=403, detail="You do not own this course")
    kb = await svc.update_kb(kb_id, name=body.name, description=body.description,
                             age_group=body.age_group)
    if not kb:
        raise HTTPException(404, "Knowledge base not found")
    return {"id": kb.id, "name": kb.name, "description": kb.description,
            "is_active": kb.is_active, "age_group": kb.age_group}


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
    # Ownership check: only the creator or an admin may delete.
    user = getattr(getattr(request, "state", None), "user", None)
    is_admin = user and any(r in {"Admin", "SuperAdmin"} for r in getattr(user, "roles", []))
    if not is_admin:
        svc = request.app.state.cms
        kb_row = await svc.get_kb_raw(kb_id)
        if kb_row and kb_row.get("created_by_keycloak_id") and \
                kb_row["created_by_keycloak_id"] != getattr(user, "sub", None):
            raise HTTPException(status_code=403, detail="You do not own this course")
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


class ApprovalAction(BaseModel):
    action: Literal["approve", "reject", "request_clarification"]
    reason: str | None = None


@router.get("/knowledge-bases/admin/pending")
async def list_pending_kbs(request: Request):
    """Admin-only: list all knowledge bases with pending_review status."""
    user = getattr(getattr(request, "state", None), "user", None)
    is_admin = user and any(r in {"Admin", "SuperAdmin"} for r in getattr(user, "roles", []))
    if not is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    svc = request.app.state.cms
    items, _total = await svc.list_by_approval_status("pending_review")
    return {"items": items}


@router.patch("/knowledge-bases/{kb_id}/approval")
async def set_kb_approval(kb_id: str, body: ApprovalAction, request: Request):
    """Admin-only: approve, reject, or request clarification on a course."""
    user = getattr(getattr(request, "state", None), "user", None)
    is_admin = user and any(r in {"Admin", "SuperAdmin"} for r in getattr(user, "roles", []))
    if not is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    svc = request.app.state.cms
    status_map = {
        "approve":               "approved",
        "reject":                "rejected",
        "request_clarification": "clarification_requested",
    }
    new_status = status_map[body.action]
    await svc.update_kb_field(kb_id, "approval_status", new_status)
    if body.reason:
        field = "rejection_reason" if body.action == "reject" else "clarification_message"
        await svc.update_kb_field(kb_id, field, body.reason)
    return {"kb_id": kb_id, "approval_status": new_status}
