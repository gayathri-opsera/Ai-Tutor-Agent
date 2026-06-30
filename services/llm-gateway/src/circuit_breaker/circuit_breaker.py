"""Sliding-window circuit breaker for LLM provider failover (ADR-001).

State machine: CLOSED → OPEN → HALF_OPEN → CLOSED
                                 ↑____________|

Trips when, within a rolling `window_seconds` window:
  - At least `failure_threshold` failures have occurred, AND
  - The error rate exceeds `error_rate_threshold` (50% by default).

Once open, routes all traffic to the fallback provider until
`recovery_timeout_seconds` elapses, then moves to HALF_OPEN to probe.
"""
from __future__ import annotations

import asyncio
import time
from collections import deque
from enum import Enum
from threading import Lock


class CircuitState(str, Enum):
    CLOSED = "closed"       # Normal operation — primary provider active
    OPEN = "open"           # Primary tripped — fallback active
    HALF_OPEN = "half_open" # Probe mode — one request let through


class CircuitBreakerError(Exception):
    """Raised when the circuit is OPEN and no fallback is available."""


class CircuitBreaker:
    """Thread-safe sliding-window circuit breaker.

    Each element of the window is a (timestamp, success: bool) tuple.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        error_rate_threshold: float = 0.5,
        window_seconds: int = 30,
        recovery_timeout_seconds: int = 60,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.error_rate_threshold = error_rate_threshold
        self.window_seconds = window_seconds
        self.recovery_timeout_seconds = recovery_timeout_seconds

        self._state = CircuitState.CLOSED
        self._lock = Lock()
        self._window: deque[tuple[float, bool]] = deque()
        self._opened_at: float | None = None

    @property
    def state(self) -> CircuitState:
        return self._state

    def _prune_window(self, now: float) -> None:
        """Remove events outside the rolling window (must be called under lock)."""
        cutoff = now - self.window_seconds
        while self._window and self._window[0][0] < cutoff:
            self._window.popleft()

    def _should_trip(self) -> bool:
        """Evaluate whether the circuit should transition CLOSED → OPEN."""
        total = len(self._window)
        if total == 0:
            return False
        failures = sum(1 for _, success in self._window if not success)
        if failures < self.failure_threshold:
            return False
        return (failures / total) >= self.error_rate_threshold

    def record_success(self) -> None:
        """Record a successful call and potentially close the circuit."""
        now = time.monotonic()
        with self._lock:
            self._prune_window(now)
            self._window.append((now, True))
            if self._state == CircuitState.HALF_OPEN:
                # Probe succeeded — restore normal service
                self._state = CircuitState.CLOSED
                self._opened_at = None

    def record_failure(self) -> None:
        """Record a failed call and potentially open the circuit."""
        now = time.monotonic()
        with self._lock:
            self._prune_window(now)
            self._window.append((now, False))
            if self._state == CircuitState.CLOSED and self._should_trip():
                self._state = CircuitState.OPEN
                self._opened_at = now
            elif self._state == CircuitState.HALF_OPEN:
                # Probe failed — back to OPEN
                self._state = CircuitState.OPEN
                self._opened_at = now

    def allow_request(self) -> bool:
        """Return True when the request should use the primary provider."""
        now = time.monotonic()
        with self._lock:
            if self._state == CircuitState.CLOSED:
                return True
            if self._state == CircuitState.OPEN:
                if (
                    self._opened_at is not None
                    and (now - self._opened_at) >= self.recovery_timeout_seconds
                ):
                    self._state = CircuitState.HALF_OPEN
                    return True  # Let one probe through
                return False
            # HALF_OPEN — only one probe already let through
            return False

    def reset(self) -> None:
        """Force circuit back to CLOSED (for testing / admin override)."""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._window.clear()
            self._opened_at = None

    def get_stats(self) -> dict:
        now = time.monotonic()
        with self._lock:
            self._prune_window(now)
            total = len(self._window)
            failures = sum(1 for _, s in self._window if not s)
            return {
                "state": self._state.value,
                "window_total": total,
                "window_failures": failures,
                "error_rate": failures / total if total else 0.0,
                "opened_at": self._opened_at,
            }
