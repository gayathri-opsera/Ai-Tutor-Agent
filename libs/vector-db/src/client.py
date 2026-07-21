"""Provider-agnostic vector database client.

Supports Weaviate (default) with an in-memory mock for testing.
Wraps all operations with retry + exponential backoff and raises
VectorDBConnectionError on exhaustion.
"""
from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_BACKOFF_BASE = 0.5


class VectorDBConnectionError(Exception):
    """Raised after all retries are exhausted."""


@dataclass
class VectorRecord:
    id: str
    vector: list[float]
    metadata: dict[str, Any] = field(default_factory=dict)
    namespace: str = "default"


@dataclass
class QueryResult:
    id: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)


class VectorDBClient:
    """Async vector DB client with retry and namespace isolation.

    Parameters
    ----------
    _mock_store:
        Injectable in-memory store for unit tests (avoids real DB).
    """

    def __init__(self, _mock_store: dict | None = None) -> None:
        self._mock = _mock_store  # {namespace: {id: VectorRecord}}
        self._weaviate: Any = None

    async def connect(self, url: str = "http://localhost:8080") -> None:
        if self._mock is not None:
            return
        try:
            import weaviate  # type: ignore
            api_key = os.getenv("WEAVIATE_API_KEY", "")
            if api_key:
                auth = weaviate.AuthApiKey(api_key=api_key)
                self._weaviate = weaviate.Client(url, auth_client_secret=auth)
            else:
                self._weaviate = weaviate.Client(url)
            self._ensure_schema()
        except Exception as exc:
            logger.warning("Weaviate connect failed: %s — using in-memory fallback", exc)
            self._mock = {}

    def _ensure_schema(self) -> None:
        """Create the DocumentChunk class in Weaviate if it doesn't exist yet."""
        try:
            existing = {c["class"] for c in (self._weaviate.schema.get().get("classes") or [])}
            if "DocumentChunk" in existing:
                # Ensure any missing properties are added (safe no-op if already present)
                existing_props = {
                    p["name"]
                    for c in (self._weaviate.schema.get().get("classes") or [])
                    if c["class"] == "DocumentChunk"
                    for p in c.get("properties", [])
                }
                for prop_name in ("excerpt", "chunk_index", "document_id", "document_title", "text"):
                    if prop_name not in existing_props:
                        try:
                            self._weaviate.schema.property.create("DocumentChunk", {
                                "name": prop_name,
                                "dataType": ["int"] if prop_name == "chunk_index" else ["text"],
                            })
                            logger.info("Added missing Weaviate property: %s", prop_name)
                        except Exception:
                            pass
                return
            self._weaviate.schema.create_class({
                "class": "DocumentChunk",
                "vectorizer": "none",
                "properties": [
                    {"name": "knowledge_base_id", "dataType": ["text"]},
                    {"name": "document_id",        "dataType": ["text"]},
                    {"name": "document_title",     "dataType": ["text"]},
                    {"name": "text",               "dataType": ["text"]},
                    {"name": "excerpt",            "dataType": ["text"]},
                    {"name": "chunk_index",        "dataType": ["int"]},
                ],
            })
            logger.info("Created Weaviate DocumentChunk schema")
        except Exception as exc:
            logger.warning("Schema ensure failed: %s", exc)

    async def upsert_vectors(
        self,
        vectors: list[VectorRecord],
        namespace: str = "default",
    ) -> None:
        """Insert or update vectors. Idempotent on id collision."""
        await self._with_retry("upsert", self._upsert, vectors, namespace)

    async def query_vectors(
        self,
        query_vector: list[float],
        top_k: int = 5,
        filters: dict | None = None,
        namespace: str = "default",
    ) -> list[QueryResult]:
        return await self._with_retry("query", self._query, query_vector, top_k, filters, namespace)

    async def delete_vectors(self, ids: list[str], namespace: str = "default") -> None:
        await self._with_retry("delete", self._delete, ids, namespace)

    # ------------------------------------------------------------------
    # Internal implementation methods
    # ------------------------------------------------------------------

    async def _upsert(self, vectors: list[VectorRecord], namespace: str) -> None:
        if self._mock is not None:
            ns = self._mock.setdefault(namespace, {})
            for rec in vectors:
                ns[rec.id] = rec
            return
        # Real Weaviate upsert
        for rec in vectors:
            # Strip mock-only '_namespace' key — Weaviate rejects properties with leading '_'
            weaviate_obj = {k: v for k, v in rec.metadata.items() if not k.startswith("_")}
            try:
                # replace() is a true upsert: creates if absent, replaces if present
                self._weaviate.data_object.replace(
                    data_object=weaviate_obj,
                    class_name="DocumentChunk",
                    uuid=rec.id,
                    vector=rec.vector,
                )
            except Exception:
                # Fallback: create for objects that may not exist yet
                self._weaviate.data_object.create(
                    data_object=weaviate_obj,
                    class_name="DocumentChunk",
                    uuid=rec.id,
                    vector=rec.vector,
                )

    async def _query(
        self,
        query_vector: list[float],
        top_k: int,
        filters: dict | None,
        namespace: str,
    ) -> list[QueryResult]:
        if self._mock is not None:
            return self._mock_query(query_vector, top_k, filters, namespace)
        # Real Weaviate query
        where_filter = self._build_weaviate_filter(filters, namespace)
        # Always retrieve the core content properties; filter keys are used only for the where clause
        _CORE_PROPS = ["knowledge_base_id", "document_id", "document_title", "text", "excerpt", "chunk_index"]
        fetch_props = list({*_CORE_PROPS, *(filters.keys() if filters else [])})
        result = (
            self._weaviate.query.get("DocumentChunk", fetch_props)
            .with_near_vector({"vector": query_vector})
            .with_limit(top_k)
            .with_additional(["id", "distance"])
        )
        if where_filter:
            result = result.with_where(where_filter)
        data = result.do()
        chunks = (data.get("data", {}).get("Get", {}).get("DocumentChunk") or [])
        return [
            QueryResult(
                id=c["_additional"]["id"],
                score=1.0 - float(c["_additional"]["distance"]),
                metadata={k: v for k, v in c.items() if not k.startswith("_")},
            )
            for c in chunks
        ]

    async def _delete(self, ids: list[str], namespace: str) -> None:
        if self._mock is not None:
            ns = self._mock.get(namespace, {})
            for vid in ids:
                ns.pop(vid, None)
            return
        for vid in ids:
            self._weaviate.data_object.delete(vid, class_name="DocumentChunk")

    def _mock_query(
        self,
        query_vector: list[float],
        top_k: int,
        filters: dict | None,
        namespace: str,
    ) -> list[QueryResult]:
        """Cosine-similarity search over the in-memory store."""
        ns = self._mock.get(namespace, {})
        results = []
        for rec in ns.values():
            # Apply metadata filters
            if filters:
                if not all(rec.metadata.get(k) == v for k, v in filters.items()):
                    continue
            score = _cosine(query_vector, rec.vector)
            results.append(QueryResult(id=rec.id, score=score, metadata=rec.metadata))
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]

    def _build_weaviate_filter(self, filters: dict | None, namespace: str) -> dict | None:
        # NOTE: The _namespace concept only applies to the in-memory mock store.
        # In real Weaviate, isolation is achieved via the knowledge_base_id filter alone
        # (Weaviate rejects property names starting with '_').
        if not filters:
            return None
        operands = []
        for k, v in filters.items():
            operands.append({"path": [k], "operator": "Equal", "valueString": str(v)})
        if len(operands) == 1:
            return operands[0]
        return {"operator": "And", "operands": operands}

    # ------------------------------------------------------------------
    # Retry wrapper
    # ------------------------------------------------------------------

    async def _with_retry(self, op_name: str, fn, *args):
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                return await fn(*args)
            except Exception as exc:
                last_exc = exc
                wait = _BACKOFF_BASE * (2 ** attempt)
                logger.warning(
                    "VectorDB %s attempt %d/%d failed: %s — retrying in %.1fs",
                    op_name, attempt + 1, _MAX_RETRIES, exc, wait,
                )
                await asyncio.sleep(wait)
        raise VectorDBConnectionError(
            f"VectorDB {op_name} failed after {_MAX_RETRIES} attempts: {last_exc}"
        ) from last_exc


def _cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = sum(x * x for x in a) ** 0.5
    mag_b = sum(x * x for x in b) ** 0.5
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)
