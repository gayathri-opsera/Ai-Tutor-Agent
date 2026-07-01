"""Audit Logging Service — PostgreSQL-backed."""
from __future__ import annotations

import json
import logging
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

import asyncpg
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

DB_DSN = os.getenv(
    "DATABASE_URL",
    "postgresql://ai_tutor:ai_tutor_local_password@postgres:5432/ai_tutor",
)


class AuditLogRequest(BaseModel):
    action: str
    user_id: str           # maps to actor_id
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
    pool = await asyncpg.create_pool(dsn=DB_DSN, min_size=1, max_size=5)
    app.state.pool = pool
    yield
    await pool.close()


app = FastAPI(title="Audit Logging Service", version="1.0.0", lifespan=lifespan)


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
            entry_id, request.user_id, request.action,
            request.resource_type, request.resource_id,
            request.outcome, json.dumps(request.metadata),
        )
    return AuditLogResponse(
        id=entry_id, action=request.action, actor_id=request.user_id,
        resource_id=request.resource_id, resource_type=request.resource_type,
        outcome=request.outcome, metadata=request.metadata, timestamp=now,
    )


@app.get("/api/v1/audit/logs", response_model=AuditLogListResponse)
async def list_audit_logs(
    user_id: str | None = None,
    action: str | None = None,
    limit: int = 100,
) -> AuditLogListResponse:
    async with app.state.pool.acquire() as conn:
        total = await conn.fetchval("SELECT COUNT(*) FROM audit_logs")
        if user_id and action:
            rows = await conn.fetch(
                "SELECT * FROM audit_logs WHERE actor_id=$1 AND action=$2 ORDER BY created_at DESC LIMIT $3",
                user_id, action, limit,
            )
        elif user_id:
            rows = await conn.fetch(
                "SELECT * FROM audit_logs WHERE actor_id=$1 ORDER BY created_at DESC LIMIT $2",
                user_id, limit,
            )
        elif action:
            rows = await conn.fetch(
                "SELECT * FROM audit_logs WHERE action=$1 ORDER BY created_at DESC LIMIT $2",
                action, limit,
            )
        else:
            rows = await conn.fetch("SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT $1", limit)

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
        row = await conn.fetchrow("SELECT * FROM audit_logs WHERE id=$1::uuid", log_id)
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
