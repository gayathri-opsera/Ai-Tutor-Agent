"""Chat API routes."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from src.models import Session
from src.service import ChatOrchestratorService

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])


class CreateSessionRequest(BaseModel):
    user_id: str
    knowledge_base_id: str | None = None


class RenameSessionRequest(BaseModel):
    title: str


class MessageRequest(BaseModel):
    content: str
    knowledge_base_id: str | None = None
    lesson_context: str | None = None   # current lesson transcript/content for in-course chat


# ── Ownership helper ──────────────────────────────────────────────────────────

def _caller_id(request: Request) -> str | None:
    """Extract the caller's Keycloak sub from request.state.user (if set)."""
    user = getattr(request.state, "user", None)
    return getattr(user, "sub", None) if user else None


def _is_admin(request: Request) -> bool:
    user = getattr(request.state, "user", None)
    return bool(user and any(r in {"Admin", "SuperAdmin"} for r in getattr(user, "roles", [])))


async def _assert_session_owner(session_id: str, request: Request, svc: ChatOrchestratorService) -> None:
    """Raise 403 if the caller does not own the session (admins are exempt)."""
    if _is_admin(request):
        return
    caller = _caller_id(request)
    if caller is None:
        return  # No auth middleware configured — allow (dev mode)
    session = await svc.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if getattr(session, "user_id", None) and session.user_id != caller:
        raise HTTPException(status_code=403, detail="Access denied — this session belongs to another user")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/sessions")
async def create_session(body: CreateSessionRequest, request: Request):
    svc: ChatOrchestratorService = request.app.state.chat_service
    # Prefer the authenticated user's sub over the body-supplied user_id.
    user_id = _caller_id(request) or body.user_id
    session = await svc.create_session(user_id, body.knowledge_base_id)
    return {"id": session.id, "title": session.title}


@router.get("/sessions")
async def list_sessions(user_id: str = Query(...), request: Request = None):
    svc: ChatOrchestratorService = request.app.state.chat_service
    # Scope to the authenticated caller; ignore the query param for non-admins.
    caller = _caller_id(request)
    if caller and not _is_admin(request):
        user_id = caller
    sessions = await svc.list_sessions(user_id)
    return {"sessions": sessions}


@router.patch("/sessions/{session_id}")
async def rename_session(session_id: str, body: RenameSessionRequest, request: Request):
    """Rename a chat session."""
    title = body.title.strip()
    if not title:
        raise HTTPException(400, "Title cannot be empty")
    svc: ChatOrchestratorService = request.app.state.chat_service
    await _assert_session_owner(session_id, request, svc)
    ok = await svc.rename_session(session_id, title)
    if not ok:
        raise HTTPException(404, "Session not found")
    return {"id": session_id, "title": title}


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(session_id: str, request: Request):
    """Permanently delete a chat session and all its messages."""
    svc: ChatOrchestratorService = request.app.state.chat_service
    await _assert_session_owner(session_id, request, svc)
    await svc.delete_session(session_id)
    # Return 204 No Content regardless — idempotent delete


@router.post("/sessions/{session_id}/messages")
async def send_message(session_id: str, body: MessageRequest, request: Request):
    svc: ChatOrchestratorService = request.app.state.chat_service
    await _assert_session_owner(session_id, request, svc)

    async def event_generator():
        kb_id = body.knowledge_base_id
        if kb_id:
            s = await svc.get_session(session_id)
            if s:
                s.knowledge_base_id = kb_id
                await svc.update_session(s)
        async for event in svc.stream_response(
            session_id, body.content, rag_chunks=None, lesson_context=body.lesson_context
        ):
            yield {"event": event.split("\n")[0].replace("event: ", ""), "data": event.split("data: ", 1)[-1].strip()}

    return EventSourceResponse(event_generator())


@router.get("/sessions/{session_id}/history")
async def get_history(session_id: str, request: Request):
    svc: ChatOrchestratorService = request.app.state.chat_service
    await _assert_session_owner(session_id, request, svc)
    messages = await svc.get_history(session_id)
    return {
        "session_id": session_id,
        "messages": [
            {"role": m.role, "content": m.content, "sources": m.sources}
            for m in messages
        ],
    }
