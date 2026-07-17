"""Audit Logging Service — PostgreSQL-backed, immutable append-only log."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

import asyncpg
from fastapi import FastAPI, HTTPException
from fastapi.middleware.gzip import GZipMiddleware
from pydantic import BaseModel

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

# Credential loaded via shared secrets provider — no plaintext fallback in code.
try:
    from provider import get_db_dsn  # type: ignore[import]
    DB_DSN = get_db_dsn()
except ImportError:
    DB_DSN = os.environ["DATABASE_URL"]

# Explicit column projection — avoids fetching large metadata JSONB on list queries.
_AUDIT_COLS = "id, actor_id, action, resource_type, resource_id, outcome, metadata, created_at"

# Pool sizing constants (named rather than magic numbers).
_POOL_MIN = int(os.getenv("DB_POOL_MIN", "1"))
_POOL_MAX = int(os.getenv("DB_POOL_MAX", "5"))


class AuditLogRequest(BaseModel):
    action: str
    actor_id: str          # canonical field name — same as the DB column
    resource_id: str
    resource_type: str = "generic"
    outcome: str = "success"
    metadata: dict[str, Any] = {}


class AuditLogResponse(BaseModel):
    id: str
    action: str
    actor_id: str
    resource_id: str
    resource_type: str
    outcome: str
    metadata: dict[str, Any]
    timestamp: datetime


class AuditLogListResponse(BaseModel):
    entries: list[AuditLogResponse]
    total: int


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = await asyncpg.create_pool(dsn=DB_DSN, min_size=_POOL_MIN, max_size=_POOL_MAX)
    app.state.pool = pool
    yield
    await pool.close()


app = FastAPI(title="Audit Logging Service", version="1.0.0", lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=1000)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "audit"}


@app.post("/api/v1/audit/log", response_model=AuditLogResponse, status_code=201)
async def create_audit_log(request: AuditLogRequest) -> AuditLogResponse:
    entry_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    async with app.state.pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO audit_logs (id, actor_id, action, resource_type, resource_id, outcome, metadata)
            VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)
            """,
            entry_id, request.actor_id, request.action,
            request.resource_type, request.resource_id,
            request.outcome, json.dumps(request.metadata),
        )
    return AuditLogResponse(
        id=entry_id, action=request.action, actor_id=request.actor_id,
        resource_id=request.resource_id, resource_type=request.resource_type,
        outcome=request.outcome, metadata=request.metadata, timestamp=now,
    )


@app.get("/api/v1/audit/logs", response_model=AuditLogListResponse)
async def list_audit_logs(
    actor_id: str | None = None,
    action: str | None = None,
    limit: int = 100,
) -> AuditLogListResponse:
    async with app.state.pool.acquire() as conn:
        # Filtered COUNT avoids a full table scan when filters are active.
        if actor_id and action:
            total, rows = await asyncio.gather(
                conn.fetchval(
                    "SELECT COUNT(*) FROM audit_logs WHERE actor_id=$1 AND action=$2",
                    actor_id, action,
                ),
                conn.fetch(
                    f"SELECT {_AUDIT_COLS} FROM audit_logs WHERE actor_id=$1 AND action=$2 ORDER BY created_at DESC LIMIT $3",
                    actor_id, action, limit,
                ),
            )
        elif actor_id:
            total, rows = await asyncio.gather(
                conn.fetchval("SELECT COUNT(*) FROM audit_logs WHERE actor_id=$1", actor_id),
                conn.fetch(
                    f"SELECT {_AUDIT_COLS} FROM audit_logs WHERE actor_id=$1 ORDER BY created_at DESC LIMIT $2",
                    actor_id, limit,
                ),
            )
        elif action:
            total, rows = await asyncio.gather(
                conn.fetchval("SELECT COUNT(*) FROM audit_logs WHERE action=$1", action),
                conn.fetch(
                    f"SELECT {_AUDIT_COLS} FROM audit_logs WHERE action=$1 ORDER BY created_at DESC LIMIT $2",
                    action, limit,
                ),
            )
        else:
            total, rows = await asyncio.gather(
                conn.fetchval("SELECT COUNT(*) FROM audit_logs"),
                conn.fetch(
                    f"SELECT {_AUDIT_COLS} FROM audit_logs ORDER BY created_at DESC LIMIT $1",
                    limit,
                ),
            )

    return AuditLogListResponse(
        entries=[
            AuditLogResponse(
                id=str(r["id"]),
                action=r["action"],
                actor_id=str(r["actor_id"]),
                resource_id=str(r["resource_id"] or ""),
                resource_type=str(r["resource_type"] or "generic"),
                outcome=str(r["outcome"] or "success"),
                metadata=r["metadata"] or {},
                timestamp=r["created_at"],
            )
            for r in rows
        ],
        total=total or 0,
    )


@app.get("/api/v1/audit/logs/{log_id}", response_model=AuditLogResponse)
async def get_audit_log(log_id: str) -> AuditLogResponse:
    async with app.state.pool.acquire() as conn:
        row = await conn.fetchrow(
            f"SELECT {_AUDIT_COLS} FROM audit_logs WHERE id=$1::uuid", log_id
        )
    if not row:
        raise HTTPException(status_code=404, detail=f"Audit log {log_id!r} not found")
    return AuditLogResponse(
        id=str(row["id"]),
        action=row["action"],
        actor_id=str(row["actor_id"]),
        resource_id=str(row["resource_id"] or ""),
        resource_type=str(row["resource_type"] or "generic"),
        outcome=str(row["outcome"] or "success"),
        metadata=row["metadata"] or {},
        timestamp=row["created_at"],
    )
