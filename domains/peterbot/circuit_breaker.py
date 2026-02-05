"""Circuit breaker for peterbot-mem worker calls.

Prevents hammering a dead worker and enables graceful degradation.

States:
- CLOSED: Normal operation, requests pass through
- OPEN: Worker is down, requests fail fast (no network call)
- HALF_OPEN: Testing recovery, one request allowed through

Transitions:
- CLOSED → OPEN: After CIRCUIT_FAILURE_THRESHOLD consecutive failures
- OPEN → HALF_OPEN: After CIRCUIT_RECOVERY_TIMEOUT seconds
- HALF_OPEN → CLOSED: On successful request
- HALF_OPEN → OPEN: On failed request
"""

import time
import threading
from enum import Enum
from typing import Optional

from logger import logger
from . import config


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing fast, no requests
    HALF_OPEN = "half_open"  # Testing recovery


class CircuitBreaker:
    """Thread-safe circuit breaker for worker calls.

    Usage:
        breaker = CircuitBreaker()

        if breaker.allow_request():
            try:
                result = await make_worker_call()
                breaker.record_success()
                return result
            except Exception as e:
                breaker.record_failure()
                raise
        else:
            # Circuit is open, use fallback
            return fallback_value
    """

    def __init__(
        self,
        failure_threshold: Optional[int] = None,
        recovery_timeout: Optional[int] = None,
        name: str = "worker"
    ):
        """Initialize circuit breaker.

        Args:
            failure_threshold: Consecutive failures before opening (default from config)
            recovery_timeout: Seconds before testing recovery (default from config)
            name: Name for logging purposes
        """
        self.failure_threshold = failure_threshold or config.CIRCUIT_FAILURE_THRESHOLD
        self.recovery_timeout = recovery_timeout or config.CIRCUIT_RECOVERY_TIMEOUT
        self.name = name

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: Optional[float] = None
        self._opened_at: Optional[float] = None
        self._lock = threading.Lock()

        # Stats for monitoring
        self._total_successes = 0
        self._total_failures = 0
        self._times_opened = 0

    @property
    def state(self) -> CircuitState:
        """Get current circuit state, checking for auto-transition to HALF_OPEN."""
        with self._lock:
            return self._get_state_locked()

    def _get_state_locked(self) -> CircuitState:
        """Get state while holding lock (checks for OPEN → HALF_OPEN transition)."""
        if self._state == CircuitState.OPEN:
            # Check if recovery timeout has elapsed
            if self._opened_at and (time.time() - self._opened_at) >= self.recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                logger.info(f"Circuit breaker [{self.name}]: OPEN → HALF_OPEN (testing recovery)")

        return self._state

    def allow_request(self) -> bool:
        """Check if a request should be allowed through.

        Returns:
            True if request should proceed, False if circuit is open
        """
        with self._lock:
            state = self._get_state_locked()

            if state == CircuitState.CLOSED:
                return True
            elif state == CircuitState.HALF_OPEN:
                # Allow one request through to test recovery
                return True
            else:  # OPEN
                return False

    def record_success(self) -> None:
        """Record a successful request."""
        with self._lock:
            self._total_successes += 1

            if self._state == CircuitState.HALF_OPEN:
                # Recovery confirmed, close circuit
                self._state = CircuitState.CLOSED
                self._failure_count = 0
                self._opened_at = None
                logger.info(f"Circuit breaker [{self.name}]: HALF_OPEN → CLOSED (worker recovered)")
            elif self._state == CircuitState.CLOSED:
                # Reset failure count on success
                self._failure_count = 0

    def record_failure(self) -> None:
        """Record a failed request."""
        with self._lock:
            self._failure_count += 1
            self._total_failures += 1
            self._last_failure_time = time.time()

            if self._state == CircuitState.HALF_OPEN:
                # Recovery test failed, reopen circuit
                self._state = CircuitState.OPEN
                self._opened_at = time.time()
                logger.warning(f"Circuit breaker [{self.name}]: HALF_OPEN → OPEN (recovery failed)")

            elif self._state == CircuitState.CLOSED:
                if self._failure_count >= self.failure_threshold:
                    # Too many failures, open circuit
                    self._state = CircuitState.OPEN
                    self._opened_at = time.time()
                    self._times_opened += 1
                    logger.warning(
                        f"Circuit breaker [{self.name}]: CLOSED → OPEN "
                        f"(after {self._failure_count} consecutive failures)"
                    )

    def force_open(self) -> None:
        """Manually open the circuit (for testing or emergency)."""
        with self._lock:
            if self._state != CircuitState.OPEN:
                self._state = CircuitState.OPEN
                self._opened_at = time.time()
                self._times_opened += 1
                logger.warning(f"Circuit breaker [{self.name}]: Manually opened")

    def force_close(self) -> None:
        """Manually close the circuit (for testing or recovery)."""
        with self._lock:
            if self._state != CircuitState.CLOSED:
                self._state = CircuitState.CLOSED
                self._failure_count = 0
                self._opened_at = None
                logger.info(f"Circuit breaker [{self.name}]: Manually closed")

    def get_stats(self) -> dict:
        """Get circuit breaker statistics.

        Returns:
            Dict with state, failure_count, total_successes, total_failures, etc.
        """
        with self._lock:
            state = self._get_state_locked()
            time_in_state = None

            if self._opened_at and state in (CircuitState.OPEN, CircuitState.HALF_OPEN):
                time_in_state = int(time.time() - self._opened_at)

            return {
                "state": state.value,
                "failure_count": self._failure_count,
                "failure_threshold": self.failure_threshold,
                "total_successes": self._total_successes,
                "total_failures": self._total_failures,
                "times_opened": self._times_opened,
                "time_in_current_state": time_in_state,
                "recovery_timeout": self.recovery_timeout,
            }

    def reset(self) -> None:
        """Reset circuit breaker to initial state (for testing)."""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._last_failure_time = None
            self._opened_at = None
            self._total_successes = 0
            self._total_failures = 0
            self._times_opened = 0
            logger.debug(f"Circuit breaker [{self.name}]: Reset to initial state")


# Global circuit breaker instance for worker calls
# Shared across all memory operations
_worker_circuit_breaker: Optional[CircuitBreaker] = None


def get_circuit_breaker() -> CircuitBreaker:
    """Get the global circuit breaker for worker calls.

    Creates the instance on first call (lazy initialization).
    """
    global _worker_circuit_breaker

    if _worker_circuit_breaker is None:
        _worker_circuit_breaker = CircuitBreaker(name="peterbot-mem")
        logger.info("Circuit breaker initialized for peterbot-mem worker")

    return _worker_circuit_breaker


def reset_circuit_breaker() -> None:
    """Reset the global circuit breaker (for testing)."""
    global _worker_circuit_breaker

    if _worker_circuit_breaker is not None:
        _worker_circuit_breaker.reset()
    else:
        _worker_circuit_breaker = CircuitBreaker(name="peterbot-mem")
