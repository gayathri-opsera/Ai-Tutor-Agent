"""Agent reasoning API."""
from __future__ import annotations

from fastapi import APIRouter, Request

from agent import ReasonRequest  # noqa: F401 — re-export from libs/contracts (WO-015)

router = APIRouter(prefix="/api/internal/agent", tags=["agent"])


@router.post("/reason")
async def reason(body: ReasonRequest, request: Request):
    agent = request.app.state.react_agent
    kb_id = body.knowledge_base_id

    # Inject knowledge_base_id into the retriever via a local closure
    original_retriever = agent.retriever
    if original_retriever and kb_id:
        import functools
        async def kb_retriever(query: str):
            return await original_retriever(query, knowledge_base_id=kb_id)
        agent.retriever = kb_retriever

    trace = await agent.reason(body.query, body.confidence)

    # Restore original retriever
    if original_retriever and kb_id:
        agent.retriever = original_retriever

    return {
        "query": trace.query,
        "sub_queries": trace.sub_queries,
        "steps": [
            {"thought": s.thought, "action": s.action, "action_input": s.action_input, "observation": s.observation}
            for s in trace.steps
        ],
        "final_answer": trace.final_answer,
    }
