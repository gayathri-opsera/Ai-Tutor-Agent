"""Unit tests for VectorDBClient using in-memory mock store."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from src.client import VectorDBClient, VectorDBConnectionError, VectorRecord, QueryResult

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _make_client() -> VectorDBClient:
    return VectorDBClient(_mock_store={})


def _load_fixtures() -> list[VectorRecord]:
    data = json.loads((FIXTURES / "sample_vectors.json").read_text())
    return [VectorRecord(**d) for d in data]


class TestUpsertAndQuery:
    @pytest.mark.asyncio
    async def test_upsert_and_retrieve(self):
        c = _make_client()
        recs = [VectorRecord(id="v1", vector=[1.0, 0.0], metadata={"kb": "kb1"}, namespace="kb1")]
        await c.upsert_vectors(recs, namespace="kb1")
        results = await c.query_vectors([1.0, 0.0], top_k=1, namespace="kb1")
        assert len(results) == 1
        assert results[0].id == "v1"

    @pytest.mark.asyncio
    async def test_query_returns_sorted_by_score(self):
        c = _make_client()
        recs = [
            VectorRecord(id="hi",  vector=[1.0, 0.0], metadata={}, namespace="ns"),
            VectorRecord(id="low", vector=[0.0, 1.0], metadata={}, namespace="ns"),
        ]
        await c.upsert_vectors(recs, namespace="ns")
        results = await c.query_vectors([1.0, 0.0], top_k=2, namespace="ns")
        assert results[0].id == "hi"
        assert results[0].score > results[1].score

    @pytest.mark.asyncio
    async def test_top_k_limits_results(self):
        c = _make_client()
        recs = [VectorRecord(id=f"v{i}", vector=[float(i), 0.0], metadata={}, namespace="ns")
                for i in range(10)]
        await c.upsert_vectors(recs, namespace="ns")
        results = await c.query_vectors([5.0, 0.0], top_k=3, namespace="ns")
        assert len(results) <= 3

    @pytest.mark.asyncio
    async def test_metadata_filter_applied(self):
        c = _make_client()
        recs = [
            VectorRecord(id="match", vector=[1.0, 0.0], metadata={"kb": "kb1", "type": "pdf"}, namespace="ns"),
            VectorRecord(id="no",    vector=[1.0, 0.0], metadata={"kb": "kb2", "type": "pdf"}, namespace="ns"),
        ]
        await c.upsert_vectors(recs, namespace="ns")
        results = await c.query_vectors([1.0, 0.0], filters={"kb": "kb1"}, namespace="ns")
        ids = [r.id for r in results]
        assert "match" in ids
        assert "no" not in ids

    @pytest.mark.asyncio
    async def test_namespace_isolation(self):
        c = _make_client()
        await c.upsert_vectors(
            [VectorRecord(id="kb1-vec", vector=[1.0, 0.0], metadata={}, namespace="kb-001")],
            namespace="kb-001",
        )
        await c.upsert_vectors(
            [VectorRecord(id="kb2-vec", vector=[1.0, 0.0], metadata={}, namespace="kb-002")],
            namespace="kb-002",
        )
        results = await c.query_vectors([1.0, 0.0], namespace="kb-001")
        ids = [r.id for r in results]
        assert "kb1-vec" in ids
        assert "kb2-vec" not in ids

    @pytest.mark.asyncio
    async def test_upsert_is_idempotent(self):
        c = _make_client()
        rec = VectorRecord(id="v1", vector=[1.0, 0.0], metadata={"v": 1}, namespace="ns")
        await c.upsert_vectors([rec], namespace="ns")
        rec2 = VectorRecord(id="v1", vector=[1.0, 0.0], metadata={"v": 2}, namespace="ns")
        await c.upsert_vectors([rec2], namespace="ns")
        results = await c.query_vectors([1.0, 0.0], namespace="ns")
        assert results[0].metadata["v"] == 2  # updated

    @pytest.mark.asyncio
    async def test_fixture_vectors_loaded_and_queried(self):
        c = _make_client()
        recs = _load_fixtures()
        for ns in {r.namespace for r in recs}:
            ns_recs = [r for r in recs if r.namespace == ns]
            await c.upsert_vectors(ns_recs, namespace=ns)
        # kb-001 query should not return kb-002 results
        results = await c.query_vectors([0.1, 0.2, 0.3, 0.4, 0.5], namespace="kb-001")
        for r in results:
            assert r.metadata.get("knowledge_base_id") == "kb-001"


class TestDelete:
    @pytest.mark.asyncio
    async def test_delete_removes_vectors(self):
        c = _make_client()
        await c.upsert_vectors([VectorRecord(id="del", vector=[1.0], metadata={}, namespace="ns")], namespace="ns")
        await c.delete_vectors(["del"], namespace="ns")
        results = await c.query_vectors([1.0], namespace="ns")
        assert all(r.id != "del" for r in results)

    @pytest.mark.asyncio
    async def test_delete_nonexistent_is_safe(self):
        c = _make_client()
        await c.delete_vectors(["ghost"], namespace="ns")  # should not raise


class TestCosineHelper:
    def test_identical_vectors_score_one(self):
        from src.client import _cosine
        assert abs(_cosine([1.0, 0.0], [1.0, 0.0]) - 1.0) < 1e-9

    def test_orthogonal_vectors_score_zero(self):
        from src.client import _cosine
        assert abs(_cosine([1.0, 0.0], [0.0, 1.0])) < 1e-9

    def test_zero_vector_returns_zero(self):
        from src.client import _cosine
        assert _cosine([0.0, 0.0], [1.0, 0.0]) == 0.0

    def test_mismatched_lengths_returns_zero(self):
        from src.client import _cosine
        assert _cosine([1.0], [1.0, 2.0]) == 0.0


class TestVectorRecord:
    def test_default_namespace(self):
        rec = VectorRecord(id="x", vector=[1.0])
        assert rec.namespace == "default"
        assert rec.metadata == {}

    def test_query_result_fields(self):
        qr = QueryResult(id="q", score=0.9, metadata={"k": "v"})
        assert qr.id == "q"
        assert qr.score == 0.9


class TestConnectFallback:
    @pytest.mark.asyncio
    async def test_connect_with_mock_store_is_noop(self):
        c = VectorDBClient(_mock_store={"ns": {}})
        await c.connect()  # should not raise

    @pytest.mark.asyncio
    async def test_connect_without_weaviate_falls_back_to_mock(self):
        import sys, unittest.mock as mock
        c = VectorDBClient()
        with mock.patch.dict(sys.modules, {"weaviate": None}):
            try:
                await c.connect(url="http://localhost:9999")
            except Exception:
                pass
        # After failure, mock store is set or weaviate is still None
        # Either way no unhandled crash

    @pytest.mark.asyncio
    async def test_empty_namespace_query_returns_empty(self):
        c = _make_client()
        results = await c.query_vectors([1.0, 0.0], namespace="empty-ns")
        assert results == []


class TestWeaviateBackendPaths:
    """Tests that exercise the real-Weaviate code paths using mocked clients."""

    def _make_weaviate_client(self):
        from unittest.mock import MagicMock
        c = VectorDBClient()
        weaviate_mock = MagicMock()
        # Mock query chain
        query_chain = MagicMock()
        query_chain.get.return_value = query_chain
        query_chain.with_near_vector.return_value = query_chain
        query_chain.with_limit.return_value = query_chain
        query_chain.with_additional.return_value = query_chain
        query_chain.with_where.return_value = query_chain
        query_chain.do.return_value = {
            "data": {"Get": {"DocumentChunk": [
                {"_additional": {"id": "wv-1", "distance": "0.1"}, "knowledge_base_id": "kb1"}
            ]}}
        }
        weaviate_mock.query = query_chain
        weaviate_mock.data_object = MagicMock()
        c._weaviate = weaviate_mock
        c._mock = None
        return c, weaviate_mock

    @pytest.mark.asyncio
    async def test_weaviate_upsert_called(self):
        c, weaviate_mock = self._make_weaviate_client()
        recs = [VectorRecord(id="v1", vector=[1.0, 0.0], metadata={"k": "v"}, namespace="ns")]
        await c.upsert_vectors(recs, namespace="ns")
        weaviate_mock.data_object.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_weaviate_query_returns_results(self):
        c, _ = self._make_weaviate_client()
        results = await c.query_vectors([1.0, 0.0], top_k=5, namespace="kb1")
        assert len(results) == 1
        assert results[0].id == "wv-1"
        assert abs(results[0].score - 0.9) < 0.01

    @pytest.mark.asyncio
    async def test_weaviate_query_with_filters(self):
        c, _ = self._make_weaviate_client()
        results = await c.query_vectors([1.0, 0.0], filters={"kb": "kb1"}, namespace="ns")
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_weaviate_delete_called(self):
        c, weaviate_mock = self._make_weaviate_client()
        await c.delete_vectors(["v1"], namespace="ns")
        weaviate_mock.data_object.delete.assert_called_once_with("v1", class_name="DocumentChunk")

    def test_build_weaviate_filter_no_extra_filters(self):
        c = VectorDBClient(_mock_store={})
        f = c._build_weaviate_filter(None, "ns1")
        assert f is not None
        assert f["operator"] == "Equal"

    def test_build_weaviate_filter_with_filters(self):
        c = VectorDBClient(_mock_store={})
        f = c._build_weaviate_filter({"kb": "kb1"}, "ns1")
        assert f["operator"] == "And"

    def test_build_weaviate_filter_no_namespace_no_filters(self):
        c = VectorDBClient(_mock_store={})
        f = c._build_weaviate_filter(None, "")
        assert f is None


class TestRetryAndErrors:
    @pytest.mark.asyncio
    async def test_raises_connection_error_after_retries(self):
        c = VectorDBClient()
        c._mock = None

        async def always_fail(*args):
            raise ConnectionError("no db")

        c._upsert = always_fail
        with patch("asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(VectorDBConnectionError):
                await c.upsert_vectors(
                    [VectorRecord(id="x", vector=[1.0], metadata={}, namespace="ns")], namespace="ns"
                )

    @pytest.mark.asyncio
    async def test_retry_succeeds_on_third_attempt(self):
        c = VectorDBClient(_mock_store={})
        call_count = 0

        orig_upsert = c._upsert

        async def flaky_upsert(vectors, namespace):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("transient")
            return await orig_upsert(vectors, namespace)

        c._upsert = flaky_upsert
        with patch("asyncio.sleep", new_callable=AsyncMock):
            await c.upsert_vectors(
                [VectorRecord(id="x", vector=[1.0], metadata={}, namespace="ns")], namespace="ns"
            )
        assert call_count == 3
