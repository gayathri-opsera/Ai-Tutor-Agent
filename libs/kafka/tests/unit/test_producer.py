"""Unit tests for KafkaProducer — retry logic, DLQ routing, serialisation."""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from src.producer import KafkaProducer, ProduceError
from src.schemas.events import LLMUsageEvent


def make_producer(mock_aiokafka: AsyncMock | None = None) -> KafkaProducer:
    return KafkaProducer(_aiokafka_producer=mock_aiokafka, max_retries=3)


class TestProduceSuccess:
    @pytest.mark.asyncio
    async def test_basic_dict_produce(self):
        mock = AsyncMock()
        p = make_producer(mock)
        await p.produce("my-topic", {"key": "val"}, key="k1")
        mock.send_and_wait.assert_called_once()
        args = mock.send_and_wait.call_args
        assert args.kwargs["key"] == "k1" or args[1].get("key") == "k1" or "k1" in str(args)

    @pytest.mark.asyncio
    async def test_pydantic_model_serialised(self):
        mock = AsyncMock()
        p = make_producer(mock)
        event = LLMUsageEvent(
            request_id="req-1",
            provider="openai",
            model_used="gpt-4o",
            token_count_input=10,
            token_count_output=5,
            total_tokens=15,
            estimated_cost_usd=0.001,
        )
        await p.produce("llm-usage-events", event)
        mock.send_and_wait.assert_called_once()
        _, kwargs = mock.send_and_wait.call_args
        payload = kwargs.get("value") or mock.send_and_wait.call_args[0][1]
        assert isinstance(payload, dict)
        assert payload["provider"] == "openai"

    @pytest.mark.asyncio
    async def test_no_kafka_logs_locally(self, caplog):
        p = make_producer(None)
        import logging
        with caplog.at_level(logging.INFO, logger="src.producer"):
            await p.produce("my-topic", {"data": 1})
        assert "KAFKA_LOCAL" in caplog.text


class TestProduceRetry:
    @pytest.mark.asyncio
    async def test_retries_on_transient_failure(self):
        mock = AsyncMock()
        mock.send_and_wait.side_effect = [
            Exception("transient"),
            Exception("transient"),
            None,  # third attempt succeeds
        ]
        p = make_producer(mock)
        with patch("asyncio.sleep", new_callable=AsyncMock):
            await p.produce("my-topic", {"x": 1})
        assert mock.send_and_wait.call_count == 3

    @pytest.mark.asyncio
    async def test_routes_to_dlq_after_all_retries_exhausted(self):
        mock = AsyncMock()
        mock.send_and_wait.side_effect = [
            Exception("fail1"),
            Exception("fail2"),
            Exception("fail3"),
            None,  # DLQ produce succeeds
        ]
        p = make_producer(mock)
        with patch("asyncio.sleep", new_callable=AsyncMock):
            await p.produce("my-topic", {"x": 1})
        # 4th call should be to DLQ topic
        fourth_call_args = mock.send_and_wait.call_args_list[3]
        topic_arg = fourth_call_args[0][0] if fourth_call_args[0] else fourth_call_args[1].get("topic") or str(fourth_call_args)
        assert "dlq" in str(fourth_call_args).lower() or "dlq" in str(mock.send_and_wait.call_args_list).lower()

    @pytest.mark.asyncio
    async def test_dlq_payload_contains_original_topic(self):
        sent_payloads = []

        async def capture_send(topic, *, value, key, headers):
            sent_payloads.append((topic, value))

        mock = AsyncMock()
        mock.send_and_wait.side_effect = [
            Exception("fail1"),
            Exception("fail2"),
            Exception("fail3"),
            None,
        ]

        p = make_producer(mock)

        captured_topics = []
        captured_payloads = []

        orig_send = p._send

        async def spy_send(topic, value, key, headers):
            captured_topics.append(topic)
            captured_payloads.append(value)
            return await orig_send(topic, value, key, headers)

        p._send = spy_send

        with patch("asyncio.sleep", new_callable=AsyncMock):
            await p.produce("my-topic", {"x": 1})

        dlq_payload = captured_payloads[-1]
        assert dlq_payload["original_topic"] == "my-topic"

    @pytest.mark.asyncio
    async def test_raises_produce_error_when_dlq_also_fails(self):
        mock = AsyncMock()
        mock.send_and_wait.side_effect = Exception("always fail")
        p = make_producer(mock)
        with patch("asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(ProduceError):
                await p.produce("my-topic", {"x": 1})


class TestProducerLifecycle:
    @pytest.mark.asyncio
    async def test_start_stop(self):
        mock_aiokafka = AsyncMock()
        p = KafkaProducer(_aiokafka_producer=mock_aiokafka)
        await p.start()
        assert p._started
        await p.stop()
        assert not p._started

    @pytest.mark.asyncio
    async def test_start_gracefully_handles_connection_failure(self):
        """Producer should degrade gracefully when aiokafka can't connect."""
        import src.producer as producer_module

        fake_broken = MagicMock(side_effect=Exception("no broker"))
        with patch.object(producer_module, "_MAX_RETRIES", 1):
            p = KafkaProducer(bootstrap_servers="invalid:9999", max_retries=1)
            # Directly simulate the start path raising by injecting a broken producer
            p._producer = None

            async def broken_start():
                raise Exception("no broker")

            mock_aio = MagicMock()
            mock_aio.start = broken_start
            mock_aio.stop = AsyncMock()

            with patch("aiokafka.AIOKafkaProducer", return_value=mock_aio):
                await p.start()
            # After failure, producer is None and _started is True (degraded mode)
            assert p._started
