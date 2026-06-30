"""LLM Gateway FastAPI application entry point.

Starts the Kafka usage logger on startup and shuts it down cleanly on exit.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.llm import router as llm_router
from src.config import settings
from src.kafka.usage_logger import KafkaUsageLogger
from src.router import LLMRouter

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(
        title="LLM Gateway",
        description=(
            "Provider-agnostic LLM inference gateway with circuit breaker, "
            "PII scrubbing, SSE streaming, and Kafka usage telemetry. Implements ADR-001."
        ),
        version="1.0.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # tighten in production via env
        allow_methods=["POST", "GET"],
        allow_headers=["*"],
    )

    app.include_router(llm_router)

    @app.on_event("startup")
    async def startup() -> None:
        # Allow test fixtures to inject a pre-configured router via app.state
        if not hasattr(app.state, "llm_router"):
            usage_logger = KafkaUsageLogger()
            await usage_logger.start()
            app.state.usage_logger = usage_logger
            app.state.llm_router = LLMRouter(usage_logger=usage_logger)
        logger.info("LLM Gateway started — primary=%s fallback=%s", settings.default_provider, settings.fallback_provider)

    @app.on_event("shutdown")
    async def shutdown() -> None:
        if hasattr(app.state, "usage_logger"):
            await app.state.usage_logger.stop()
        logger.info("LLM Gateway shut down.")

    return app


app = create_app()
