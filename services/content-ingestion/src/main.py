"""Content Ingestion FastAPI app."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.cors import CORSMiddleware

from src.api.content import router as content_router
from src.service import ContentIngestionService, DATABASE_URL

logging.basicConfig(level="INFO")
logger = logging.getLogger(__name__)

_events: list[dict] = []


async def _local_publish(topic: str, payload: dict) -> None:
    _events.append({"topic": topic, "payload": payload})


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
    app.state.ingestion_service = ContentIngestionService(pool=pool, publish_event=_local_publish)
    app.state.published_events = _events
    logger.info("Content Ingestion started — connected to PostgreSQL")
    yield
    await pool.close()


def create_app(ingestion_service=None) -> FastAPI:
    """Factory used in tests to inject a mock ingestion service."""
    _app = FastAPI(title="Content Ingestion", version="1.0.0", lifespan=lifespan)
    _app.add_middleware(GZipMiddleware, minimum_size=1000)
    _app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    _app.include_router(content_router)
    if ingestion_service is not None:
        _app.state.ingestion_service = ingestion_service

    @_app.get("/health")
    async def health():
        return {"status": "healthy"}

    return _app


app = create_app()
