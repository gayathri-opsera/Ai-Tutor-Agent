"""Agent Reasoning FastAPI app — connects to real RAG pipeline."""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.cors import CORSMiddleware

from src.agent import ReActAgent
from src.api.agent import router as agent_router
from src.web_search import WebSearchService
from service_middleware import ServiceAuthMiddleware  # libs/auth/src/ in PYTHONPATH via Dockerfile

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

RAG_SERVICE_URL = os.getenv("RAG_SERVICE_URL", "http://rag-pipeline:8002")


async def _real_retriever(query: str, knowledge_base_id: str | None = None):
    """Call the live RAG pipeline to retrieve relevant chunks."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{RAG_SERVICE_URL}/api/internal/rag/retrieve",
                json={
                    "query": query,
                    "knowledge_base_id": knowledge_base_id or "",
                    "top_k": 5,
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("chunks", [])
    except Exception:
        pass
    return [{"text": f"No context found for: {query[:60]}", "score": 0.1}]


@asynccontextmanager
async def lifespan(app: FastAPI):
    web = WebSearchService()
    app.state.react_agent = ReActAgent(
        retriever=_real_retriever,
        web_search=web.search_if_needed,
    )
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Agent Reasoning", version="1.0.0", lifespan=lifespan)
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    app.add_middleware(
        ServiceAuthMiddleware,
        exclude_paths=["/health", "/ready", "/metrics", "/docs", "/openapi.json", "/api/internal"],
    )
    app.include_router(agent_router)

    @app.get("/health")
    async def health():
        return {"status": "healthy", "service": "agent-reasoning"}

    return app


app = create_app()
