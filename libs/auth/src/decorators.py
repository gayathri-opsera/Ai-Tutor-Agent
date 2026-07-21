"""Role-based access control helpers for FastAPI.

`require_role` returns a FastAPI dependency (not a decorator) so that it can be
used with `Depends()` and introspected cleanly by FastAPI's OpenAPI schema
generator.  The returned inner function only takes a `Request`, which FastAPI
handles natively without emitting a JSON schema for it.
"""
from __future__ import annotations

from typing import Callable

from fastapi import HTTPException, Request


def require_role(*roles: str) -> Callable[[Request], None]:
    """Return a FastAPI dependency that enforces one of the given roles."""

    async def _check(request: Request) -> None:
        user = getattr(request.state, "user", None)
        if user is None:
            raise HTTPException(status_code=401, detail="Authentication required")

        user_roles = getattr(user, "roles", [])
        if not any(role in user_roles for role in roles):
            raise HTTPException(
                status_code=403,
                detail=f"Insufficient permissions. Required roles: {list(roles)}",
            )

    return _check
