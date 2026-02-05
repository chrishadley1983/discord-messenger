"""Tests for context cache functionality (Phase 3).

Tests caching, retrieval, expiration, cleanup, and degraded mode behavior.
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
def isolated_cache_env(monkeypatch):
    """Create isolated environment for cache tests."""
    import domains.peterbot.config as config

    # Create unique temp file
    fd, temp_path = tempfile.mkstemp(suffix="_cache_test.db")
    os.close(fd)

    # Override config
    monkeypatch.setattr(config, 'CAPTURE_STORE_DB', temp_path)
    monkeypatch.setattr(config, 'CIRCUIT_FAILURE_THRESHOLD', 3)
    monkeypatch.setattr(config, 'CIRCUIT_RECOVERY_TIMEOUT', 60)  # Long timeout to prevent auto-transition
    monkeypatch.setattr(config, 'CONTEXT_CACHE_MAX_ENTRIES', 5)
    monkeypatch.setattr(config, 'CONTEXT_CACHE_TTL_SECONDS', 2)
    monkeypatch.setattr(config, 'WORKER_URL', "http://localhost:99999")

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

    # Reset connection
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


def test_cache_set_and_get(isolated_cache_env):
    """Test basic cache set and get operations."""
    capture_store = isolated_cache_env['capture_store']

    query = "What did I eat yesterday?"
    context = "You ate pizza for dinner and had cereal for breakfast."

    # Set cache
    capture_store.set_cached_context(query, context)

    # Get cache (should hit)
    cached = capture_store.get_cached_context(query)
    assert cached is not None, "Cache should return value"
    assert cached.context == context


def test_cache_miss(isolated_cache_env):
    """Test cache miss for unknown query."""
    capture_store = isolated_cache_env['capture_store']

    cached = capture_store.get_cached_context("some random query that was never cached")
    assert cached is None, "Should return None for cache miss"


def test_cache_expiration(isolated_cache_env):
    """Test that cached entries expire after TTL."""
    capture_store = isolated_cache_env['capture_store']
    config = isolated_cache_env['config']

    query = "What time did I wake up?"
    context = "You woke up at 7:30 AM."

    # Set cache
    capture_store.set_cached_context(query, context)

    # Should hit immediately
    cached = capture_store.get_cached_context(query)
    assert cached is not None, "Should hit before TTL"

    # Wait for TTL to expire
    time.sleep(config.CONTEXT_CACHE_TTL_SECONDS + 0.5)

    # Should miss after TTL
    cached = capture_store.get_cached_context(query)
    assert cached is None, "Should miss after TTL"


def test_cache_stale_retrieval(isolated_cache_env):
    """Test that stale cache can be retrieved during outages."""
    capture_store = isolated_cache_env['capture_store']
    config = isolated_cache_env['config']

    query = "What's my daily calorie target?"
    context = "Your daily calorie target is 2000 kcal."

    # Set cache
    capture_store.set_cached_context(query, context)

    # Wait for TTL to expire
    time.sleep(config.CONTEXT_CACHE_TTL_SECONDS + 0.5)

    # Normal get should miss
    cached = capture_store.get_cached_context(query)
    assert cached is None, "Normal get should miss after TTL"

    # Stale get should still work
    stale = capture_store.get_cached_context_stale(query)
    assert stale is not None, "Stale get should work after TTL"
    assert stale.context == context


def test_cache_stats(isolated_cache_env):
    """Test cache statistics."""
    capture_store = isolated_cache_env['capture_store']
    config = isolated_cache_env['config']

    # Add some entries
    for i in range(3):
        capture_store.set_cached_context(f"stats_query_{i}", f"stats_context_{i}")

    stats = capture_store.get_cache_stats()

    assert "entry_count" in stats
    assert "oldest_entry_age" in stats
    assert "newest_entry_age" in stats
    assert "max_entries" in stats
    assert "ttl_seconds" in stats

    assert stats["entry_count"] == 3
    assert stats["max_entries"] == config.CONTEXT_CACHE_MAX_ENTRIES
    assert stats["ttl_seconds"] == config.CONTEXT_CACHE_TTL_SECONDS


@pytest.mark.asyncio
async def test_degraded_mode_with_cache(isolated_cache_env):
    """Test that degraded mode returns cached context when available."""
    capture_store = isolated_cache_env['capture_store']
    memory = isolated_cache_env['memory']
    config = isolated_cache_env['config']
    get_circuit_breaker = isolated_cache_env['get_circuit_breaker']
    reset_circuit_breaker = isolated_cache_env['reset_circuit_breaker']
    CircuitState = isolated_cache_env['CircuitState']

    # Reset circuit breaker
    reset_circuit_breaker()
    cb = get_circuit_breaker()

    query = "What meetings do I have today?"
    context = "You have a team standup at 10am and a 1:1 at 2pm."

    # Pre-populate cache
    capture_store.set_cached_context(query, context)

    # Open circuit
    for _ in range(config.CIRCUIT_FAILURE_THRESHOLD):
        cb.record_failure()

    assert cb.state == CircuitState.OPEN

    # Fetch context - should use cache
    result_context, is_degraded = await memory.get_memory_context(query)

    assert is_degraded is True, "Should be in degraded mode"
    assert context in result_context or result_context == context


@pytest.mark.asyncio
async def test_degraded_mode_without_cache(isolated_cache_env):
    """Test that degraded mode returns notice when no cache available."""
    memory = isolated_cache_env['memory']
    config = isolated_cache_env['config']
    get_circuit_breaker = isolated_cache_env['get_circuit_breaker']
    reset_circuit_breaker = isolated_cache_env['reset_circuit_breaker']
    CircuitState = isolated_cache_env['CircuitState']

    # Reset circuit breaker
    reset_circuit_breaker()
    cb = get_circuit_breaker()

    # Open circuit
    for _ in range(config.CIRCUIT_FAILURE_THRESHOLD):
        cb.record_failure()

    assert cb.state == CircuitState.OPEN

    # Fetch with uncached query
    result_context, is_degraded = await memory.get_memory_context(
        "completely_unique_never_cached_query_12345"
    )

    assert is_degraded is True, "Should be in degraded mode"
    assert "MEMORY SYSTEM UNAVAILABLE" in result_context


def test_hash_consistency(isolated_cache_env):
    """Test that query hashing is consistent."""
    capture_store = isolated_cache_env['capture_store']

    query = "What's the weather today?"

    # Hash should be consistent
    hash1 = capture_store._hash_query(query)
    hash2 = capture_store._hash_query(query)

    assert hash1 == hash2, "Same query should produce same hash"
    assert len(hash1) == 32, f"Hash should be 32 chars, got {len(hash1)}"

    # Different queries should produce different hashes
    hash3 = capture_store._hash_query("Different query")
    assert hash1 != hash3, "Different queries should produce different hashes"
