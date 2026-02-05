"""Tests for worker_health.py circuit breaker integration.

Uses pytest fixtures for proper test isolation.
"""

import os
import sys
import asyncio
import tempfile
import pytest

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def worker_health_env(monkeypatch):
    """Create isolated environment for worker health tests."""
    import domains.peterbot.config as config

    # Create unique temp file
    fd, temp_path = tempfile.mkstemp(suffix="_worker_health.db")
    os.close(fd)

    # Override config
    monkeypatch.setattr(config, 'CAPTURE_STORE_DB', temp_path)
    monkeypatch.setattr(config, 'CIRCUIT_FAILURE_THRESHOLD', 3)
    monkeypatch.setattr(config, 'CIRCUIT_RECOVERY_TIMEOUT', 1)

    # Delete peterbot submodules EXCEPT config
    # Also delete jobs.worker_health so it gets reimported with fresh peterbot refs
    for mod in list(sys.modules.keys()):
        if 'domains.peterbot' in mod and 'config' not in mod:
            del sys.modules[mod]
        if mod == 'jobs.worker_health':
            del sys.modules[mod]

    # Reimport with fresh state
    from domains.peterbot import capture_store
    from domains.peterbot import circuit_breaker as cb_module
    from domains.peterbot.circuit_breaker import (
        get_circuit_breaker,
        reset_circuit_breaker,
        CircuitState,
    )

    # Reset connection and circuit breaker
    capture_store.close()
    capture_store._connection = None
    cb_module._worker_circuit_breaker = None
    reset_circuit_breaker()
    cb = get_circuit_breaker()
    cb.force_close()

    yield {
        'capture_store': capture_store,
        'config': config,
        'get_circuit_breaker': get_circuit_breaker,
        'reset_circuit_breaker': reset_circuit_breaker,
        'CircuitState': CircuitState,
    }

    # Cleanup
    capture_store.close()
    try:
        os.unlink(temp_path)
        for suffix in ["-wal", "-shm"]:
            try:
                os.unlink(temp_path + suffix)
            except FileNotFoundError:
                pass
    except Exception:
        pass


class MockBot:
    """Mock Discord bot for testing."""

    def __init__(self):
        self.sent_messages = []
        self._channel = MockChannel(self)

    def get_channel(self, channel_id):
        return self._channel

    async def fetch_channel(self, channel_id):
        return self._channel


class MockChannel:
    """Mock Discord channel for testing."""

    def __init__(self, bot):
        self.bot = bot

    async def send(self, message):
        self.bot.sent_messages.append(message)


def test_circuit_breaker_import(worker_health_env):
    """Verify worker_health can import circuit breaker."""
    from jobs.worker_health import get_circuit_breaker, CircuitState

    cb = get_circuit_breaker()
    assert cb is not None
    assert cb.state in (CircuitState.CLOSED, CircuitState.OPEN, CircuitState.HALF_OPEN)


def test_circuit_state_in_health_check(worker_health_env):
    """Verify circuit state is checked in health check."""
    get_circuit_breaker = worker_health_env['get_circuit_breaker']
    CircuitState = worker_health_env['CircuitState']

    cb = get_circuit_breaker()

    # Verify initial state
    assert cb.state == CircuitState.CLOSED

    # Open the circuit
    for _ in range(3):
        cb.record_failure()

    assert cb.state == CircuitState.OPEN

    # Check that stats contain the expected fields
    stats = cb.get_stats()
    assert "state" in stats
    assert "time_in_current_state" in stats
    assert "total_failures" in stats
    assert "times_opened" in stats

    assert stats["state"] == "open"
    assert stats["times_opened"] == 1


@pytest.mark.asyncio
async def test_health_check_includes_circuit_state(worker_health_env):
    """Verify health check includes circuit state in alerts when circuit is open."""
    from jobs.worker_health import worker_health_check, LOCAL_QUEUE_WARNING_THRESHOLD

    capture_store = worker_health_env['capture_store']
    get_circuit_breaker = worker_health_env['get_circuit_breaker']
    config = worker_health_env['config']
    CircuitState = worker_health_env['CircuitState']

    cb = get_circuit_breaker()
    for _ in range(config.CIRCUIT_FAILURE_THRESHOLD):
        cb.record_failure()

    assert cb.state == CircuitState.OPEN, "Circuit should be OPEN"

    # Add pending captures to trigger local queue alert
    for i in range(LOCAL_QUEUE_WARNING_THRESHOLD + 5):
        capture_store.add_capture(
            session_id=f"test-session-open-{i}",
            user_message=f"Test message {i}",
            assistant_response=f"Test response {i}",
            channel="test"
        )

    mock_bot = MockBot()

    # Run health check
    await worker_health_check(mock_bot)

    messages = mock_bot.sent_messages

    # Should have at least one message (local queue alert with circuit state)
    assert len(messages) >= 1, f"Expected at least 1 alert, got {len(messages)}"

    # Find an alert that includes circuit state
    circuit_alert = None
    for msg in messages:
        if "Circuit:" in msg:
            circuit_alert = msg
            break

    assert circuit_alert is not None, f"No alert with circuit state found. Messages: {messages}"
    assert "OPEN" in circuit_alert, f"Circuit OPEN not in alert: {circuit_alert[:200]}"


def test_circuit_open_alert_threshold(worker_health_env):
    """Verify CIRCUIT_OPEN_ALERT_SECONDS is set correctly."""
    from jobs.worker_health import CIRCUIT_OPEN_ALERT_SECONDS

    # Should be 30 minutes (1800 seconds)
    assert CIRCUIT_OPEN_ALERT_SECONDS == 1800, \
        f"Expected 1800, got {CIRCUIT_OPEN_ALERT_SECONDS}"


def test_local_queue_alert_includes_circuit(worker_health_env):
    """Verify local queue alert includes circuit state when not closed."""
    import inspect
    from jobs.worker_health import worker_health_check

    source = inspect.getsource(worker_health_check)

    # Check that circuit state is conditionally included
    assert 'circuit_info = f"Circuit: **{circuit_state.upper()}**' in source, \
        "Circuit state formatting not found in worker_health_check"
    assert 'if circuit_state != "closed"' in source, \
        "Circuit state condition not found in worker_health_check"


def test_logging_includes_circuit(worker_health_env):
    """Verify logging includes circuit state."""
    import inspect
    from jobs.worker_health import worker_health_check

    source = inspect.getsource(worker_health_check)

    # Check that circuit state is included in log messages
    assert "circuit={circuit_state}" in source, \
        "Circuit state not included in log format"
