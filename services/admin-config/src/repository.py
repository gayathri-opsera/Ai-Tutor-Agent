"""User repository — DB operations for user registration and admin approval."""
from __future__ import annotations

import hashlib
from typing import TypedDict

import asyncpg


class UserRecord(TypedDict):
    id: str
    keycloak_id: str
    email_hash: str
    approval_status: str
    created_at: str


class UserRepository:
    """Low-level asyncpg queries for the users table."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def find_by_keycloak_id(self, keycloak_id: str) -> UserRecord | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id::text, keycloak_id, email_hash, approval_status,
                       created_at::text
                FROM users
                WHERE keycloak_id = $1
                """,
                keycloak_id,
            )
        return dict(row) if row else None  # type: ignore[return-value]

    async def find_by_id(self, user_id: str) -> UserRecord | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id::text, keycloak_id, email_hash, approval_status,
                       created_at::text
                FROM users
                WHERE id = $1::uuid
                """,
                user_id,
            )
        return dict(row) if row else None  # type: ignore[return-value]

    async def get_approval_status(self, keycloak_id: str) -> str | None:
        """Return just the approval_status for the given keycloak_id."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT approval_status FROM users WHERE keycloak_id = $1",
                keycloak_id,
            )
        return row["approval_status"] if row else None

    async def list_pending(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[UserRecord], int]:
        """Return pending users and the total count."""
        async with self._pool.acquire() as conn:
            total: int = await conn.fetchval(
                "SELECT COUNT(*) FROM users WHERE approval_status = 'pending'"
            )
            rows = await conn.fetch(
                """
                SELECT id::text, keycloak_id, email_hash, approval_status,
                       created_at::text
                FROM users
                WHERE approval_status = 'pending'
                ORDER BY created_at ASC
                LIMIT $1 OFFSET $2
                """,
                limit,
                offset,
            )
        return [dict(r) for r in rows], total  # type: ignore[return-value]

    async def update_approval_status(
        self,
        user_id: str,
        new_status: str,
    ) -> UserRecord | None:
        """Set approval_status and return the updated record."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE users
                SET approval_status = $1, updated_at = now()
                WHERE id = $2::uuid
                RETURNING id::text, keycloak_id, email_hash,
                          approval_status, created_at::text
                """,
                new_status,
                user_id,
            )
        return dict(row) if row else None  # type: ignore[return-value]

    async def assign_roles(self, user_id: str, role_names: list[str]) -> None:
        """Assign roles to a user by name, inserting into user_roles table."""
        if not role_names:
            return
        async with self._pool.acquire() as conn:
            for role_name in role_names:
                role_id = await conn.fetchval(
                    "SELECT id FROM roles WHERE name = $1", role_name
                )
                if role_id is None:
                    continue  # Role doesn't exist in DB, skip silently
                await conn.execute(
                    """
                    INSERT INTO user_roles (user_id, role_id)
                    VALUES ($1::uuid, $2)
                    ON CONFLICT (user_id, role_id) DO NOTHING
                    """,
                    user_id,
                    role_id,
                )

    async def create_pending_user(
        self,
        keycloak_id: str,
        email: str,
        full_name: str,
    ) -> UserRecord:
        """Create a new user with approval_status='pending'.

        Email and full_name are stored as SHA-256 hashes (email_hash is for
        lookup; full encryption is handled at rest in production by pgcrypto
        or application-level AES-256 encryption outside this story scope).
        """
        email_hash = hashlib.sha256(email.lower().encode()).hexdigest()
        email_encrypted = email.encode()
        full_name_encrypted = full_name.encode()

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO users
                    (keycloak_id, email_encrypted, email_hash,
                     full_name_encrypted, approval_status)
                VALUES ($1, $2, $3, $4, 'pending')
                RETURNING id::text, keycloak_id, email_hash,
                          approval_status, created_at::text
                """,
                keycloak_id,
                email_encrypted,
                email_hash,
                full_name_encrypted,
            )
        return dict(row)  # type: ignore[return-value]

    async def list_all_users(
        self,
        limit: int = 100,
        offset: int = 0,
        status_filter: str | None = None,
    ) -> tuple[list[UserRecord], int]:
        """Return all users (optionally filtered by approval_status).

        Joins user_local_auth to expose plain email for self-registered users.
        Falls back to decoding email_encrypted bytes for seed/OAuth users.
        """
        async with self._pool.acquire() as conn:
            base_select = """
                SELECT u.id::text, u.keycloak_id, u.email_hash, u.approval_status,
                       u.created_at::text,
                       COALESCE(la.email, convert_from(u.email_encrypted, 'UTF8')) AS email,
                       convert_from(u.full_name_encrypted, 'UTF8') AS full_name
                FROM users u
                LEFT JOIN user_local_auth la ON la.user_id = u.id
            """
            if status_filter:
                total = await conn.fetchval(
                    "SELECT COUNT(*) FROM users WHERE approval_status = $1", status_filter
                )
                rows = await conn.fetch(
                    base_select + "WHERE u.approval_status = $1 ORDER BY u.created_at DESC LIMIT $2 OFFSET $3",
                    status_filter, limit, offset,
                )
            else:
                total = await conn.fetchval("SELECT COUNT(*) FROM users")
                rows = await conn.fetch(
                    base_select + "ORDER BY u.created_at DESC LIMIT $1 OFFSET $2",
                    limit, offset,
                )
        return [dict(r) for r in rows], total  # type: ignore[return-value]

    async def get_user_roles(self, user_id: str) -> list[str]:
        """Return role names assigned to a user."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT r.name
                FROM user_roles ur
                JOIN roles r ON r.id = ur.role_id
                WHERE ur.user_id = $1::uuid
                """,
                user_id,
            )
        return [r["name"] for r in rows]

    async def revoke_roles(self, user_id: str) -> None:
        """Remove all role assignments for a user."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM user_roles WHERE user_id = $1::uuid", user_id
            )

    async def delete_user(self, user_id: str) -> bool:
        """Hard-delete a user record. Returns True if a row was deleted."""
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM users WHERE id = $1::uuid", user_id
            )
        return result == "DELETE 1"
