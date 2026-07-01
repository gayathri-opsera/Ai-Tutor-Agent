"""Analytics Service — FastAPI entrypoint."""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI

from src.api.analytics import router
from src.service import AnalyticsService, DB_DSN

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = await asyncpg.create_pool(dsn=DB_DSN, min_size=1, max_size=5)
    app.state.analytics = AnalyticsService(pool=pool)
    yield
    await pool.close()


app = FastAPI(title="Analytics Service", lifespan=lifespan)
app.include_router(router)


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "analytics"}
