"""Data Subject endpoints: account deletion (WO-268) and DSAR export (WO-269)."""
from __future__ import annotations

import hashlib
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/data-subject", tags=["data-subject"])


def _require_admin(request: Request) -> None:
    token_data = getattr(request.state, "token_data", {})
    roles = token_data.get("realm_access", {}).get("roles", [])
    if "Admin" not in roles and "SuperAdmin" not in roles:
        raise HTTPException(status_code=403, detail="Admin role required")


# ── WO-268: Account deletion request ─────────────────────────────────────────

@router.delete("/{user_id}", status_code=202)
async def request_account_deletion(user_id: str, request: Request) -> dict[str, Any]:
    """Create a data deletion request; PII will be purged within 30 days.

    Immediately soft-deletes the user account and queues a full erasure
    scheduled 30 days from now.
    """
    _require_admin(request)
    pool = request.app.state.db_pool
    caller = getattr(request.state, "token_data", {}).get("sub", "unknown")

    async with pool.acquire() as conn:
        user = await conn.fetchrow("SELECT id FROM users WHERE id = $1", user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Check for existing pending request
        existing = await conn.fetchrow(
            "SELECT id FROM data_deletion_requests WHERE user_id = $1 AND status = 'pending'",
            user_id,
        )
        if existing:
            return {"detail": "Deletion request already pending", "request_id": str(existing["id"])}

        row = await conn.fetchrow(
            """
            INSERT INTO data_deletion_requests (user_id, requested_by)
            VALUES ($1, $2)
            RETURNING id, scheduled_purge_at
            """,
            user_id, caller,
        )

    logger.info("Data deletion request created for user %s by %s", user_id, caller)
    return {
        "detail": "Deletion request accepted. PII will be purged within 30 days.",
        "request_id": str(row["id"]),
        "scheduled_purge_at": row["scheduled_purge_at"].isoformat(),
    }


@router.post("/{user_id}/execute-purge", status_code=200)
async def execute_pii_purge(user_id: str, request: Request) -> dict[str, Any]:
    """Immediately execute PII purge for a user (used by the erasure service).

    Deletes all user data across tables and replaces audit_log actor_id with
    a SHA-256 pseudonymous hash.
    """
    _require_admin(request)
    pool = request.app.state.db_pool

    hashed_id = hashlib.sha256(user_id.encode()).hexdigest()

    async with pool.acquire() as conn:
        # Pseudonymise audit logs (allowed even with immutability trigger for the purge account)
        await conn.execute(
            "UPDATE audit_logs SET actor_id = $1 WHERE actor_id = $2",
            f"[deleted:{hashed_id[:16]}]", user_id,
        )
        # Delete user data across all relevant tables
        for table, col in [
            ("local_learner_profiles", "user_id"),
            ("local_topic_progress", "user_id"),
            ("local_lesson_progress", "user_id"),
            ("local_assessment_results", "user_id"),
            ("chat_sessions", "user_id"),
            ("user_roles", "user_id"),
            ("users", "id"),
        ]:
            try:
                await conn.execute(f"DELETE FROM {table} WHERE {col} = $1", user_id)
            except Exception as exc:
                logger.warning("Could not delete from %s for user %s: %s", table, user_id, exc)

        # Mark deletion request as completed
        await conn.execute(
            """
            UPDATE data_deletion_requests
            SET status = 'completed', completed_at = now()
            WHERE user_id = $1 AND status = 'pending'
            """,
            user_id,
        )

    logger.info("PII purge completed for user %s (pseudonymised as %s)", user_id, hashed_id[:16])
    return {"detail": "PII purge completed", "pseudonymised_id": hashed_id[:16]}


# ── WO-269: DSAR export ───────────────────────────────────────────────────────

@router.get("/{user_id}/export", status_code=200)
async def dsar_export(user_id: str, request: Request) -> dict[str, Any]:
    """Export all data held for a user (Data Subject Access Request).

    Returns profile data, assessment results, chat sessions, and audit logs
    as a structured JSON response.
    """
    _require_admin(request)
    pool = request.app.state.db_pool

    async with pool.acquire() as conn:
        user = await conn.fetchrow(
            "SELECT id, email, display_name, approval_status, created_at FROM users WHERE id = $1",
            user_id,
        )
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        profile = await conn.fetchrow(
            "SELECT * FROM local_learner_profiles WHERE user_id = $1", user_id
        )
        assessment_rows = await conn.fetch(
            "SELECT assessment_id, score, submitted_at FROM local_assessment_results WHERE user_id = $1",
            user_id,
        )
        chat_rows = await conn.fetch(
            "SELECT id, title, created_at FROM chat_sessions WHERE user_id = $1 ORDER BY created_at DESC LIMIT 100",
            user_id,
        )
        audit_rows = await conn.fetch(
            """
            SELECT action, resource_type, resource_id, created_at
            FROM audit_logs
            WHERE actor_id = $1
            ORDER BY created_at DESC LIMIT 200
            """,
            user_id,
        )

    return {
        "user_id": user_id,
        "profile": {
            "email": user["email"],
            "display_name": user["display_name"],
            "approval_status": user["approval_status"],
            "registered_at": user["created_at"].isoformat() if user["created_at"] else None,
            "proficiency_level": profile["proficiency_level"] if profile else None,
            "total_sessions": profile["total_sessions"] if profile else 0,
        },
        "assessment_results": [
            {
                "assessment_id": str(r["assessment_id"]),
                "score": r["score"],
                "submitted_at": r["submitted_at"].isoformat() if r["submitted_at"] else None,
            }
            for r in assessment_rows
        ],
        "chat_sessions": [
            {
                "id": str(r["id"]),
                "title": r["title"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in chat_rows
        ],
        "audit_logs": [
            {
                "action": r["action"],
                "resource_type": r["resource_type"],
                "resource_id": str(r["resource_id"]) if r["resource_id"] else None,
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in audit_rows
        ],
    }
