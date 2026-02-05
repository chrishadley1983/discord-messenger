"""End-to-end tests for Phase 1: Reliable Memory Capture.

Tests the full flow from capture_message_pair() through to local persistence,
including worker outage scenarios.

Uses pytest fixtures for proper test isolation.
"""

import asyncio
import os
import sys
import tempfile
import pytest

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def isolated_capture_env(monkeypatch):
    """Create isolated environment for capture tests."""
    import domains.peterbot.config as config

    # Create unique temp file
    fd, temp_path = tempfile.mkstemp(suffix="_e2e_test.db")
    os.close(fd)

    # Override config
    monkeypatch.setattr(config, 'CAPTURE_STORE_DB', temp_path)
    monkeypatch.setattr(config, 'CAPTURE_MAX_RETRIES', 3)
    monkeypatch.setattr(config, 'MESSAGES_ENDPOINT', "http://localhost:99999/api/sessions/messages")

    # Force reimport modules with new config
    for mod in list(sys.modules.keys()):
        if 'capture_store' in mod or 'memory' in mod:
            if 'domains.peterbot' in mod:
                del sys.modules[mod]

    from domains.peterbot import capture_store
    from domains.peterbot import memory

    # Reset connection
    capture_store.close()
    capture_store._connection = None

    yield {
        'capture_store': capture_store,
        'memory': memory,
        'config': config,
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
async def test_e2e_capture_persists_during_outage(isolated_capture_env):
    """Test that captures are persisted locally when worker is unreachable."""
    capture_store = isolated_capture_env['capture_store']
    memory = isolated_capture_env['memory']

    # Verify clean state
    stats = capture_store.get_queue_stats()
    assert stats["pending_count"] == 0, "Should start with empty queue"

    # Simulate 5 conversation pairs during worker outage
    for i in range(5):
        result = await memory.capture_message_pair(
            session_id=f"e2e-test-{i}",
            user_message=f"User message {i}",
            assistant_response=f"Assistant response {i}",
            channel="e2e-test"
        )
        assert result is True, f"Capture {i} should return True"

    # Wait for async tasks to attempt sends and fail
    await asyncio.sleep(2)

    # Verify all 5 are in local store
    stats = capture_store.get_queue_stats()

    # All should be pending (worker unreachable, returned to pending after fail)
    assert stats["pending_count"] == 5, f"All 5 captures should be pending, got {stats}"
    assert stats["sent_count"] == 0, "None should be sent (worker unreachable)"


@pytest.mark.asyncio
async def test_e2e_retry_mechanics(isolated_capture_env):
    """Test that retries work correctly."""
    capture_store = isolated_capture_env['capture_store']
    config = isolated_capture_env['config']

    # Add a capture
    capture_id = capture_store.add_capture(
        session_id="e2e-retry-test",
        user_message="Test message",
        assistant_response="Test response"
    )

    # Simulate failures up to max retries
    for i in range(config.CAPTURE_MAX_RETRIES):
        capture_store.mark_sending(capture_id)
        capture_store.mark_failed(capture_id, f"Test error {i+1}")

        updated = capture_store.get_by_id(capture_id)
        if i < config.CAPTURE_MAX_RETRIES - 1:
            assert updated.status == "pending"
        else:
            assert updated.status == "failed"

    # After max retries, should be failed
    final = capture_store.get_by_id(capture_id)
    assert final.status == "failed"


def test_e2e_queue_stats(isolated_capture_env):
    """Test queue statistics reporting."""
    capture_store = isolated_capture_env['capture_store']
    config = isolated_capture_env['config']

    # Add specific captures
    id1 = capture_store.add_capture("s1", "m1", "r1")  # pending
    id2 = capture_store.add_capture("s2", "m2", "r2")  # will send
    id3 = capture_store.add_capture("s3", "m3", "r3")  # will fail

    # Mark one sent
    capture_store.mark_sending(id2)
    capture_store.mark_sent(id2)

    # Fail one past retries
    for _ in range(config.CAPTURE_MAX_RETRIES):
        capture_store.mark_sending(id3)
        capture_store.mark_failed(id3, "error")

    stats = capture_store.get_queue_stats()

    # Should have exactly: 1 pending, 1 sent, 1 failed
    assert stats["pending_count"] == 1
    assert stats["sent_count"] == 1
    assert stats["failed_count"] == 1


def test_e2e_successful_send_simulation(isolated_capture_env):
    """Simulate what happens when a capture is successfully sent."""
    capture_store = isolated_capture_env['capture_store']

    # Add a new capture
    capture_id = capture_store.add_capture(
        session_id="e2e-success-test",
        user_message="Success test message",
        assistant_response="Success test response"
    )

    # Simulate successful send
    capture_store.mark_sending(capture_id)
    capture_store.mark_sent(capture_id)

    # Verify
    capture = capture_store.get_by_id(capture_id)
    assert capture.status == "sent"
    assert capture.sent_at is not None

    # Should not appear in pending
    pending = capture_store.get_pending()
    assert all(c.id != capture_id for c in pending)


def test_e2e_multiple_captures_ordering(isolated_capture_env):
    """Test that captures maintain proper ordering."""
    capture_store = isolated_capture_env['capture_store']

    # Add captures in order
    ids = []
    for i in range(5):
        capture_id = capture_store.add_capture(
            session_id=f"order-test-{i}",
            user_message=f"Message {i}",
            assistant_response=f"Response {i}"
        )
        ids.append(capture_id)

    # Get pending - should be in order
    pending = capture_store.get_pending(limit=10)
    pending_ids = [c.id for c in pending]

    assert pending_ids == ids, "Captures should maintain insertion order"
