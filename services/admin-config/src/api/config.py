"""Admin config API."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/admin/config", tags=["admin"])


class ConfigValue(BaseModel):
    value: Any
    description: str = ""


@router.get("/{key}")
async def get_config(key: str, organization_id: str = "default", request: Request = None):
    svc = request.app.state.admin_config
    entry = await svc.get(organization_id, key)
    if not entry:
        raise HTTPException(404, f"Config key '{key}' not found")
    return {"key": entry["config_key"], "value": entry["config_value"], "organization_id": entry["org_id"]}


@router.put("/{key}")
async def put_config(key: str, body: ConfigValue, organization_id: str = "default", request: Request = None):
    svc = request.app.state.admin_config
    entry = await svc.set(organization_id, key, body.value, body.description)
    return {"key": key, "value": entry["value"], "organization_id": organization_id}


@router.delete("/{key}", status_code=204)
async def delete_config(key: str, organization_id: str = "default", request: Request = None):
    svc = request.app.state.admin_config
    await svc.delete(organization_id, key)


@router.get("")
async def list_config(organization_id: str = "default", request: Request = None):
    svc = request.app.state.admin_config
    entries = await svc.list_all(organization_id)
    return {
        "configs": [{"key": e["config_key"], "value": e["config_value"], "description": e.get("description", "")} for e in entries]
    }
