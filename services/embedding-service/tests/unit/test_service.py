"""Unit tests for EmbeddingService — validation, backend selection, response assembly."""
import pytest

from src.backends.mock import MockEmbeddingBackend
from src.schemas import EmbedRequest
from src.service import EmbeddingService, make_backend


def make_svc(dims: int = 1536) -> EmbeddingService:
    return EmbeddingService(MockEmbeddingBackend(dimensions=dims))


class TestInputValidation:
    @pytest.mark.asyncio
    async def test_empty_texts_raises(self):
        svc = make_svc()
        # Pydantic enforces min_length=1 on the texts field at schema level
        from pydantic import ValidationError
        with pytest.raises((ValueError, ValidationError)):
            await svc.generate(EmbedRequest(texts=[]))

    @pytest.mark.asyncio
    async def test_whitespace_only_text_raises(self):
        svc = make_svc()
        with pytest.raises(ValueError, match="whitespace"):
            await svc.generate(EmbedRequest(texts=["   "]))

    @pytest.mark.asyncio
    async def test_oversized_text_raises(self):
        svc = make_svc()
        big = "x" * 9000
        with pytest.raises(ValueError, match="exceeds limit"):
            await svc.generate(EmbedRequest(texts=[big]))

    @pytest.mark.asyncio
    async def test_batch_too_large_raises(self):
        svc = make_svc()
        texts = ["text"] * 101
        with pytest.raises(ValueError, match="Batch size"):
            await svc.generate(EmbedRequest(texts=texts))

    @pytest.mark.asyncio
    async def test_max_batch_size_passes(self):
        svc = make_svc()
        texts = ["text"] * 100
        result = await svc.generate(EmbedRequest(texts=texts))
        assert len(result.embeddings) == 100


class TestResponseAssembly:
    @pytest.mark.asyncio
    async def test_response_shape(self):
        svc = make_svc()
        result = await svc.generate(EmbedRequest(texts=["hello"]))
        assert result.dimensions == 1536
        assert result.backend == "mock"
        assert result.model == "mock-embedding-v1"
        assert len(result.embeddings) == 1
        assert len(result.embeddings[0]) == 1536

    @pytest.mark.asyncio
    async def test_model_override_passed_to_backend(self):
        backend = MockEmbeddingBackend()
        svc = EmbeddingService(backend)
        result = await svc.generate(EmbedRequest(texts=["hi"], model="custom-model"))
        assert result.model == "custom-model"

    @pytest.mark.asyncio
    async def test_default_model_used_when_none(self):
        svc = make_svc()
        result = await svc.generate(EmbedRequest(texts=["hi"]))
        assert result.model == "mock-embedding-v1"

    @pytest.mark.asyncio
    async def test_batch_response_count_matches_input(self):
        svc = make_svc()
        texts = ["a", "b", "c", "d", "e"]
        result = await svc.generate(EmbedRequest(texts=texts))
        assert len(result.embeddings) == 5


class TestDimensionalConsistency:
    @pytest.mark.asyncio
    async def test_same_text_same_vector_repeated_calls(self):
        svc = make_svc()
        req = EmbedRequest(texts=["consistent text"])
        r1 = await svc.generate(req)
        r2 = await svc.generate(req)
        assert r1.embeddings == r2.embeddings

    @pytest.mark.asyncio
    async def test_all_vectors_same_dimension(self):
        svc = make_svc()
        texts = ["alpha", "beta", "gamma", "delta"]
        result = await svc.generate(EmbedRequest(texts=texts))
        dims = [len(v) for v in result.embeddings]
        assert len(set(dims)) == 1   # all equal


class TestBackendFactory:
    def test_unknown_backend_raises(self):
        with pytest.raises(ValueError, match="Unknown embedding backend"):
            make_backend("nonexistent")

    def test_mock_backend_created(self):
        backend = make_backend("mock")
        assert backend.name == "mock"

    def test_openai_gateway_backend_created(self):
        from src.backends.openai_gateway import OpenAIGatewayBackend
        backend = make_backend("openai_gateway")
        assert isinstance(backend, OpenAIGatewayBackend)

    def test_sentence_transformers_raises_import_error_without_package(self):
        import unittest.mock as mock
        import sys
        with mock.patch.dict(sys.modules, {"sentence_transformers": None}):
            with pytest.raises((ImportError, TypeError)):
                make_backend("sentence_transformers")
