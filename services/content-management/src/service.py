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
    "postgresql://ai_tutor:ai_tutor_local_password@postgres:5432/ai_tutor",
)


@dataclass
class KnowledgeBase:
    id: str
    name: str
    organization_id: str
    description: str = ""
    is_active: bool = True


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
        self, name: str, organization_id: str, description: str = ""
    ) -> KnowledgeBase:
        kb_id = str(uuid.uuid4())
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO knowledge_bases (id, name, description, organization_id)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (id) DO NOTHING
                """,
                kb_id, name, description, organization_id,
            )
        return KnowledgeBase(id=kb_id, name=name, organization_id=organization_id, description=description)

    async def get_kb(self, kb_id: str) -> KnowledgeBase | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, name, description, organization_id, is_active FROM knowledge_bases WHERE id = $1",
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
        )

    async def list_kbs(self, organization_id: str) -> list[KnowledgeBase]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, name, description, organization_id, is_active
                FROM knowledge_bases
                WHERE organization_id = $1 AND is_active = true
                ORDER BY created_at DESC
                """,
                organization_id,
            )
        return [
            KnowledgeBase(
                id=str(r["id"]),
                name=r["name"],
                description=r["description"] or "",
                organization_id=r["organization_id"],
                is_active=r["is_active"],
            )
            for r in rows
        ]

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
                SELECT id, knowledge_base_id, title, content_type, chunk_count, is_active, retired_at
                FROM documents
                WHERE knowledge_base_id = $1 AND is_active = true
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
            )
            for r in rows
        ]

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


async def create_pool() -> asyncpg.Pool:
    return await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
