"""Admin user management API — full CRUD for user records.

All endpoints require Admin or SuperAdmin role.

Endpoints:
  GET    /api/v1/admin/users                 — paginated list of ALL users
  GET    /api/v1/admin/users/pending         — paginated pending list
  GET    /api/v1/admin/users/{user_id}       — get single user + roles
  PUT    /api/v1/admin/users/{user_id}       — update status + roles
  DELETE /api/v1/admin/users/{user_id}       — hard-delete user
  POST   /api/v1/admin/users/{user_id}/approve — approve + assign roles
  POST   /api/v1/admin/users/{user_id}/reject  — reject registration
"""
from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from src.repository import UserRecord, UserRepository

try:
    from src.kafka_events import emit_approval_event
except ImportError:
    # Kafka not configured (test/dev environment)
    async def emit_approval_event(*args: Any, **kwargs: Any) -> None:  # type: ignore[misc]
        pass

logger = logging.getLogger(__name__)

AUDIT_SERVICE_URL = os.getenv("AUDIT_SERVICE_URL", "http://audit:8012")

router = APIRouter(prefix="/api/v1/admin/users", tags=["admin-users"])


# ── Pydantic models ──────────────────────────────────────────────────────────

class PendingUserResponse(BaseModel):
    id: str
    keycloak_id: str
    email_hash: str
    approval_status: str
    created_at: str


class PendingListResponse(BaseModel):
    users: list[PendingUserResponse]
    total: int
    limit: int
    offset: int


class ApproveRequest(BaseModel):
    roles: list[str] = ["Learner"]


class ApprovalActionResponse(BaseModel):
    user_id: str
    keycloak_id: str
    approval_status: str
    roles_assigned: list[str] = []
    message: str


class UserDetailResponse(BaseModel):
    id: str
    keycloak_id: str
    email_hash: str
    approval_status: str
    roles: list[str]
    created_at: str
    email: str = ""
    full_name: str = ""


class AllUsersResponse(BaseModel):
    users: list[UserDetailResponse]
    total: int
    limit: int
    offset: int


class UpdateUserRequest(BaseModel):
    approval_status: str | None = None
    roles: list[str] | None = None


# ── Helper ────────────────────────────────────────────────────────────────────

async def _require_admin(request: Request) -> None:
    """Raise 403 if the requester does not have Admin or SuperAdmin role."""
    user = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    allowed = {"Admin", "SuperAdmin"}
    if not any(role in allowed for role in getattr(user, "roles", [])):
        raise HTTPException(
            status_code=403,
            detail="Insufficient permissions — Admin or SuperAdmin role required",
        )


async def _post_audit_log(
    actor_id: str,
    action: str,
    resource_id: str,
    outcome: str = "success",
    metadata: dict | None = None,
) -> None:
    """Fire-and-forget audit log to the audit service (non-blocking)."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                f"{AUDIT_SERVICE_URL}/api/v1/audit/log",
                json={
                    "action": action,
                    "actor_id": actor_id,
                    "resource_id": resource_id,
                    "resource_type": "user",
                    "outcome": outcome,
                    "metadata": metadata or {},
                },
            )
    except Exception as exc:
        logger.warning("Audit log delivery failed (non-blocking): %s", exc)


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/pending", response_model=PendingListResponse)
async def list_pending_users(
    request: Request,
    limit: int = 50,
    offset: int = 0,
) -> PendingListResponse:
    """Return paginated list of users awaiting admin approval.

    Requires Admin or SuperAdmin role.
    """
    await _require_admin(request)
    repo: UserRepository = request.app.state.user_repo
    users, total = await repo.list_pending(limit=limit, offset=offset)
    return PendingListResponse(
        users=[PendingUserResponse(**u) for u in users],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/{user_id}/approve", response_model=ApprovalActionResponse, status_code=200)
async def approve_user(
    user_id: str,
    body: ApproveRequest,
    request: Request,
) -> ApprovalActionResponse:
    """Approve a pending user registration and assign roles.

    - Sets approval_status = 'approved' in the users table
    - Inserts rows into user_roles for each role in body.roles
    - Emits a UserApprovalCompleted Kafka event
    - Creates an audit log entry

    Requires Admin or SuperAdmin role.
    """
    await _require_admin(request)
    actor = request.state.user

    repo: UserRepository = request.app.state.user_repo
    existing = await repo.find_by_id(user_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"User {user_id!r} not found")

    updated = await repo.update_approval_status(user_id, "approved")
    await repo.assign_roles(user_id, body.roles)

    # Emit Kafka event (non-blocking)
    await emit_approval_event(
        actor_id=actor.sub,
        user_id=user_id,
        keycloak_id=existing["keycloak_id"],
        outcome="approved",
        roles_assigned=body.roles,
    )

    # Audit log (fire-and-forget)
    await _post_audit_log(
        actor_id=actor.sub,
        action="user.approved",
        resource_id=user_id,
        outcome="success",
        metadata={"roles_assigned": body.roles},
    )

    return ApprovalActionResponse(
        user_id=user_id,
        keycloak_id=existing["keycloak_id"],
        approval_status="approved",
        roles_assigned=body.roles,
        message="User approved successfully",
    )


@router.post("/{user_id}/reject", response_model=ApprovalActionResponse, status_code=200)
async def reject_user(
    user_id: str,
    request: Request,
) -> ApprovalActionResponse:
    """Reject a pending user registration.

    - Sets approval_status = 'rejected' in the users table
    - Emits a UserApprovalCompleted Kafka event with outcome='rejected'
    - Creates an audit log entry

    Requires Admin or SuperAdmin role.
    """
    await _require_admin(request)
    actor = request.state.user

    repo: UserRepository = request.app.state.user_repo
    existing = await repo.find_by_id(user_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"User {user_id!r} not found")

    await repo.update_approval_status(user_id, "rejected")

    # Emit Kafka event (non-blocking)
    await emit_approval_event(
        actor_id=actor.sub,
        user_id=user_id,
        keycloak_id=existing["keycloak_id"],
        outcome="rejected",
        roles_assigned=[],
    )

    # Audit log (fire-and-forget)
    await _post_audit_log(
        actor_id=actor.sub,
        action="user.rejected",
        resource_id=user_id,
        outcome="success",
        metadata={},
    )

    return ApprovalActionResponse(
        user_id=user_id,
        keycloak_id=existing["keycloak_id"],
        approval_status="rejected",
        roles_assigned=[],
        message="User rejected",
    )


# ── Full CRUD ─────────────────────────────────────────────────────────────────

@router.get("", response_model=AllUsersResponse)
async def list_all_users(
    request: Request,
    limit: int = 100,
    offset: int = 0,
    status: str | None = None,
) -> AllUsersResponse:
    """Return all users (admin only). Optionally filter by approval_status."""
    await _require_admin(request)
    repo: UserRepository = request.app.state.user_repo
    users, total = await repo.list_all_users(limit=limit, offset=offset, status_filter=status)
    result = []
    for u in users:
        roles = await repo.get_user_roles(u["id"])
        result.append(UserDetailResponse(
            **{k: v for k, v in u.items() if k in ("id", "keycloak_id", "email_hash", "approval_status", "created_at")},
            roles=roles,
            email=u.get("email", "") or "",
            full_name=u.get("full_name", "") or "",
        ))
    return AllUsersResponse(users=result, total=total, limit=limit, offset=offset)


@router.get("/{user_id}", response_model=UserDetailResponse)
async def get_user(user_id: str, request: Request) -> UserDetailResponse:
    """Return a single user with their roles."""
    await _require_admin(request)
    repo: UserRepository = request.app.state.user_repo
    pool = request.app.state.db_pool
    user = await repo.find_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    # Fetch email/full_name via join
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT COALESCE(la.email, convert_from(u.email_encrypted, 'UTF8')) AS email,
                   convert_from(u.full_name_encrypted, 'UTF8') AS full_name
            FROM users u LEFT JOIN user_local_auth la ON la.user_id = u.id
            WHERE u.id = $1::uuid
            """,
            user_id,
        )
    roles = await repo.get_user_roles(user_id)
    return UserDetailResponse(
        **{k: v for k, v in user.items() if k in ("id", "keycloak_id", "email_hash", "approval_status", "created_at")},
        roles=roles,
        email=row["email"] if row else "",
        full_name=row["full_name"] if row else "",
    )


@router.put("/{user_id}", response_model=UserDetailResponse)
async def update_user(user_id: str, body: UpdateUserRequest, request: Request) -> UserDetailResponse:
    """Update a user's approval_status and/or roles."""
    await _require_admin(request)
    actor = request.state.user
    repo: UserRepository = request.app.state.user_repo

    existing = await repo.find_by_id(user_id)
    if not existing:
        raise HTTPException(status_code=404, detail="User not found")

    if body.approval_status:
        await repo.update_approval_status(user_id, body.approval_status)
    if body.roles is not None:
        await repo.revoke_roles(user_id)
        await repo.assign_roles(user_id, body.roles)

    await _post_audit_log(
        actor_id=actor.sub,
        action="user.updated",
        resource_id=user_id,
        outcome="success",
        metadata={"approval_status": body.approval_status, "roles": body.roles},
    )

    updated = await repo.find_by_id(user_id)
    roles = await repo.get_user_roles(user_id)
    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT COALESCE(la.email, convert_from(u.email_encrypted, 'UTF8')) AS email,
                   convert_from(u.full_name_encrypted, 'UTF8') AS full_name
            FROM users u LEFT JOIN user_local_auth la ON la.user_id = u.id
            WHERE u.id = $1::uuid
            """,
            user_id,
        )
    return UserDetailResponse(
        **{k: v for k, v in updated.items() if k in ("id", "keycloak_id", "email_hash", "approval_status", "created_at")},  # type: ignore[union-attr]
        roles=roles,
        email=row["email"] if row else "",
        full_name=row["full_name"] if row else "",
    )


@router.delete("/{user_id}", status_code=204)
async def delete_user(user_id: str, request: Request) -> None:
    """Hard-delete a user. Cascades to sessions, roles, and profile data."""
    await _require_admin(request)
    actor = request.state.user
    repo: UserRepository = request.app.state.user_repo

    existing = await repo.find_by_id(user_id)
    if not existing:
        raise HTTPException(status_code=404, detail="User not found")

    await repo.delete_user(user_id)

    await _post_audit_log(
        actor_id=actor.sub,
        action="user.deleted",
        resource_id=user_id,
        outcome="success",
    )
