"""Unit tests for KafkaUsageLogger."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.kafka.usage_logger import KafkaUsageLogger, UsageEvent, get_usage_logger


def make_event() -> UsageEvent:
    return UsageEvent(
        request_id="test-req-kafka-001",
        provider="openai",
        model_used="gpt-4o",
        token_count_input=10,
        token_count_output=5,
        estimated_cost_usd=0.00005,
        extra={"latency_ms": 250},
    )


class TestUsageEvent:
    def test_to_dict_contains_required_fields(self):
        event = make_event()
        d = event.to_dict()
        assert d["request_id"] == "test-req-kafka-001"
        assert d["provider"] == "openai"
        assert d["model_used"] == "gpt-4o"
        assert d["token_count_input"] == 10
        assert d["token_count_output"] == 5
        assert d["estimated_cost_usd"] == 0.00005
        assert "timestamp_ms" in d
        assert d["latency_ms"] == 250

    def test_timestamp_ms_is_reasonable(self):
        import time
        event = make_event()
        now_ms = int(time.time() * 1000)
        assert abs(event.timestamp_ms - now_ms) < 2000


class TestKafkaUsageLoggerDisabled:
    @pytest.mark.asyncio
    async def test_disabled_logger_does_not_connect(self):
        with patch("src.kafka.usage_logger.settings") as mock_settings:
            mock_settings.kafka_enabled = False
            logger = KafkaUsageLogger()
            await logger.start()
            assert logger._producer is None

    @pytest.mark.asyncio
    async def test_disabled_logger_logs_locally(self, caplog):
        import logging
        with patch("src.kafka.usage_logger.settings") as mock_settings:
            mock_settings.kafka_enabled = False
            logger = KafkaUsageLogger()
            with caplog.at_level(logging.INFO, logger="src.kafka.usage_logger"):
                await logger.log_usage(make_event())
            assert any("LLM_USAGE_EVENT" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_stop_without_producer_is_safe(self):
        logger = KafkaUsageLogger()
        logger._producer = None
        await logger.stop()  # must not raise


class TestKafkaUsageLoggerEnabled:
    @pytest.mark.asyncio
    async def test_log_usage_sends_to_kafka_when_producer_exists(self):
        logger = KafkaUsageLogger()
        mock_producer = AsyncMock()
        mock_producer.send_and_wait = AsyncMock()
        logger._producer = mock_producer

        await logger.log_usage(make_event())

        mock_producer.send_and_wait.assert_called_once()
        call_kwargs = mock_producer.send_and_wait.call_args
        assert "test-req-kafka-001".encode() in call_kwargs.kwargs.get("key", b"") or \
               b"test-req-kafka-001" == call_kwargs.kwargs.get("key", b"")

    @pytest.mark.asyncio
    async def test_kafka_failure_does_not_propagate(self):
        """A Kafka error must never fail the caller's request."""
        logger = KafkaUsageLogger()
        mock_producer = AsyncMock()
        mock_producer.send_and_wait = AsyncMock(side_effect=Exception("Kafka unavailable"))
        logger._producer = mock_producer

        # Must complete without raising
        await logger.log_usage(make_event())

    @pytest.mark.asyncio
    async def test_stop_closes_producer(self):
        logger = KafkaUsageLogger()
        mock_producer = AsyncMock()
        mock_producer.stop = AsyncMock()
        logger._producer = mock_producer

        await logger.stop()
        mock_producer.stop.assert_called_once()


class TestGetUsageLogger:
    def test_returns_singleton(self):
        import src.kafka.usage_logger as module
        module._logger_instance = None  # reset
        logger1 = get_usage_logger()
        logger2 = get_usage_logger()
        assert logger1 is logger2
        module._logger_instance = None  # cleanup
