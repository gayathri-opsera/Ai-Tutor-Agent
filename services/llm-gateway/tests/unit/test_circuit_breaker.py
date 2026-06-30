"""Unit tests for CircuitBreaker state machine.

Covers: closed→open→half-open→closed transitions, error-rate threshold,
failure-count threshold, window pruning, reset, and stats reporting.
"""
from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from src.circuit_breaker.circuit_breaker import CircuitBreaker, CircuitState


def make_cb(**kwargs) -> CircuitBreaker:
    defaults = {
        "failure_threshold": 3,
        "error_rate_threshold": 0.5,
        "window_seconds": 30,
        "recovery_timeout_seconds": 60,
    }
    defaults.update(kwargs)
    return CircuitBreaker(**defaults)


class TestClosedState:
    def test_initial_state_is_closed(self):
        cb = make_cb()
        assert cb.state == CircuitState.CLOSED

    def test_allow_request_in_closed_state(self):
        cb = make_cb()
        assert cb.allow_request() is True

    def test_success_does_not_change_state(self):
        cb = make_cb()
        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_failures_below_threshold_remain_closed(self):
        cb = make_cb(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED

    def test_trips_after_threshold_failures_at_high_error_rate(self):
        cb = make_cb(failure_threshold=3, error_rate_threshold=0.5)
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_does_not_trip_when_error_rate_below_threshold(self):
        """Enough failures but not enough error rate — stays CLOSED."""
        cb = make_cb(failure_threshold=2, error_rate_threshold=0.9)
        # 3 successes, 2 failures = 40% error rate < 90% threshold
        cb.record_success()
        cb.record_success()
        cb.record_success()
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED


class TestOpenState:
    def test_open_blocks_primary_requests(self):
        cb = make_cb(failure_threshold=1, error_rate_threshold=0.5)
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.allow_request() is False

    def test_open_transitions_to_half_open_after_timeout(self):
        cb = make_cb(failure_threshold=1, error_rate_threshold=0.5, recovery_timeout_seconds=1)
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        # Simulate time passing beyond recovery timeout
        with patch("src.circuit_breaker.circuit_breaker.time.monotonic", return_value=time.monotonic() + 2):
            result = cb.allow_request()
        assert result is True
        assert cb.state == CircuitState.HALF_OPEN


class TestHalfOpenState:
    def _open_cb(self) -> CircuitBreaker:
        cb = make_cb(failure_threshold=1, error_rate_threshold=0.5, recovery_timeout_seconds=0)
        cb.record_failure()
        # Force transition to half-open
        with patch("src.circuit_breaker.circuit_breaker.time.monotonic", return_value=time.monotonic() + 1):
            cb.allow_request()
        return cb

    def test_success_in_half_open_closes_circuit(self):
        cb = self._open_cb()
        assert cb.state == CircuitState.HALF_OPEN
        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_failure_in_half_open_reopens_circuit(self):
        cb = self._open_cb()
        assert cb.state == CircuitState.HALF_OPEN
        cb.record_failure()
        assert cb.state == CircuitState.OPEN


class TestWindowPruning:
    def test_old_events_are_pruned(self):
        # Use a high threshold so old events don't trip the circuit while being recorded.
        # threshold=5, window=5s. Record 4 failures at t-10 (old); then reset state to CLOSED
        # so we can test pruning on the next fresh call.
        cb = make_cb(failure_threshold=5, window_seconds=5)
        old_time = time.monotonic() - 10
        with patch("src.circuit_breaker.circuit_breaker.time.monotonic", return_value=old_time):
            # Record 4 failures — below the threshold of 5, so circuit stays CLOSED
            for _ in range(4):
                cb.record_failure()

        assert cb.state == CircuitState.CLOSED  # still closed (below threshold)

        # One fresh failure now — the 4 old events should be pruned, leaving only 1
        cb.record_failure()
        stats = cb.get_stats()
        assert stats["window_total"] == 1  # only the fresh failure survives
        assert cb.state == CircuitState.CLOSED  # 1 failure < threshold=5


class TestReset:
    def test_reset_closes_open_circuit(self):
        cb = make_cb(failure_threshold=1, error_rate_threshold=0.5)
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        cb.reset()
        assert cb.state == CircuitState.CLOSED
        assert cb.allow_request() is True

    def test_reset_clears_window(self):
        cb = make_cb(failure_threshold=1, error_rate_threshold=0.5)
        cb.record_failure()
        cb.reset()
        stats = cb.get_stats()
        assert stats["window_total"] == 0


class TestStats:
    def test_stats_include_state_and_counts(self):
        cb = make_cb(failure_threshold=5)
        cb.record_success()
        cb.record_failure()
        stats = cb.get_stats()
        assert stats["state"] == "closed"
        assert stats["window_total"] == 2
        assert stats["window_failures"] == 1
        assert abs(stats["error_rate"] - 0.5) < 0.01
