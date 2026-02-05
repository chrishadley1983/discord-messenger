"""Phase 2 Integration Tests - Circuit Breaker with Memory Module.

Tests that the circuit breaker correctly protects memory operations
and integrates with the capture queue.

Uses pytest fixtures for proper test isolation.
"""

import os
import sys
import asyncio
import tempfile
import time
import pytest

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def phase2_env(monkeypatch):
    """Create isolated environment for phase 2 tests."""
    import domains.peterbot.config as config

    # Create unique temp file
    fd, temp_path = tempfile.mkstemp(suffix="_phase2.db")
    os.close(fd)

    # Override config
    monkeypatch.setattr(config, 'CAPTURE_STORE_DB', temp_path)
    monkeypatch.setattr(config, 'CIRCUIT_FAILURE_THRESHOLD', 3)
    monkeypatch.setattr(config, 'CIRCUIT_RECOVERY_TIMEOUT', 1)
    monkeypatch.setattr(config, 'WORKER_URL', "http://localhost:99999")
    monkeypatch.setattr(config, 'MESSAGES_ENDPOINT', "http://localhost:99999/api/sessions/messages")
    monkeypatch.setattr(config, 'CONTEXT_ENDPOINT', "http://localhost:99999/api/context/inject")

    # Delete peterbot submodules EXCEPT config
    for mod in list(sys.modules.keys()):
        if 'domains.peterbot' in mod and 'config' not in mod:
            del sys.modules[mod]

    # Reimport with fresh state
    from domains.peterbot import capture_store
    from domains.peterbot import memory
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
        'memory': memory,
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


def test_memory_exports_circuit_functions(phase2_env):
    """Verify memory module exports circuit breaker functions."""
    memory = phase2_env['memory']

    # Check exports
    assert hasattr(memory, 'get_circuit_state'), "get_circuit_state not exported"
    assert hasattr(memory, 'is_circuit_open'), "is_circuit_open not exported"

    # Verify they work
    state = memory.get_circuit_state()
    assert "state" in state, f"Invalid state dict: {state}"

    is_open = memory.is_circuit_open()
    assert isinstance(is_open, bool), f"is_circuit_open returned {type(is_open)}"


@pytest.mark.asyncio
async def test_circuit_breaker_affects_context_fetch(phase2_env):
    """Verify circuit breaker uses degraded mode when open."""
    memory = phase2_env['memory']
    get_circuit_breaker = phase2_env['get_circuit_breaker']
    CircuitState = phase2_env['CircuitState']

    cb = get_circuit_breaker()

    # Circuit should be closed
    assert cb.state == CircuitState.CLOSED
    assert memory.is_circuit_open() is False

    # Open the circuit
    for _ in range(3):
        cb.record_failure()

    assert cb.state == CircuitState.OPEN
    assert memory.is_circuit_open() is True

    # Now fetch context - should return degraded mode (no cache available)
    context, is_degraded = await memory.get_memory_context("test query")
    assert is_degraded is True, "Should be in degraded mode when circuit open"
    assert "MEMORY SYSTEM UNAVAILABLE" in context or context == "", \
        f"Expected degraded mode notice or empty, got: {context[:100]}"


@pytest.mark.asyncio
async def test_capture_records_circuit_state(phase2_env):
    """Verify capture operations work with circuit breaker."""
    memory = phase2_env['memory']

    # Get initial stats
    initial_stats = memory.get_queue_stats()
    initial_total = (
        initial_stats.get("pending_count", 0) +
        initial_stats.get("sending_count", 0) +
        initial_stats.get("sent_count", 0) +
        initial_stats.get("failed_count", 0)
    )

    # Capture a message pair
    result = await memory.capture_message_pair(
        session_id="test-phase2-capture",
        user_message="Testing circuit breaker integration",
        assistant_response="This tests the Phase 2 integration",
        channel="test"
    )
    assert result is True, "Capture should succeed (persists locally)"

    # Give async task time to complete
    await asyncio.sleep(0.5)

    # Verify capture was persisted locally
    stats = memory.get_queue_stats()
    total = (
        stats.get("pending_count", 0) +
        stats.get("sending_count", 0) +
        stats.get("sent_count", 0) +
        stats.get("failed_count", 0)
    )
    assert total > initial_total, f"Capture should be recorded: {stats}"


def test_circuit_state_in_queue_stats(phase2_env):
    """Verify circuit state is accessible alongside queue stats."""
    memory = phase2_env['memory']

    # Get both stats
    queue_stats = memory.get_queue_stats()
    circuit_stats = memory.get_circuit_state()

    # Verify both have expected keys
    assert "pending_count" in queue_stats
    assert "state" in circuit_stats
    assert "failure_count" in circuit_stats
    assert "times_opened" in circuit_stats


def test_circuit_recovery_flow(phase2_env):
    """Test circuit breaker recovery flow."""
    memory = phase2_env['memory']
    get_circuit_breaker = phase2_env['get_circuit_breaker']
    CircuitState = phase2_env['CircuitState']

    cb = get_circuit_breaker()

    for _ in range(3):
        cb.record_failure()

    assert cb.state == CircuitState.OPEN
    assert memory.is_circuit_open() is True

    # Wait for recovery timeout
    time.sleep(1.1)

    # Circuit should be half-open
    assert cb.state == CircuitState.HALF_OPEN

    # Record success to close circuit
    cb.record_success()
    assert cb.state == CircuitState.CLOSED
    assert memory.is_circuit_open() is False


@pytest.mark.asyncio
async def test_send_capture_respects_circuit(phase2_env):
    """Verify send_capture_to_worker respects circuit breaker."""
    memory = phase2_env['memory']
    capture_store = phase2_env['capture_store']
    get_circuit_breaker = phase2_env['get_circuit_breaker']
    CircuitState = phase2_env['CircuitState']

    cb = get_circuit_breaker()

    for _ in range(3):
        cb.record_failure()

    assert cb.state == CircuitState.OPEN

    # Try to send a capture - should fail immediately (circuit open)
    capture = capture_store.PendingCapture(
        id=999,
        session_id="test-blocked",
        user_message="Test",
        assistant_response="Test",
        channel="test",
        created_at=0,
        status="pending",
        retries=0,
        last_error=None,
        sent_at=None
    )

    result = await memory.send_capture_to_worker(capture)
    assert result is False, "Send should fail when circuit is open"
