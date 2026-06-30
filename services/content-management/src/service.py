"""Content management CRUD."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class KnowledgeBase:
    id: str
    name: str
    organization_id: str
    is_active: bool = True


@dataclass
class Document:
    id: str
    knowledge_base_id: str
    title: str
    is_active: bool = True
    retired_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class ContentManagementService:
    def __init__(self) -> None:
        self.knowledge_bases: dict[str, KnowledgeBase] = {}
        self.documents: dict[str, Document] = {}

    def create_kb(self, name: str, organization_id: str) -> KnowledgeBase:
        kb = KnowledgeBase(id=str(uuid.uuid4()), name=name, organization_id=organization_id)
        self.knowledge_bases[kb.id] = kb
        return kb

    def get_kb(self, kb_id: str) -> KnowledgeBase | None:
        return self.knowledge_bases.get(kb_id)

    def list_kbs(self, organization_id: str) -> list[KnowledgeBase]:
        return [kb for kb in self.knowledge_bases.values() if kb.organization_id == organization_id and kb.is_active]

    def create_document(self, kb_id: str, title: str) -> Document:
        doc = Document(id=str(uuid.uuid4()), knowledge_base_id=kb_id, title=title)
        self.documents[doc.id] = doc
        return doc

    def retire_document(self, doc_id: str) -> Document | None:
        doc = self.documents.get(doc_id)
        if doc:
            doc.is_active = False
            doc.retired_at = datetime.now(timezone.utc)
        return doc
