"""Learner Profile Service — FastAPI entrypoint."""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI

from src.api.profile import router
from src.service import LearnerProfileService, DB_DSN

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = await asyncpg.create_pool(dsn=DB_DSN, min_size=1, max_size=5)
    app.state.profile_service = LearnerProfileService(pool=pool)
    yield
    await pool.close()


app = FastAPI(title="Learner Profile Service", lifespan=lifespan)
app.include_router(router)


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "learner-profile"}
