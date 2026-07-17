"""Assessment Service — FastAPI entrypoint."""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware

from src.api.assessment import router
from src.service import AssessmentService, DB_DSN

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = await asyncpg.create_pool(dsn=DB_DSN, min_size=1, max_size=5)
    app.state.assessment_service = AssessmentService(pool=pool)
    yield
    await pool.close()


app = FastAPI(title="Assessment Engine", lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.include_router(router)


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "assessment"}
