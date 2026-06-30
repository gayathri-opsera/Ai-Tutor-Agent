"""Agent Reasoning FastAPI app."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.agent import ReActAgent
from src.api.agent import router as agent_router
from src.web_search import WebSearchService


async def _mock_retriever(query: str):
    return [{"text": f"Retrieved context for {query}", "score": 0.9}]


def create_app() -> FastAPI:
    app = FastAPI(title="Agent Reasoning", version="1.0.0")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    app.include_router(agent_router)

    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    @app.on_event("startup")
    async def startup():
        web = WebSearchService()
        app.state.react_agent = ReActAgent(
            retriever=_mock_retriever,
            web_search=web.search_if_needed,
        )

    web = WebSearchService()
    app.state.react_agent = ReActAgent(
        retriever=_mock_retriever,
        web_search=web.search_if_needed,
    )
    return app


app = create_app()
