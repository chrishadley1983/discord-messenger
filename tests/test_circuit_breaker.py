"""Tests for the circuit breaker module."""

import os
import sys
import time

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Override config before importing
import domains.peterbot.config as config
config.CIRCUIT_FAILURE_THRESHOLD = 3  # Lower threshold for faster tests
config.CIRCUIT_RECOVERY_TIMEOUT = 2   # Shorter timeout for faster tests

from domains.peterbot.circuit_breaker import (
    CircuitBreaker,
    CircuitState,
    get_circuit_breaker,
    reset_circuit_breaker,
)


def test_initial_state():
    """Circuit should start in CLOSED state."""
    print("Test: initial_state...")

    cb = CircuitBreaker(failure_threshold=3, recovery_timeout=2, name="test")

    assert cb.state == CircuitState.CLOSED
    assert cb.allow_request() is True

    stats = cb.get_stats()
    assert stats["state"] == "closed"
    assert stats["failure_count"] == 0
    assert stats["total_successes"] == 0
    assert stats["total_failures"] == 0

    print("  PASSED")


def test_stays_closed_on_success():
    """Circuit should stay closed on successful requests."""
    print("Test: stays_closed_on_success...")

    cb = CircuitBreaker(failure_threshold=3, recovery_timeout=2, name="test")

    for i in range(10):
        assert cb.allow_request() is True
        cb.record_success()

    assert cb.state == CircuitState.CLOSED
    assert cb.get_stats()["total_successes"] == 10

    print("  PASSED")


def test_opens_after_threshold_failures():
    """Circuit should open after consecutive failures reach threshold."""
    print("Test: opens_after_threshold_failures...")

    cb = CircuitBreaker(failure_threshold=3, recovery_timeout=2, name="test")

    # Record failures
    for i in range(3):
        assert cb.allow_request() is True, f"Should allow request {i+1}"
        cb.record_failure()

    # Should now be open
    assert cb.state == CircuitState.OPEN
    assert cb.allow_request() is False  # Requests blocked

    stats = cb.get_stats()
    assert stats["state"] == "open"
    assert stats["times_opened"] == 1

    print("  PASSED")


def test_success_resets_failure_count():
    """Success should reset the failure count."""
    print("Test: success_resets_failure_count...")

    cb = CircuitBreaker(failure_threshold=3, recovery_timeout=2, name="test")

    # Record 2 failures (not enough to open)
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.CLOSED
    assert cb.get_stats()["failure_count"] == 2

    # Success resets count
    cb.record_success()
    assert cb.get_stats()["failure_count"] == 0

    # Need 3 more failures to open
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.CLOSED  # Still closed

    cb.record_failure()
    assert cb.state == CircuitState.OPEN  # Now open

    print("  PASSED")


def test_transitions_to_half_open_after_timeout():
    """Circuit should transition to HALF_OPEN after recovery timeout."""
    print("Test: transitions_to_half_open_after_timeout...")

    cb = CircuitBreaker(failure_threshold=3, recovery_timeout=1, name="test")

    # Open the circuit
    for _ in range(3):
        cb.record_failure()

    assert cb.state == CircuitState.OPEN

    # Wait for recovery timeout
    print("  Waiting for recovery timeout (1s)...")
    time.sleep(1.1)

    # Should transition to HALF_OPEN on next state check
    assert cb.state == CircuitState.HALF_OPEN
    assert cb.allow_request() is True  # Should allow test request

    print("  PASSED")


def test_half_open_closes_on_success():
    """Circuit should close on successful request in HALF_OPEN state."""
    print("Test: half_open_closes_on_success...")

    cb = CircuitBreaker(failure_threshold=3, recovery_timeout=1, name="test")

    # Open the circuit
    for _ in range(3):
        cb.record_failure()

    # Wait for HALF_OPEN
    time.sleep(1.1)
    assert cb.state == CircuitState.HALF_OPEN

    # Record success
    cb.record_success()

    assert cb.state == CircuitState.CLOSED
    assert cb.get_stats()["failure_count"] == 0

    print("  PASSED")


def test_half_open_reopens_on_failure():
    """Circuit should reopen on failed request in HALF_OPEN state."""
    print("Test: half_open_reopens_on_failure...")

    cb = CircuitBreaker(failure_threshold=3, recovery_timeout=1, name="test")

    # Open the circuit
    for _ in range(3):
        cb.record_failure()

    # Wait for HALF_OPEN
    time.sleep(1.1)
    assert cb.state == CircuitState.HALF_OPEN

    # Record failure
    cb.record_failure()

    assert cb.state == CircuitState.OPEN
    # times_opened only counts CLOSED → OPEN transitions, not HALF_OPEN → OPEN
    assert cb.get_stats()["times_opened"] == 1

    print("  PASSED")


def test_force_open():
    """Can manually open the circuit."""
    print("Test: force_open...")

    cb = CircuitBreaker(failure_threshold=3, recovery_timeout=2, name="test")

    assert cb.state == CircuitState.CLOSED

    cb.force_open()

    assert cb.state == CircuitState.OPEN
    assert cb.allow_request() is False

    print("  PASSED")


def test_force_close():
    """Can manually close the circuit."""
    print("Test: force_close...")

    cb = CircuitBreaker(failure_threshold=3, recovery_timeout=2, name="test")

    # Open it
    for _ in range(3):
        cb.record_failure()
    assert cb.state == CircuitState.OPEN

    # Force close
    cb.force_close()

    assert cb.state == CircuitState.CLOSED
    assert cb.allow_request() is True

    print("  PASSED")


def test_reset():
    """Can reset circuit breaker to initial state."""
    print("Test: reset...")

    cb = CircuitBreaker(failure_threshold=3, recovery_timeout=2, name="test")

    # Accumulate some state
    cb.record_success()
    cb.record_success()
    cb.record_failure()
    cb.record_failure()
    cb.record_failure()  # Opens circuit

    assert cb.state == CircuitState.OPEN
    assert cb.get_stats()["total_successes"] == 2
    assert cb.get_stats()["total_failures"] == 3

    # Reset
    cb.reset()

    assert cb.state == CircuitState.CLOSED
    stats = cb.get_stats()
    assert stats["total_successes"] == 0
    assert stats["total_failures"] == 0
    assert stats["times_opened"] == 0

    print("  PASSED")


def test_global_circuit_breaker():
    """Test global circuit breaker access."""
    print("Test: global_circuit_breaker...")

    # Reset first
    reset_circuit_breaker()

    cb1 = get_circuit_breaker()
    cb2 = get_circuit_breaker()

    # Should be same instance
    assert cb1 is cb2

    # Should be usable
    assert cb1.state == CircuitState.CLOSED
    assert cb1.allow_request() is True

    print("  PASSED")


def test_thread_safety():
    """Basic thread safety test."""
    print("Test: thread_safety...")

    import threading

    cb = CircuitBreaker(failure_threshold=100, recovery_timeout=2, name="test")

    errors = []

    def record_operations():
        try:
            for _ in range(100):
                if cb.allow_request():
                    cb.record_success()
                cb.record_failure()
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=record_operations) for _ in range(10)]

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0, f"Thread errors: {errors}"

    # Should have recorded lots of operations
    stats = cb.get_stats()
    assert stats["total_successes"] > 0
    assert stats["total_failures"] > 0

    print(f"  Recorded {stats['total_successes']} successes, {stats['total_failures']} failures")
    print("  PASSED")


def main():
    print("=" * 60)
    print("Circuit Breaker Tests")
    print("=" * 60)
    print()

    test_initial_state()
    test_stays_closed_on_success()
    test_opens_after_threshold_failures()
    test_success_resets_failure_count()
    test_transitions_to_half_open_after_timeout()
    test_half_open_closes_on_success()
    test_half_open_reopens_on_failure()
    test_force_open()
    test_force_close()
    test_reset()
    test_global_circuit_breaker()
    test_thread_safety()

    print()
    print("=" * 60)
    print("ALL CIRCUIT BREAKER TESTS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    main()
