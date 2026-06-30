"""Unit tests for KafkaConsumer — handler execution, retries, DLQ routing."""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.consumer import KafkaConsumer


def _make_msg(payload: dict) -> MagicMock:
    msg = MagicMock()
    msg.value = json.dumps(payload).encode()
    return msg


def _make_consumer_with_messages(messages: list, auto_commit: bool = True) -> MagicMock:
    """Build a mock aiokafka consumer that yields given messages then stops."""
    mock_consumer = MagicMock()
    mock_consumer.commit = AsyncMock()
    mock_consumer.stop = AsyncMock()

    async def _aiter():
        for msg in messages:
            yield msg

    mock_consumer.__aiter__ = lambda self: _aiter()
    return mock_consumer


class TestConsumerHandlerSuccess:
    @pytest.mark.asyncio
    async def test_handler_called_for_each_message(self):
        msgs = [_make_msg({"n": i}) for i in range(3)]
        mock_consumer = _make_consumer_with_messages(msgs)
        handler = AsyncMock()

        c = KafkaConsumer(_aiokafka_consumer=mock_consumer)
        await c.consume("test-topic", handler, max_messages=3)

        assert handler.call_count == 3

    @pytest.mark.asyncio
    async def test_offset_committed_after_success(self):
        msgs = [_make_msg({"x": 1})]
        mock_consumer = _make_consumer_with_messages(msgs)
        handler = AsyncMock()

        c = KafkaConsumer(_aiokafka_consumer=mock_consumer)
        await c.consume("test-topic", handler, max_messages=1)

        mock_consumer.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_invalid_json_is_skipped(self):
        bad_msg = MagicMock()
        bad_msg.value = b"not-json{{"
        mock_consumer = _make_consumer_with_messages([bad_msg])
        handler = AsyncMock()

        c = KafkaConsumer(_aiokafka_consumer=mock_consumer)
        await c.consume("test-topic", handler, max_messages=1)

        handler.assert_not_called()
        mock_consumer.commit.assert_called_once()


class TestConsumerRetry:
    @pytest.mark.asyncio
    async def test_handler_retried_on_failure(self):
        msgs = [_make_msg({"x": 1})]
        mock_consumer = _make_consumer_with_messages(msgs)
        call_count = 0

        async def flaky_handler(payload):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("transient error")

        dlq_producer = AsyncMock()
        c = KafkaConsumer(
            _aiokafka_consumer=mock_consumer,
            _dlq_producer=dlq_producer,
            max_handler_retries=3,
        )
        with __import__("unittest.mock", fromlist=["patch"]).patch("asyncio.sleep", new=AsyncMock()):
            await c.consume("test-topic", flaky_handler, max_messages=1)

        assert call_count == 3
        dlq_producer.produce.assert_not_called()  # succeeded on 3rd attempt

    @pytest.mark.asyncio
    async def test_dlq_routing_after_all_retries_failed(self):
        msgs = [_make_msg({"x": 1})]
        mock_consumer = _make_consumer_with_messages(msgs)
        handler = AsyncMock(side_effect=RuntimeError("always fails"))

        dlq_producer = AsyncMock()
        c = KafkaConsumer(
            _aiokafka_consumer=mock_consumer,
            _dlq_producer=dlq_producer,
            max_handler_retries=3,
        )
        with __import__("unittest.mock", fromlist=["patch"]).patch("asyncio.sleep", new=AsyncMock()):
            await c.consume("test-topic", handler, max_messages=1)

        dlq_producer.produce.assert_called_once()
        call_args = dlq_producer.produce.call_args
        dlq_topic = call_args[0][0]
        assert "dlq" in dlq_topic

    @pytest.mark.asyncio
    async def test_dlq_payload_contains_original_topic_and_error(self):
        msgs = [_make_msg({"data": "sensitive"})]
        mock_consumer = _make_consumer_with_messages(msgs)
        handler = AsyncMock(side_effect=RuntimeError("boom"))
        dlq_producer = AsyncMock()

        c = KafkaConsumer(
            _aiokafka_consumer=mock_consumer,
            _dlq_producer=dlq_producer,
            max_handler_retries=1,
        )
        with __import__("unittest.mock", fromlist=["patch"]).patch("asyncio.sleep", new=AsyncMock()):
            await c.consume("my-topic", handler, max_messages=1)

        call_args = dlq_producer.produce.call_args
        dlq_payload = call_args[0][1]
        assert dlq_payload["original_topic"] == "my-topic"
        assert "boom" in dlq_payload["error"]

    @pytest.mark.asyncio
    async def test_fallback_to_local_log_when_no_dlq_producer(self, caplog):
        msgs = [_make_msg({"x": 1})]
        mock_consumer = _make_consumer_with_messages(msgs)
        handler = AsyncMock(side_effect=RuntimeError("fail"))

        import logging
        c = KafkaConsumer(_aiokafka_consumer=mock_consumer, max_handler_retries=1)
        with __import__("unittest.mock", fromlist=["patch"]).patch("asyncio.sleep", new=AsyncMock()):
            with caplog.at_level(logging.ERROR, logger="src.consumer"):
                await c.consume("my-topic", handler, max_messages=1)

        assert "DLQ_FALLBACK" in caplog.text
