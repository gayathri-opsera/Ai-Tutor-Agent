"""Chat API routes."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from src.service import ChatOrchestratorService

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])


class CreateSessionRequest(BaseModel):
    user_id: str
    knowledge_base_id: str | None = None


class MessageRequest(BaseModel):
    content: str
    knowledge_base_id: str | None = None


@router.post("/sessions")
async def create_session(body: CreateSessionRequest, request: Request):
    svc: ChatOrchestratorService = request.app.state.chat_service
    session = await svc.create_session(body.user_id, body.knowledge_base_id)
    return {"id": session.id, "title": session.title}


@router.post("/sessions/{session_id}/messages")
async def send_message(session_id: str, body: MessageRequest, request: Request):
    svc: ChatOrchestratorService = request.app.state.chat_service
    session = await svc.cache.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    async def event_generator():
        # Pass knowledge_base_id override from message body if provided
        kb_id = body.knowledge_base_id
        if kb_id:
            session = await svc.cache.get(session_id)
            if session:
                session.knowledge_base_id = kb_id
                await svc.cache.set(session)
        async for event in svc.stream_response(session_id, body.content, rag_chunks=None):
            yield {"event": event.split("\n")[0].replace("event: ", ""), "data": event.split("data: ", 1)[-1].strip()}

    return EventSourceResponse(event_generator())


@router.get("/sessions/{session_id}/history")
async def get_history(session_id: str, request: Request):
    svc: ChatOrchestratorService = request.app.state.chat_service
    messages = await svc.repository.get_history(session_id)
    return {
        "session_id": session_id,
        "messages": [
            {"role": m.role, "content": m.content, "sources": m.sources}
            for m in messages
        ],
    }
