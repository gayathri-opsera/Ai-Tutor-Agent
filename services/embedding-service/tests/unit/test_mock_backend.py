"""Unit tests for MockEmbeddingBackend — determinism, dimensionality, edge cases."""
import json
from pathlib import Path

import pytest

from src.backends.mock import MockEmbeddingBackend

FIXTURES = Path(__file__).parent.parent / "fixtures"


class TestMockBackend:
    @pytest.mark.asyncio
    async def test_returns_one_vector_per_text(self):
        backend = MockEmbeddingBackend()
        texts = ["hello", "world", "foo"]
        result = await backend.embed(texts)
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_default_dimensions_1536(self):
        backend = MockEmbeddingBackend()
        result = await backend.embed(["test"])
        assert len(result[0]) == 1536

    @pytest.mark.asyncio
    async def test_custom_dimensions(self):
        backend = MockEmbeddingBackend(dimensions=384)
        result = await backend.embed(["test"])
        assert len(result[0]) == 384

    @pytest.mark.asyncio
    async def test_same_text_same_vector(self):
        backend = MockEmbeddingBackend()
        r1 = await backend.embed(["deterministic text"])
        r2 = await backend.embed(["deterministic text"])
        assert r1 == r2

    @pytest.mark.asyncio
    async def test_different_texts_different_vectors(self):
        backend = MockEmbeddingBackend()
        r = await backend.embed(["text A", "text B"])
        assert r[0] != r[1]

    @pytest.mark.asyncio
    async def test_batch_from_fixture(self):
        texts = json.loads((FIXTURES / "sample_chunks.json").read_text())
        backend = MockEmbeddingBackend()
        result = await backend.embed(texts)
        assert len(result) == len(texts)
        assert all(len(v) == 1536 for v in result)

    def test_default_model_name(self):
        backend = MockEmbeddingBackend()
        assert backend.default_model() == "mock-embedding-v1"

    def test_dimensions_for_returns_configured_dim(self):
        backend = MockEmbeddingBackend(dimensions=512)
        assert backend.dimensions_for("any-model") == 512

    @pytest.mark.asyncio
    async def test_single_character_text(self):
        backend = MockEmbeddingBackend()
        result = await backend.embed(["a"])
        assert len(result) == 1
        assert len(result[0]) == 1536

    @pytest.mark.asyncio
    async def test_special_characters(self):
        backend = MockEmbeddingBackend()
        result = await backend.embed(["!@#$%^&*()_+ 你好 🎉"])
        assert len(result[0]) == 1536
