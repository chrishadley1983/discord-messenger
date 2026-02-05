"""Full End-to-End Tests - All Phases Combined.

Tests the complete reliability system:
- Phase 1: Persistent capture queue
- Phase 2: Circuit breaker
- Phase 3: Context cache & degraded mode
- Phase 4: Background processor

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
def full_e2e_env(monkeypatch):
    """Create isolated environment for full E2E tests."""
    import domains.peterbot.config as config

    # Create unique temp file
    fd, temp_path = tempfile.mkstemp(suffix="_full_e2e.db")
    os.close(fd)

    # Override config
    monkeypatch.setattr(config, 'CAPTURE_STORE_DB', temp_path)
    monkeypatch.setattr(config, 'CIRCUIT_FAILURE_THRESHOLD', 3)
    monkeypatch.setattr(config, 'CIRCUIT_RECOVERY_TIMEOUT', 2)
    monkeypatch.setattr(config, 'CAPTURE_MAX_RETRIES', 3)
    monkeypatch.setattr(config, 'CONTEXT_CACHE_MAX_ENTRIES', 10)
    monkeypatch.setattr(config, 'CONTEXT_CACHE_TTL_SECONDS', 3)
    monkeypatch.setattr(config, 'CAPTURE_PROCESSOR_MAX_PER_CYCLE', 5)
    monkeypatch.setattr(config, 'CAPTURE_PROCESSOR_DELAY_BETWEEN', 0.1)
    monkeypatch.setattr(config, 'WORKER_URL', "http://localhost:99999")
    monkeypatch.setattr(config, 'MESSAGES_ENDPOINT', "http://localhost:99999/api/sessions/messages")
    monkeypatch.setattr(config, 'CONTEXT_ENDPOINT', "http://localhost:99999/api/context/inject")

    # Delete peterbot submodules EXCEPT config to ensure clean state
    # while keeping the monkeypatched config
    for mod in list(sys.modules.keys()):
        if 'domains.peterbot' in mod and 'config' not in mod:
            del sys.modules[mod]

    # Now reimport - modules get fresh global state but use patched config
    from domains.peterbot import capture_store
    from domains.peterbot import memory
    from domains.peterbot import circuit_breaker as cb_module
    from domains.peterbot.circuit_breaker import (
        get_circuit_breaker,
        reset_circuit_breaker,
        CircuitState,
    )

    # Reset
    capture_store.close()
    capture_store._connection = None

    # Ensure circuit breaker global is None, then create fresh one
    cb_module._worker_circuit_breaker = None
    reset_circuit_breaker()
    cb = get_circuit_breaker()
    cb.force_close()  # Ensure CLOSED state

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


@pytest.mark.asyncio
async def test_e2e_capture_persists_during_outage(full_e2e_env):
    """E2E: Captures persist locally when worker is down."""
    memory = full_e2e_env['memory']

    # Capture multiple messages
    for i in range(5):
        result = await memory.capture_message_pair(
            session_id=f"e2e-outage-{i}",
            user_message=f"E2E test message {i}",
            assistant_response=f"E2E test response {i}",
            channel="e2e-test"
        )
        assert result is True, f"Capture {i} should succeed"

    # Wait for async sends to complete
    await asyncio.sleep(1)

    # Check queue stats
    stats = memory.get_queue_stats()
    total = stats["pending_count"] + stats["sending_count"] + stats["failed_count"]
    assert total >= 5, f"Should have at least 5 captures in queue: {stats}"


@pytest.mark.asyncio
async def test_e2e_circuit_breaker_opens_on_failures(full_e2e_env):
    """E2E: Circuit opens after consecutive failures."""
    memory = full_e2e_env['memory']
    config = full_e2e_env['config']
    get_circuit_breaker = full_e2e_env['get_circuit_breaker']
    reset_circuit_breaker = full_e2e_env['reset_circuit_breaker']
    CircuitState = full_e2e_env['CircuitState']

    # Reset circuit
    reset_circuit_breaker()
    cb = get_circuit_breaker()

    assert cb.state == CircuitState.CLOSED, "Should start closed"

    # Simulate failures by fetching context (will fail due to unreachable worker)
    for i in range(config.CIRCUIT_FAILURE_THRESHOLD):
        context, is_degraded = await memory.get_memory_context(f"test query {i}")

    # Circuit should be open now
    assert cb.state == CircuitState.OPEN, f"Circuit should be OPEN after failures, got {cb.state}"


@pytest.mark.asyncio
async def test_e2e_degraded_mode_uses_cache(full_e2e_env):
    """E2E: Degraded mode returns cached context when available."""
    capture_store = full_e2e_env['capture_store']
    memory = full_e2e_env['memory']
    config = full_e2e_env['config']
    get_circuit_breaker = full_e2e_env['get_circuit_breaker']
    reset_circuit_breaker = full_e2e_env['reset_circuit_breaker']
    CircuitState = full_e2e_env['CircuitState']

    # Reset circuit
    reset_circuit_breaker()

    # Pre-populate cache
    query = "What did I do yesterday?"
    cached_context = "You worked on the peterbot reliability system."
    capture_store.set_cached_context(query, cached_context)

    # Open circuit
    cb = get_circuit_breaker()
    for _ in range(config.CIRCUIT_FAILURE_THRESHOLD):
        cb.record_failure()

    assert cb.state == CircuitState.OPEN

    # Fetch context - should use cache
    context, is_degraded = await memory.get_memory_context(query)

    assert is_degraded is True, "Should be in degraded mode"
    assert cached_context in context, f"Should return cached context, got: {context[:100]}"


@pytest.mark.asyncio
async def test_e2e_degraded_mode_notice_when_no_cache(full_e2e_env):
    """E2E: Degraded mode returns notice when no cache available."""
    memory = full_e2e_env['memory']
    config = full_e2e_env['config']
    get_circuit_breaker = full_e2e_env['get_circuit_breaker']
    reset_circuit_breaker = full_e2e_env['reset_circuit_breaker']
    CircuitState = full_e2e_env['CircuitState']

    # Reset and open circuit
    reset_circuit_breaker()
    cb = get_circuit_breaker()
    for _ in range(config.CIRCUIT_FAILURE_THRESHOLD):
        cb.record_failure()

    # Fetch context for uncached query
    context, is_degraded = await memory.get_memory_context("random_uncached_query_xyz")

    assert is_degraded is True, "Should be in degraded mode"
    assert "MEMORY SYSTEM UNAVAILABLE" in context


@pytest.mark.asyncio
async def test_e2e_circuit_recovery(full_e2e_env):
    """E2E: Circuit recovers after timeout."""
    config = full_e2e_env['config']
    get_circuit_breaker = full_e2e_env['get_circuit_breaker']
    reset_circuit_breaker = full_e2e_env['reset_circuit_breaker']
    CircuitState = full_e2e_env['CircuitState']

    # Reset and open circuit
    reset_circuit_breaker()
    cb = get_circuit_breaker()
    for _ in range(config.CIRCUIT_FAILURE_THRESHOLD):
        cb.record_failure()

    assert cb.state == CircuitState.OPEN

    # Wait for recovery timeout
    await asyncio.sleep(config.CIRCUIT_RECOVERY_TIMEOUT + 0.5)

    # Should transition to half-open
    assert cb.state == CircuitState.HALF_OPEN, f"Should be HALF_OPEN, got {cb.state}"

    # Record success
    cb.record_success()

    # Should close
    assert cb.state == CircuitState.CLOSED, f"Should be CLOSED after success, got {cb.state}"
