"""Provider selection and circuit-breaker routing layer.

Selects the primary provider (default: OpenAI) and transparently falls back
to Azure OpenAI if the circuit breaker is open. The circuit trips when:
  - 5 consecutive 5xx errors occur, OR
  - >50% error rate in a 30-second window.

Fallback must complete within 100ms additional latency, enforced by the
circuit breaker's in-memory state (no I/O on the hot path).
"""
from __future__ import annotations

import logging
from typing import AsyncIterator

import httpx

from src.circuit_breaker.circuit_breaker import CircuitBreaker, CircuitState
from src.config import settings
from src.kafka.usage_logger import KafkaUsageLogger, UsageEvent, get_usage_logger
from src.middleware.pii_scrubber import PIIScrubber
from src.providers.anthropic_provider import AnthropicProvider
from src.providers.azure_openai_provider import AzureOpenAIProvider
from src.providers.base import LLMProvider
from src.providers.groq_provider import GroqProvider
from src.providers.ollama_provider import OllamaProvider
from src.providers.openai_provider import OpenAIProvider
from src.schemas.request import CompletionRequest
from src.schemas.response import CompletionResponse, StreamChunk

logger = logging.getLogger(__name__)

_PROVIDER_MAP: dict[str, type[LLMProvider]] = {
    "openai":    OpenAIProvider,
    "azure":     AzureOpenAIProvider,
    "anthropic": AnthropicProvider,
    "groq":      GroqProvider,
    "ollama":    OllamaProvider,
}


class LLMRouter:
    """Stateful routing layer that owns the circuit breaker and scrubber.

    Designed as a singleton injected via FastAPI dependency injection.
    """

    def __init__(
        self,
        primary: LLMProvider | None = None,
        fallback: LLMProvider | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        pii_scrubber: PIIScrubber | None = None,
        usage_logger: KafkaUsageLogger | None = None,
    ) -> None:
        primary_cls  = _PROVIDER_MAP.get(settings.default_provider,  AnthropicProvider)
        fallback_cls = _PROVIDER_MAP.get(settings.fallback_provider, OpenAIProvider)
        self._primary = primary or primary_cls()
        self._fallback = fallback or fallback_cls()
        self._cb = circuit_breaker or CircuitBreaker(
            failure_threshold=settings.cb_failure_threshold,
            error_rate_threshold=settings.cb_error_rate_threshold,
            window_seconds=settings.cb_window_seconds,
            recovery_timeout_seconds=settings.cb_recovery_timeout_seconds,
        )
        self._scrubber = pii_scrubber or PIIScrubber(
            extra_patterns_file=settings.pii_patterns_file
        )
        self._usage_logger = usage_logger or get_usage_logger()

    # ── Provider resolution ─────────────────────────────────────────────────

    @property
    def primary(self) -> LLMProvider:
        return self._primary

    def _resolve_provider(self, request: CompletionRequest) -> LLMProvider:
        """Select the provider for this request respecting circuit state."""
        if request.provider_override:
            cls = _PROVIDER_MAP.get(request.provider_override)
            if cls:
                return cls()

        if self._cb.allow_request():
            return self._primary
        logger.warning(
            "Circuit breaker OPEN — routing to fallback provider '%s'.",
            self._fallback.name,
        )
        return self._fallback

    # ── PII scrubbing ───────────────────────────────────────────────────────

    def _scrub_request(self, request: CompletionRequest) -> CompletionRequest:
        scrubbed_messages = [
            msg.model_copy(update={"content": self._scrubber.scrub(msg.content)})
            for msg in request.messages
        ]
        return request.model_copy(update={"messages": scrubbed_messages})

    # ── Synchronous completion ──────────────────────────────────────────────

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        scrubbed = self._scrub_request(request)
        provider = self._resolve_provider(scrubbed)

        try:
            response = await provider.complete(scrubbed)
            self._cb.record_success()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code >= 500:
                self._cb.record_failure()
                # Attempt failover if we were using the primary
                if provider is self._primary:
                    logger.warning(
                        "Primary provider %s returned %d — attempting fallback.",
                        provider.name,
                        exc.response.status_code,
                    )
                    response = await self._fallback.complete(scrubbed)
                else:
                    raise
            else:
                raise

        await self._log_usage(response)
        return response

    # ── Streaming completion ────────────────────────────────────────────────

    async def stream(self, request: CompletionRequest) -> AsyncIterator[StreamChunk]:
        scrubbed = self._scrub_request(request)
        provider = self._resolve_provider(scrubbed)

        try:
            async for chunk in provider.stream(scrubbed):
                if chunk.finish_reason and chunk.usage:
                    await self._log_usage_from_chunk(chunk)
                yield chunk
            self._cb.record_success()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code >= 500:
                self._cb.record_failure()
                if provider is self._primary:
                    logger.warning(
                        "Primary provider %s stream failed with %d — switching to fallback.",
                        provider.name,
                        exc.response.status_code,
                    )
                    async for chunk in self._fallback.stream(scrubbed):
                        if chunk.finish_reason and chunk.usage:
                            await self._log_usage_from_chunk(chunk)
                        yield chunk
                else:
                    raise
            else:
                raise

    # ── Usage logging ───────────────────────────────────────────────────────

    async def _log_usage(self, response: CompletionResponse) -> None:
        try:
            await self._usage_logger.log_usage(
                UsageEvent(
                    request_id=response.request_id,
                    provider=response.provider,
                    model_used=response.model_used,
                    token_count_input=response.usage.token_count_input,
                    token_count_output=response.usage.token_count_output,
                    estimated_cost_usd=response.estimated_cost_usd,
                )
            )
        except Exception as exc:
            logger.warning("Usage logging failed: %s", exc)

    async def _log_usage_from_chunk(self, chunk: StreamChunk) -> None:
        if chunk.usage is None:
            return
        try:
            await self._usage_logger.log_usage(
                UsageEvent(
                    request_id=chunk.request_id,
                    provider=chunk.provider,
                    model_used=chunk.model_used,
                    token_count_input=chunk.usage.token_count_input,
                    token_count_output=chunk.usage.token_count_output,
                    estimated_cost_usd=chunk.estimated_cost_usd or 0.0,
                )
            )
        except Exception as exc:
            logger.warning("Usage logging failed for stream chunk: %s", exc)

    @property
    def circuit_state(self) -> CircuitState:
        return self._cb.state

    def circuit_stats(self) -> dict:
        return self._cb.get_stats()
