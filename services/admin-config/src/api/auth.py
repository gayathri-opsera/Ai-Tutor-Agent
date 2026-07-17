"""User registration endpoint — POST /api/v1/auth/register.

Creates a platform user record from the Keycloak JWT claims on first OAuth
login.  The new user starts with approval_status='pending' and cannot access
any other API endpoint until an admin approves the account.

This endpoint is excluded from the approval-status gate in AuthMiddleware
(see approval_exclude_paths) but still requires a valid Bearer JWT.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, EmailStr

from src.repository import UserRepository

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: EmailStr
    full_name: str


class RegisterResponse(BaseModel):
    id: str
    keycloak_id: str
    email_hash: str
    approval_status: str
    created_at: str
    message: str


@router.post("/register", response_model=RegisterResponse, status_code=201)
async def register(body: RegisterRequest, request: Request) -> RegisterResponse:
    """Register a new user from Keycloak OAuth claims.

    - If a user with this keycloak_id already exists, returns 200 with their
      current record (idempotent — safe for retry on network failure).
    - If not, creates a user with approval_status='pending'.
    - Requires a valid Bearer JWT (set by AuthMiddleware in request.state.user).
    """
    user = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")

    keycloak_id: str = user.sub
    repo: UserRepository = request.app.state.user_repo

    existing = await repo.find_by_keycloak_id(keycloak_id)
    if existing:
        return RegisterResponse(
            **existing,
            message="User already registered",
        )

    created = await repo.create_pending_user(
        keycloak_id=keycloak_id,
        email=body.email,
        full_name=body.full_name,
    )
    return RegisterResponse(
        **created,
        message="Registration submitted — awaiting admin approval",
    )
