"""Unit tests for libs/contracts/src/rag.py — RAG pipeline shared contract models."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.rag import (
    ChunkResult,
    IngestChunk,
    IngestRequest,
    RetrieveRequest,
    RetrieveResponse,
)

FIXTURES = Path(__file__).parent / "fixtures"


# ── RetrieveRequest ──────────────────────────────────────────────────────────

class TestRetrieveRequest:
    def test_instantiation_defaults(self):
        req = RetrieveRequest(query="What is backpropagation?", knowledge_base_id="kb-123")
        assert req.query == "What is backpropagation?"
        assert req.knowledge_base_id == "kb-123"
        assert req.top_k == 5
        assert req.filters is None
        assert req.use_hybrid is True

    def test_custom_top_k(self):
        req = RetrieveRequest(query="q", knowledge_base_id="kb", top_k=10)
        assert req.top_k == 10

    def test_top_k_lower_bound(self):
        with pytest.raises(ValidationError):
            RetrieveRequest(query="q", knowledge_base_id="kb", top_k=0)

    def test_top_k_upper_bound(self):
        with pytest.raises(ValidationError):
            RetrieveRequest(query="q", knowledge_base_id="kb", top_k=51)

    def test_filters_accepted(self):
        req = RetrieveRequest(
            query="q", knowledge_base_id="kb", filters={"topic": "math"}
        )
        assert req.filters == {"topic": "math"}

    def test_serialization_to_dict(self):
        req = RetrieveRequest(query="test", knowledge_base_id="kb-abc", top_k=3)
        d = req.model_dump()
        assert d["query"] == "test"
        assert d["top_k"] == 3
        assert d["filters"] is None

    def test_deserialization_from_json_fixture(self):
        fixture = json.loads((FIXTURES / "retrieve_request.json").read_text())
        req = RetrieveRequest(**fixture)
        assert req.query == fixture["query"]
        assert req.knowledge_base_id == fixture["knowledge_base_id"]

    def test_missing_required_field(self):
        with pytest.raises(ValidationError):
            RetrieveRequest(knowledge_base_id="kb")  # query missing

    def test_missing_kb_id_field(self):
        with pytest.raises(ValidationError):
            RetrieveRequest(query="q")  # knowledge_base_id missing


# ── ChunkResult ──────────────────────────────────────────────────────────────

class TestChunkResult:
    def test_instantiation(self):
        chunk = ChunkResult(
            chunk_id="c-1",
            text="Neural networks are...",
            document_id="doc-1",
            document_title="ML Basics",
            score=0.92,
        )
        assert chunk.chunk_id == "c-1"
        assert chunk.score == 0.92
        assert chunk.metadata == {}

    def test_metadata_populated(self):
        chunk = ChunkResult(
            chunk_id="c-2",
            text="t",
            document_id="d",
            document_title="D",
            score=0.5,
            metadata={"page": 3},
        )
        assert chunk.metadata["page"] == 3

    def test_serialization(self):
        chunk = ChunkResult(
            chunk_id="c-3", text="t", document_id="d",
            document_title="D", score=0.8
        )
        d = chunk.model_dump()
        assert d["chunk_id"] == "c-3"
        assert "metadata" in d


# ── RetrieveResponse ─────────────────────────────────────────────────────────

class TestRetrieveResponse:
    def test_instantiation(self):
        chunk = ChunkResult(
            chunk_id="c-1", text="t", document_id="d",
            document_title="D", score=0.9
        )
        resp = RetrieveResponse(chunks=[chunk], query_embedding=[0.1, 0.2, 0.3])
        assert len(resp.chunks) == 1
        assert len(resp.query_embedding) == 3

    def test_empty_chunks(self):
        resp = RetrieveResponse(chunks=[], query_embedding=[])
        assert resp.chunks == []

    def test_deserialization_from_json_fixture(self):
        fixture = json.loads((FIXTURES / "retrieve_response.json").read_text())
        resp = RetrieveResponse(**fixture)
        assert len(resp.chunks) > 0
        assert isinstance(resp.chunks[0], ChunkResult)

    def test_serialization(self):
        resp = RetrieveResponse(chunks=[], query_embedding=[0.1])
        d = resp.model_dump()
        assert "chunks" in d
        assert "query_embedding" in d


# ── IngestChunk ──────────────────────────────────────────────────────────────

class TestIngestChunk:
    def test_defaults(self):
        c = IngestChunk(text="Hello world")
        assert c.chunk_index == 0
        assert c.metadata == {}

    def test_with_metadata(self):
        c = IngestChunk(text="t", chunk_index=2, metadata={"src": "pdf"})
        assert c.chunk_index == 2
        assert c.metadata["src"] == "pdf"

    def test_missing_text(self):
        with pytest.raises(ValidationError):
            IngestChunk()

    def test_serialization(self):
        c = IngestChunk(text="chunk text", chunk_index=1)
        d = c.model_dump()
        assert d["text"] == "chunk text"
        assert d["chunk_index"] == 1


# ── IngestRequest ─────────────────────────────────────────────────────────────

class TestIngestRequest:
    def test_instantiation(self):
        req = IngestRequest(
            document_id="doc-1",
            knowledge_base_id="kb-1",
            document_title="Chapter 1",
            chunks=[IngestChunk(text="Intro paragraph")],
        )
        assert req.document_id == "doc-1"
        assert len(req.chunks) == 1

    def test_empty_chunks_allowed(self):
        req = IngestRequest(
            document_id="d", knowledge_base_id="kb",
            document_title="T", chunks=[]
        )
        assert req.chunks == []

    def test_serialization(self):
        req = IngestRequest(
            document_id="d", knowledge_base_id="kb",
            document_title="T",
            chunks=[IngestChunk(text="c")]
        )
        d = req.model_dump()
        assert d["document_id"] == "d"
        assert len(d["chunks"]) == 1


# ── __init__ re-exports ───────────────────────────────────────────────────────

def test_init_reexports_all_models():
    """Verify libs/contracts/src/__init__.py re-exports every public model."""
    from src import (
        ChunkResult,
        IngestChunk,
        IngestRequest,
        RetrieveRequest,
        RetrieveResponse,
    )
    assert RetrieveRequest is not None
    assert ChunkResult is not None
    assert RetrieveResponse is not None
    assert IngestChunk is not None
    assert IngestRequest is not None
