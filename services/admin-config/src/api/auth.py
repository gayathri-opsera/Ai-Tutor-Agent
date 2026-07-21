"""User registration endpoint — POST /api/v1/auth/register.

Creates a platform user record from the Keycloak JWT claims on first OAuth
login.  The new user starts with approval_status='pending' and cannot access
any other API endpoint until an admin approves the account.

This endpoint is excluded from the approval-status gate in AuthMiddleware
(see approval_exclude_paths) but still requires a valid Bearer JWT.
"""
from __future__ import annotations

import hashlib
import uuid

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


# ── Self-registration (no JWT required) ──────────────────────────────────────

class SelfRegisterRequest(BaseModel):
    email: EmailStr
    full_name: str
    password: str
    desired_role: str = "Learner"   # "Learner" or "Creator"


class SelfRegisterResponse(BaseModel):
    message: str
    approval_status: str


class MockLoginRequest(BaseModel):
    email: EmailStr
    password: str


class MockLoginResponse(BaseModel):
    token: str
    user_id: str
    roles: list[str]
    approval_status: str
    full_name: str


def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


@router.post("/self-register", response_model=SelfRegisterResponse, status_code=201)
async def self_register(body: SelfRegisterRequest, request: Request) -> SelfRegisterResponse:
    """Public endpoint — register without Keycloak.

    Creates a user with approval_status='pending'.  Admin must approve before
    the user can log in.
    """
    repo: UserRepository = request.app.state.user_repo
    pool = request.app.state.db_pool

    email_lower = body.email.lower().strip()
    email_hash  = hashlib.sha256(email_lower.encode()).hexdigest()

    # Reject if email already registered
    async with pool.acquire() as conn:
        existing = await conn.fetchrow(
            "SELECT id FROM user_local_auth WHERE email = $1", email_lower
        )
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    # Create user record (pending)
    new_user_id = str(uuid.uuid4())
    keycloak_id = f"local-{new_user_id}"
    async with pool.acquire() as conn:
        # Users table (email/name stored as plain bytes since this is mock mode)
        await conn.execute(
            """
            INSERT INTO users (id, email_encrypted, email_hash, full_name_encrypted,
                               keycloak_id, approval_status)
            VALUES ($1::uuid, $2, $3, $4, $5, 'pending'::approval_status_enum)
            """,
            new_user_id,
            body.email.encode(),
            email_hash,
            body.full_name.encode(),
            keycloak_id,
        )
        # Assign desired role (look up role_id from roles table)
        role_id = await conn.fetchval(
            "SELECT id FROM roles WHERE name = $1", body.desired_role
        )
        if role_id:
            await conn.execute(
                """
                INSERT INTO user_roles (user_id, role_id)
                VALUES ($1::uuid, $2)
                ON CONFLICT DO NOTHING
                """,
                new_user_id,
                role_id,
            )
        # Store local auth credentials
        await conn.execute(
            """
            INSERT INTO user_local_auth (user_id, email, password_hash, desired_role)
            VALUES ($1::uuid, $2, $3, $4)
            """,
            new_user_id,
            email_lower,
            _hash_password(body.password),
            body.desired_role,
        )

    return SelfRegisterResponse(
        message="Registration submitted — awaiting admin approval",
        approval_status="pending",
    )


@router.post("/mock-login", response_model=MockLoginResponse)
async def mock_login(body: MockLoginRequest, request: Request) -> MockLoginResponse:
    """Public endpoint — verify email/password for locally-registered users.

    Returns a mock token in the format `mock-reg-<user_id>` that the frontend
    stores and sends as a Bearer token for subsequent requests.
    """
    pool = request.app.state.db_pool
    email_lower = body.email.lower().strip()
    pw_hash     = _hash_password(body.password)

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT la.user_id, la.desired_role, u.approval_status
            FROM user_local_auth la
            JOIN users u ON u.id = la.user_id
            WHERE la.email = $1 AND la.password_hash = $2
            """,
            email_lower,
            pw_hash,
        )
    if not row:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    user_id         = str(row["user_id"])
    approval_status = str(row["approval_status"])
    desired_role    = row["desired_role"]

    # Fetch actual assigned roles via role_id → roles join
    async with pool.acquire() as conn:
        role_rows = await conn.fetch(
            """
            SELECT r.name FROM user_roles ur
            JOIN roles r ON r.id = ur.role_id
            WHERE ur.user_id = $1::uuid
            """,
            user_id,
        )
    roles = [r["name"] for r in role_rows] if role_rows else [desired_role]

    return MockLoginResponse(
        token=f"mock-reg-{user_id}",
        user_id=user_id,
        roles=roles,
        approval_status=approval_status,
        full_name=email_lower,
    )


# ── JWT-authenticated register (existing) ────────────────────────────────────

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
