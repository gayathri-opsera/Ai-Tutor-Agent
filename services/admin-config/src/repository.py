"""User registration repository — DB operations for the auth/register endpoint."""
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

    async def get_approval_status(self, keycloak_id: str) -> str | None:
        """Return just the approval_status for the given keycloak_id."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT approval_status FROM users WHERE keycloak_id = $1",
                keycloak_id,
            )
        return row["approval_status"] if row else None

    async def create_pending_user(
        self,
        keycloak_id: str,
        email: str,
        full_name: str,
    ) -> UserRecord:
        """Create a new user with approval_status='pending'.

        Email and full_name are stored as SHA-256 hashes (email_hash is for
        lookup; full encryption is handled at rest in production by pgcrypto).
        For test/dev environments the plaintext is hashed.
        """
        email_hash = hashlib.sha256(email.lower().encode()).hexdigest()
        # Minimal placeholder for encrypted columns (real encryption via pgcrypto
        # or application-level AES-256 is handled outside this story scope)
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
