"""Role-based access decorators for FastAPI route handlers."""
from __future__ import annotations

from functools import wraps
from typing import Callable

from fastapi import HTTPException, Request


def require_role(*roles: str) -> Callable:
    """Decorator that enforces one of the given roles on the request user."""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            request: Request | None = kwargs.get("request")
            if request is None:
                for arg in args:
                    if isinstance(arg, Request):
                        request = arg
                        break
            if request is None:
                raise HTTPException(status_code=500, detail="Request context not found")

            user = getattr(request.state, "user", None)
            if user is None:
                raise HTTPException(status_code=401, detail="Authentication required")

            user_roles = getattr(user, "roles", [])
            if not any(role in user_roles for role in roles):
                raise HTTPException(
                    status_code=403,
                    detail=f"Insufficient permissions. Required roles: {list(roles)}",
                )
            return await func(*args, **kwargs)

        return wrapper

    return decorator
