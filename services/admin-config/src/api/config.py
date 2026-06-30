"""Admin config API."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/admin/config", tags=["admin"])


class ConfigValue(BaseModel):
    value: Any


@router.get("/{key}")
async def get_config(key: str, organization_id: str = "default", request: Request = None):
    svc = request.app.state.admin_config
    entry = svc.get(organization_id, key)
    if not entry:
        raise HTTPException(404, "Config not found")
    return {"key": key, "value": entry.value, "organization_id": organization_id}


@router.put("/{key}")
async def put_config(key: str, body: ConfigValue, organization_id: str = "default", request: Request = None):
    svc = request.app.state.admin_config
    entry = svc.set(organization_id, key, body.value)
    return {"key": key, "value": entry.value, "organization_id": organization_id}


@router.get("")
async def list_config(organization_id: str = "default", request: Request = None):
    svc = request.app.state.admin_config
    entries = svc.list_all(organization_id)
    return {"configs": [{"key": e.key, "value": e.value} for e in entries]}
