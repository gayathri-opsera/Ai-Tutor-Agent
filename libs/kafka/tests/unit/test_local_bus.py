"""Unit tests for LocalEventBus and KafkaProducer sync-mode routing."""
from __future__ import annotations

import os
from unittest.mock import AsyncMock, patch

import pytest

from src.local_bus import LocalEventBus, local_bus
from src.producer import KafkaProducer


# ---------------------------------------------------------------------------
# LocalEventBus tests
# ---------------------------------------------------------------------------

class TestLocalEventBus:
    def setup_method(self):
        self.bus = LocalEventBus()

    @pytest.mark.asyncio
    async def test_handler_called_on_publish(self):
        handler = AsyncMock()
        self.bus.subscribe("my-topic", handler)
        await self.bus.publish("my-topic", {"x": 1})
        handler.assert_called_once_with({"x": 1})

    @pytest.mark.asyncio
    async def test_multiple_handlers_all_called(self):
        h1, h2 = AsyncMock(), AsyncMock()
        self.bus.subscribe("my-topic", h1)
        self.bus.subscribe("my-topic", h2)
        await self.bus.publish("my-topic", {"n": 42})
        h1.assert_called_once()
        h2.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_handler_logs_drop(self, caplog):
        import logging
        with caplog.at_level(logging.INFO, logger="src.local_bus"):
            await self.bus.publish("orphan-topic", {"data": "lost"})
        assert "no handler" in caplog.text.lower() or "orphan-topic" in caplog.text

    @pytest.mark.asyncio
    async def test_handler_error_does_not_block_other_handlers(self):
        broken = AsyncMock(side_effect=RuntimeError("boom"))
        good = AsyncMock()
        self.bus.subscribe("t", broken)
        self.bus.subscribe("t", good)
        await self.bus.publish("t", {"x": 1})
        good.assert_called_once()

    def test_unsubscribe_removes_handler(self):
        handler = AsyncMock()
        self.bus.subscribe("t", handler)
        self.bus.unsubscribe("t", handler)
        assert handler not in self.bus._handlers["t"]

    def test_clear_all(self):
        self.bus.subscribe("t1", AsyncMock())
        self.bus.subscribe("t2", AsyncMock())
        self.bus.clear()
        assert self.bus.subscribed_topics == []

    def test_clear_single_topic(self):
        self.bus.subscribe("t1", AsyncMock())
        self.bus.subscribe("t2", AsyncMock())
        self.bus.clear("t1")
        assert "t1" not in self.bus.subscribed_topics
        assert "t2" in self.bus.subscribed_topics

    def test_subscribed_topics_lists_active(self):
        self.bus.subscribe("a", AsyncMock())
        self.bus.subscribe("b", AsyncMock())
        assert set(self.bus.subscribed_topics) == {"a", "b"}

    @pytest.mark.asyncio
    async def test_handler_receives_correct_payload(self):
        received = []
        async def capture(payload):
            received.append(payload)

        self.bus.subscribe("t", capture)
        await self.bus.publish("t", {"key": "value", "num": 99})
        assert received == [{"key": "value", "num": 99}]


# ---------------------------------------------------------------------------
# KafkaProducer sync-mode routing tests
# ---------------------------------------------------------------------------

class TestKafkaSyncMode:
    @pytest.mark.asyncio
    async def test_sync_mode_routes_to_local_bus(self):
        bus = LocalEventBus()
        handler = AsyncMock()
        bus.subscribe("test-topic", handler)

        p = KafkaProducer(sync_mode=True)
        with patch("src.producer.local_bus", bus):
            await p.produce("test-topic", {"event": "ping"})

        handler.assert_called_once_with({"event": "ping"})

    @pytest.mark.asyncio
    async def test_sync_mode_skips_kafka_broker(self):
        mock_aio = AsyncMock()
        p = KafkaProducer(sync_mode=True, _aiokafka_producer=mock_aio)
        bus = LocalEventBus()
        with patch("src.producer.local_bus", bus):
            await p.produce("test-topic", {"x": 1})

        mock_aio.send_and_wait.assert_not_called()

    @pytest.mark.asyncio
    async def test_sync_mode_start_logs_info(self, caplog):
        import logging
        p = KafkaProducer(sync_mode=True)
        with caplog.at_level(logging.INFO, logger="src.producer"):
            await p.start()
        assert "KAFKA_SYNC_MODE" in caplog.text
        assert p._started

    @pytest.mark.asyncio
    async def test_sync_mode_false_uses_kafka(self):
        mock_aio = AsyncMock()
        p = KafkaProducer(sync_mode=False, _aiokafka_producer=mock_aio)
        await p.produce("test-topic", {"x": 1})
        mock_aio.send_and_wait.assert_called_once()

    def test_sync_mode_reads_env_var(self):
        with patch.dict(os.environ, {"KAFKA_SYNC_MODE": "true"}):
            p = KafkaProducer()
            assert p.sync_mode is True

        with patch.dict(os.environ, {"KAFKA_SYNC_MODE": "false"}):
            p = KafkaProducer()
            assert p.sync_mode is False

    @pytest.mark.asyncio
    async def test_pydantic_model_serialised_in_sync_mode(self):
        from src.schemas.events import LLMUsageEvent
        received = []
        async def capture(payload):
            received.append(payload)

        bus = LocalEventBus()
        bus.subscribe("llm-usage-events", capture)
        p = KafkaProducer(sync_mode=True)
        event = LLMUsageEvent(
            request_id="r1",
            provider="openai",
            model_used="gpt-4o",
            token_count_input=10,
            token_count_output=5,
            total_tokens=15,
            estimated_cost_usd=0.001,
        )
        with patch("src.producer.local_bus", bus):
            await p.produce("llm-usage-events", event)

        assert received[0]["provider"] == "openai"
        assert received[0]["model_used"] == "gpt-4o"


# ---------------------------------------------------------------------------
# KafkaSettings config tests
# ---------------------------------------------------------------------------

class TestKafkaConfig:
    def test_sync_mode_default_false(self):
        from src.config import KafkaSettings
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("KAFKA_SYNC_MODE", None)
            s = KafkaSettings()
            assert s.sync_mode is False

    def test_sync_mode_enabled_via_env(self):
        from src.config import KafkaSettings
        with patch.dict(os.environ, {"KAFKA_SYNC_MODE": "true"}):
            s = KafkaSettings()
            assert s.sync_mode is True

    def test_summary_includes_sync_mode(self):
        from src.config import KafkaSettings
        with patch.dict(os.environ, {"KAFKA_SYNC_MODE": "true"}):
            s = KafkaSettings()
            assert s.summary()["sync_mode"] is True
