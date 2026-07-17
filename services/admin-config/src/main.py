"""Admin Config Service — FastAPI entrypoint."""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI

from src.api.admin_users import router as admin_users_router
from src.api.data_subject import router as data_subject_router
from src.api.auth import router as auth_router
from src.api.config import router as config_router
from src.repository import UserRepository
from src.service import AdminConfigService, DB_DSN

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = await asyncpg.create_pool(dsn=DB_DSN, min_size=1, max_size=5)
    app.state.admin_config = AdminConfigService(pool=pool)
    app.state.user_repo = UserRepository(pool=pool)
    yield
    await pool.close()


app = FastAPI(title="Admin Configuration Service", lifespan=lifespan)
app.include_router(config_router)
app.include_router(auth_router)
app.include_router(admin_users_router)
app.include_router(data_subject_router)


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "admin-config"}
