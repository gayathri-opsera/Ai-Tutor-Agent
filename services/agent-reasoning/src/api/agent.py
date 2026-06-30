"""Agent reasoning API."""
from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/internal/agent", tags=["agent"])


class ReasonRequest(BaseModel):
    query: str
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    knowledge_base_id: str | None = None


@router.post("/reason")
async def reason(body: ReasonRequest, request: Request):
    agent = request.app.state.react_agent
    trace = await agent.reason(body.query, body.confidence)
    return {
        "query": trace.query,
        "sub_queries": trace.sub_queries,
        "steps": [
            {"thought": s.thought, "action": s.action, "action_input": s.action_input, "observation": s.observation}
            for s in trace.steps
        ],
        "final_answer": trace.final_answer,
    }
