"""Prometheus metric definitions."""
from __future__ import annotations

from prometheus_client import Counter, Histogram

request_count = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["service", "method", "path", "status"],
)

request_latency = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency",
    ["service", "method", "path"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

llm_tokens_total = Counter(
    "llm_tokens_total",
    "Total LLM tokens consumed",
    ["service", "model", "type"],
)


class MetricsRegistry:
    """Helper to record request metrics."""

    def __init__(self, service_name: str) -> None:
        self.service_name = service_name

    def record_request(self, method: str, path: str, status: int, duration: float) -> None:
        request_count.labels(self.service_name, method, path, str(status)).inc()
        request_latency.labels(self.service_name, method, path).observe(duration)

    def record_tokens(self, model: str, token_type: str, count: int) -> None:
        llm_tokens_total.labels(self.service_name, model, token_type).inc(count)
