"""Content Ingestion FastAPI app."""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.content import router as content_router
from src.service import ContentIngestionService

logging.basicConfig(level="INFO")
logger = logging.getLogger(__name__)

_events: list[dict] = []


async def _local_publish(topic: str, payload: dict) -> None:
    _events.append({"topic": topic, "payload": payload})


def create_app() -> FastAPI:
    app = FastAPI(title="Content Ingestion", version="1.0.0")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    app.include_router(content_router)

    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    @app.on_event("startup")
    async def startup():
        app.state.ingestion_service = ContentIngestionService(publish_event=_local_publish)
        app.state.published_events = _events
        logger.info("Content Ingestion started")

    app.state.ingestion_service = ContentIngestionService(publish_event=_local_publish)
    app.state.published_events = _events
    return app


app = create_app()
