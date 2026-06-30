"""Integration tests for the Embedding Service FastAPI endpoints."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from src.backends.mock import MockEmbeddingBackend
from src.main import create_app
from src.service import EmbeddingService

FIXTURES = Path(__file__).parent.parent / "fixtures"

EMBED_PAYLOAD = {
    "texts": ["The quick brown fox jumps over the lazy dog."],
}


@pytest.fixture
def client():
    app = create_app()
    backend = MockEmbeddingBackend()
    app.state.embedding_service = EmbeddingService(backend)
    with TestClient(app) as c:
        yield c


class TestGenerateEndpoint:
    def test_successful_embed(self, client):
        resp = client.post("/api/internal/embeddings/generate", json=EMBED_PAYLOAD)
        assert resp.status_code == 200
        data = resp.json()
        assert "embeddings" in data
        assert len(data["embeddings"]) == 1
        assert data["dimensions"] == 1536
        assert data["backend"] == "mock"

    def test_batch_embed(self, client):
        texts = json.loads((FIXTURES / "sample_chunks.json").read_text())
        resp = client.post("/api/internal/embeddings/generate", json={"texts": texts})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["embeddings"]) == len(texts)

    def test_empty_texts_returns_422(self, client):
        resp = client.post("/api/internal/embeddings/generate", json={"texts": []})
        assert resp.status_code == 422

    def test_whitespace_only_text_returns_422(self, client):
        resp = client.post("/api/internal/embeddings/generate", json={"texts": ["   "]})
        assert resp.status_code == 422

    def test_oversized_batch_returns_422(self, client):
        texts = ["text"] * 101
        resp = client.post("/api/internal/embeddings/generate", json={"texts": texts})
        assert resp.status_code == 422

    def test_model_override_in_response(self, client):
        resp = client.post(
            "/api/internal/embeddings/generate",
            json={"texts": ["hello"], "model": "custom-model"},
        )
        assert resp.status_code == 200
        assert resp.json()["model"] == "custom-model"

    def test_dimensional_consistency(self, client):
        texts = ["alpha", "beta", "gamma"]
        resp = client.post("/api/internal/embeddings/generate", json={"texts": texts})
        assert resp.status_code == 200
        dims = [len(v) for v in resp.json()["embeddings"]]
        assert len(set(dims)) == 1

    def test_same_text_same_vector_across_requests(self, client):
        payload = {"texts": ["identical text"]}
        r1 = client.post("/api/internal/embeddings/generate", json=payload).json()
        r2 = client.post("/api/internal/embeddings/generate", json=payload).json()
        assert r1["embeddings"] == r2["embeddings"]

    def test_backend_error_returns_502(self, client):
        broken_backend = MagicMock()
        broken_backend.name = "broken"
        broken_backend.default_model = MagicMock(return_value="x")
        broken_backend.embed = AsyncMock(side_effect=RuntimeError("backend down"))
        broken_backend.dimensions_for = MagicMock(return_value=1536)
        client.app.state.embedding_service = EmbeddingService(broken_backend)
        resp = client.post("/api/internal/embeddings/generate", json=EMBED_PAYLOAD)
        assert resp.status_code == 502

    def test_missing_texts_field_returns_422(self, client):
        resp = client.post("/api/internal/embeddings/generate", json={})
        assert resp.status_code == 422


class TestHealthEndpoint:
    def test_health_ok(self, client):
        resp = client.get("/api/internal/embeddings/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["backend"] == "mock"
