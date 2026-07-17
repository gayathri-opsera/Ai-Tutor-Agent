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


@router.post("/sessions")
async def create_session(body: CreateSessionRequest, request: Request):
    svc: ChatOrchestratorService = request.app.state.chat_service
    session = await svc.create_session(body.user_id, body.knowledge_base_id)
    return {"id": session.id, "title": session.title}


@router.get("/sessions")
async def list_sessions(user_id: str = Query(...), request: Request = None):
    svc: ChatOrchestratorService = request.app.state.chat_service
    sessions = await svc.list_sessions(user_id)
    return {"sessions": sessions}


@router.patch("/sessions/{session_id}")
async def rename_session(session_id: str, body: RenameSessionRequest, request: Request):
    """Rename a chat session."""
    title = body.title.strip()
    if not title:
        raise HTTPException(400, "Title cannot be empty")
    svc: ChatOrchestratorService = request.app.state.chat_service
    ok = await svc.rename_session(session_id, title)
    if not ok:
        raise HTTPException(404, "Session not found")
    return {"id": session_id, "title": title}


@router.post("/sessions/{session_id}/messages")
async def send_message(session_id: str, body: MessageRequest, request: Request):
    svc: ChatOrchestratorService = request.app.state.chat_service
    session = await svc.get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    async def event_generator():
        kb_id = body.knowledge_base_id
        if kb_id:
            s = await svc.get_session(session_id)
            if s:
                s.knowledge_base_id = kb_id
                await svc.update_session(s)
        async for event in svc.stream_response(session_id, body.content, rag_chunks=None):
            yield {"event": event.split("\n")[0].replace("event: ", ""), "data": event.split("data: ", 1)[-1].strip()}

    return EventSourceResponse(event_generator())


@router.get("/sessions/{session_id}/history")
async def get_history(session_id: str, request: Request):
    svc: ChatOrchestratorService = request.app.state.chat_service
    messages = await svc.get_history(session_id)
    return {
        "session_id": session_id,
        "messages": [
            {"role": m.role, "content": m.content, "sources": m.sources}
            for m in messages
        ],
    }
