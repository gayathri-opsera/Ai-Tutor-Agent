"""Content management — PostgreSQL-backed CRUD."""
from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import asyncpg


DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "postgresql://ai_tutor:ai_tutor_local_password@postgres:5432/ai_tutor"  # local-dev only — set DATABASE_URL in production,
)


@dataclass
class KnowledgeBase:
    id: str
    name: str
    organization_id: str
    description: str = ""
    is_active: bool = True
    age_group: str | None = None
    created_by_keycloak_id: str | None = None
    approval_status: str = "pending_review"  # matches DB default
    doc_count: int = 0


@dataclass
class Document:
    id: str
    knowledge_base_id: str
    title: str
    is_active: bool = True
    content_type: str = "text"
    chunk_count: int = 0
    retired_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class ContentManagementService:
    """Thin async wrapper around the PostgreSQL knowledge_bases / documents tables."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    # ── Knowledge Bases ───────────────────────────────────────────────────────

    async def create_kb(
        self, name: str, organization_id: str, description: str = "",
        age_group: str | None = None, created_by_keycloak_id: str | None = None,
    ) -> KnowledgeBase:
        kb_id = str(uuid.uuid4())
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO knowledge_bases (id, name, description, organization_id,
                                             age_group, created_by_keycloak_id)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (id) DO NOTHING
                """,
                kb_id, name, description, organization_id,
                age_group, created_by_keycloak_id,
            )
        return KnowledgeBase(
            id=kb_id, name=name, organization_id=organization_id,
            description=description, age_group=age_group,
            created_by_keycloak_id=created_by_keycloak_id,
        )

    async def get_kb(self, kb_id: str) -> KnowledgeBase | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, name, description, organization_id, is_active, "
                "age_group, created_by_keycloak_id, approval_status "
                "FROM knowledge_bases WHERE id = $1",
                kb_id,
            )
        if not row:
            return None
        return KnowledgeBase(
            id=str(row["id"]),
            name=row["name"],
            description=row["description"] or "",
            organization_id=row["organization_id"],
            is_active=row["is_active"],
            age_group=row.get("age_group"),
            created_by_keycloak_id=row.get("created_by_keycloak_id"),
            approval_status=str(row.get("approval_status", "approved")),
        )

    async def get_kb_raw(self, kb_id: str) -> dict | None:
        """Return a raw dict row including ownership fields."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, created_by_keycloak_id FROM knowledge_bases WHERE id = $1",
                kb_id,
            )
        if not row:
            return None
        return {"id": str(row["id"]), "created_by_keycloak_id": row.get("created_by_keycloak_id")}

    async def list_kbs(
        self, organization_id: str, include_archived: bool = False,
        approved_only: bool = True, caller_keycloak_id: str | None = None
    ) -> list[KnowledgeBase]:
        async with self._pool.acquire() as conn:
            # Callers see approved KBs + their own KBs regardless of status.
            if approved_only and caller_keycloak_id:
                approval_clause = (
                    "AND (approval_status = 'approved' "
                    "     OR created_by_keycloak_id = $2)"
                )
                extra_params: list = [caller_keycloak_id]
            elif approved_only:
                approval_clause = "AND approval_status = 'approved'"
                extra_params = []
            else:
                approval_clause = ""
                extra_params = []

            if include_archived:
                rows = await conn.fetch(
                    f"""
                    SELECT id, name, description, organization_id, is_active,
                           age_group, created_by_keycloak_id, approval_status,
                           (SELECT COUNT(*) FROM documents d
                            WHERE d.knowledge_base_id = kb.id AND d.status = 'active') AS doc_count
                    FROM knowledge_bases kb
                    WHERE organization_id = $1 {approval_clause}
                    ORDER BY is_active DESC, created_at DESC
                    """,
                    organization_id, *extra_params,
                )
            else:
                rows = await conn.fetch(
                    f"""
                    SELECT id, name, description, organization_id, is_active,
                           age_group, created_by_keycloak_id, approval_status,
                           (SELECT COUNT(*) FROM documents d
                            WHERE d.knowledge_base_id = kb.id AND d.status = 'active') AS doc_count
                    FROM knowledge_bases kb
                    WHERE organization_id = $1 AND is_active = true {approval_clause}
                    ORDER BY created_at DESC
                    """,
                    organization_id, *extra_params,
                )
        return [
            KnowledgeBase(
                id=str(r["id"]),
                name=r["name"],
                description=r["description"] or "",
                organization_id=r["organization_id"],
                is_active=r["is_active"],
                age_group=r.get("age_group"),
                created_by_keycloak_id=r.get("created_by_keycloak_id"),
                approval_status=str(r.get("approval_status", "approved")),
                doc_count=int(r.get("doc_count", 0)),
            )
            for r in rows
        ]

    async def update_kb(
        self, kb_id: str, name: str | None = None, description: str | None = None,
        age_group: str | None = None,
    ) -> KnowledgeBase | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE knowledge_bases
                SET name        = COALESCE($2, name),
                    description = COALESCE($3, description),
                    age_group   = COALESCE($4, age_group)
                WHERE id = $1
                RETURNING id, name, description, organization_id, is_active,
                          age_group, created_by_keycloak_id
                """,
                kb_id, name, description, age_group,
            )
        if not row:
            return None
        return KnowledgeBase(
            id=str(row["id"]), name=row["name"],
            description=row["description"] or "",
            organization_id=row["organization_id"], is_active=row["is_active"],
            age_group=row.get("age_group"),
            created_by_keycloak_id=row.get("created_by_keycloak_id"),
        )

    async def archive_kb(self, kb_id: str) -> KnowledgeBase | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE knowledge_bases SET is_active = false
                WHERE id = $1
                RETURNING id, name, description, organization_id, is_active
                """,
                kb_id,
            )
        if not row:
            return None
        return KnowledgeBase(
            id=str(row["id"]), name=row["name"],
            description=row["description"] or "",
            organization_id=row["organization_id"], is_active=row["is_active"],
        )

    async def unarchive_kb(self, kb_id: str) -> KnowledgeBase | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE knowledge_bases SET is_active = true
                WHERE id = $1
                RETURNING id, name, description, organization_id, is_active
                """,
                kb_id,
            )
        if not row:
            return None
        return KnowledgeBase(
            id=str(row["id"]), name=row["name"],
            description=row["description"] or "",
            organization_id=row["organization_id"], is_active=row["is_active"],
        )

    # ── Documents ─────────────────────────────────────────────────────────────

    async def create_document(
        self,
        kb_id: str,
        title: str,
        content_type: str = "text",
    ) -> Document:
        doc_id = str(uuid.uuid4())
        # Normalise content_type to a valid enum value
        valid_types = {"pdf", "docx", "mp4", "mp3", "wav", "url", "text"}
        ct = content_type if content_type in valid_types else "text"
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO documents (id, knowledge_base_id, title, content_type, status)
                VALUES ($1, $2, $3, $4::content_type_enum, 'active'::document_status_enum)
                ON CONFLICT (id) DO NOTHING
                """,
                doc_id, kb_id, title, ct,
            )
        return Document(id=doc_id, knowledge_base_id=kb_id, title=title, content_type=ct)

    async def list_documents(self, kb_id: str) -> list[Document]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, knowledge_base_id, title, content_type, chunk_count,
                       is_active, retired_at, status
                FROM documents
                WHERE knowledge_base_id = $1 AND status != 'retired'::document_status_enum
                ORDER BY created_at DESC
                """,
                kb_id,
            )
        return [
            Document(
                id=str(r["id"]),
                knowledge_base_id=str(r["knowledge_base_id"]),
                title=r["title"],
                content_type=str(r["content_type"]),
                chunk_count=r["chunk_count"] or 0,
                is_active=r["is_active"],
                retired_at=r["retired_at"],
                metadata={"status": str(r["status"])},
            )
            for r in rows
        ]

    async def hard_delete_kb(self, kb_id: str) -> bool:
        """
        Permanently remove a knowledge base and all its content.

        Deletion order follows FK constraints (NO ACTION = must delete child
        before parent; CASCADE = handled automatically):

          1. assessment_results   → child of assessments (NO ACTION)
          2. assessments          → FK to knowledge_bases (NO ACTION)
          3. learner_topic_progress → FK to knowledge_bases (NO ACTION)
          4. chat_sessions        → FK to knowledge_bases (NO ACTION);
                                    chat_messages CASCADE from chat_sessions
          5. local_assessment_results → child of local_assessments
          6. local_assessments    → local dev table
          7. local_topic_progress → local dev table
          8. local_lesson_progress → local dev table
          9. knowledge_bases      → documents + document_chunks CASCADE

        Returns True if a row was deleted, False if the KB didn't exist.
        """
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                # Step 1-2: production assessment tables
                await conn.execute(
                    """
                    DELETE FROM assessment_results
                    WHERE assessment_id IN (
                        SELECT id FROM assessments WHERE knowledge_base_id = $1
                    )
                    """,
                    kb_id,
                )
                await conn.execute(
                    "DELETE FROM assessments WHERE knowledge_base_id = $1", kb_id
                )
                # Step 3: learner progress (production table, NO ACTION FK)
                await conn.execute(
                    "DELETE FROM learner_topic_progress WHERE knowledge_base_id = $1", kb_id
                )
                # Step 4: chat sessions (chat_messages CASCADE from session)
                await conn.execute(
                    "DELETE FROM chat_sessions WHERE knowledge_base_id = $1", kb_id
                )
                # Steps 5-8: local dev tables
                await conn.execute(
                    """
                    DELETE FROM local_assessment_results
                    WHERE assessment_id IN (
                        SELECT id FROM local_assessments WHERE knowledge_base_id = $1
                    )
                    """,
                    kb_id,
                )
                await conn.execute(
                    "DELETE FROM local_assessments WHERE knowledge_base_id = $1", kb_id
                )
                await conn.execute(
                    "DELETE FROM local_topic_progress WHERE knowledge_base_id = $1", kb_id
                )
                await conn.execute(
                    "DELETE FROM local_lesson_progress WHERE kb_id = $1", kb_id
                )
                # Step 9: delete the KB — documents + document_chunks CASCADE
                result = await conn.execute(
                    "DELETE FROM knowledge_bases WHERE id = $1", kb_id
                )
        return result == "DELETE 1"

    async def retire_document(self, doc_id: str) -> Document | None:
        now = datetime.now(timezone.utc)
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE documents
                SET is_active = false, retired_at = $2, status = 'retired'::document_status_enum
                WHERE id = $1
                RETURNING id, knowledge_base_id, title, content_type, chunk_count, is_active, retired_at
                """,
                doc_id, now,
            )
        if not row:
            return None
        return Document(
            id=str(row["id"]),
            knowledge_base_id=str(row["knowledge_base_id"]),
            title=row["title"],
            content_type=str(row["content_type"]),
            chunk_count=row["chunk_count"] or 0,
            is_active=row["is_active"],
            retired_at=row["retired_at"],
        )


    async def list_by_approval_status(
        self,
        status: str,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        """Return knowledge bases filtered by approval_status with total count."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, name, description, organization_id,
                       approval_status, ai_overview, created_at
                FROM knowledge_bases
                WHERE approval_status = $1
                  AND is_active = true
                ORDER BY created_at ASC
                LIMIT $2 OFFSET $3
                """,
                status, limit, offset,
            )
            total = await conn.fetchval(
                "SELECT COUNT(*) FROM knowledge_bases "
                "WHERE approval_status = $1 AND is_active = true",
                status,
            )
        return (
            [
                {
                    "id": str(r["id"]),
                    "name": r["name"],
                    "description": r["description"] or "",
                    "organization_id": r["organization_id"],
                    "approval_status": str(r["approval_status"]),
                    "ai_overview": r["ai_overview"],
                    "created_at": r["created_at"].isoformat(),
                }
                for r in rows
            ],
            int(total or 0),
        )

    async def update_kb_field(self, kb_id: str, field: str, value: str) -> None:
        """Generic single-field updater for approval workflow fields."""
        allowed = {"approval_status", "ai_overview", "rejection_reason", "clarification_message"}
        if field not in allowed:
            raise ValueError(f"Field {field!r} not allowed for update")
        # Use a safe lookup instead of direct string interpolation
        field_sql = {
            "approval_status":        "approval_status = $2",
            "ai_overview":            "ai_overview = $2",
            "rejection_reason":       "rejection_reason = $2",
            "clarification_message":  "clarification_message = $2",
        }[field]
        async with self._pool.acquire() as conn:
            await conn.execute(
                f"UPDATE knowledge_bases SET {field_sql} WHERE id = $1",
                kb_id, value,
            )

    async def platform_stats(self) -> dict:
        """Return live counts for the home-page stats strip."""
        async with self._pool.acquire() as conn:
            kb_count = await conn.fetchval(
                "SELECT COUNT(*) FROM knowledge_bases WHERE is_active = TRUE"
            )
            doc_count = await conn.fetchval(
                "SELECT COUNT(*) FROM documents WHERE status = 'active'"
            )
            chunk_count = await conn.fetchval(
                "SELECT COALESCE(SUM(chunk_count), 0) FROM documents WHERE status = 'active'"
            )
        return {
            "knowledge_bases": int(kb_count or 0),
            "documents_indexed": int(doc_count or 0),
            "chunks_in_vector_db": int(chunk_count or 0),
        }


async def create_pool() -> asyncpg.Pool:
    return await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
