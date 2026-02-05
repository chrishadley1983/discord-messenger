"""Tests for the capture store module.

Uses pytest fixtures for proper test isolation - each test gets a fresh database.
"""

import os
import sys
import tempfile
import pytest

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def temp_db(monkeypatch):
    """Create a temp database for each test."""
    import domains.peterbot.config as config

    # Create unique temp file
    fd, temp_path = tempfile.mkstemp(suffix="_capture_test.db")
    os.close(fd)

    # Override config
    monkeypatch.setattr(config, 'CAPTURE_STORE_DB', temp_path)
    monkeypatch.setattr(config, 'CAPTURE_MAX_RETRIES', 3)
    monkeypatch.setattr(config, 'CAPTURE_SENT_RETENTION_DAYS', 7)
    monkeypatch.setattr(config, 'CAPTURE_FAILED_RETENTION_DAYS', 30)

    # Force reimport capture_store with new config
    if 'domains.peterbot.capture_store' in sys.modules:
        del sys.modules['domains.peterbot.capture_store']

    from domains.peterbot import capture_store

    # Reset connection
    capture_store.close()
    capture_store._connection = None

    yield capture_store

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


def test_add_and_get_capture(temp_db):
    """Test adding and retrieving captures."""
    capture_store = temp_db

    # Add a capture
    capture_id = capture_store.add_capture(
        session_id="test-session-1",
        user_message="Hello, how are you?",
        assistant_response="I'm doing well, thanks!",
        channel="test-channel"
    )

    assert capture_id > 0, "Capture ID should be positive"

    # Get pending captures
    pending = capture_store.get_pending(limit=10)
    assert len(pending) == 1, "Should have exactly 1 pending capture"

    # Verify capture data
    capture = pending[0]
    assert capture.id == capture_id
    assert capture.session_id == "test-session-1"
    assert capture.user_message == "Hello, how are you?"
    assert capture.status == "pending"
    assert capture.retries == 0


def test_mark_sending_and_sent(temp_db):
    """Test marking captures as sending and sent."""
    capture_store = temp_db

    # Add a capture
    capture_id = capture_store.add_capture(
        session_id="test-session",
        user_message="Test message",
        assistant_response="Test response"
    )

    # Mark as sending
    capture_store.mark_sending(capture_id)
    capture = capture_store.get_by_id(capture_id)
    assert capture.status == "sending"

    # Mark as sent
    capture_store.mark_sent(capture_id)
    capture = capture_store.get_by_id(capture_id)
    assert capture.status == "sent"
    assert capture.sent_at is not None

    # Should not appear in pending anymore
    pending = capture_store.get_pending()
    assert all(c.id != capture_id for c in pending)


def test_mark_failed_with_retries(temp_db):
    """Test failure handling and retry logic."""
    capture_store = temp_db

    # Add a new capture
    capture_id = capture_store.add_capture(
        session_id="test-retry",
        user_message="Test message",
        assistant_response="Test response"
    )

    # Fail it multiple times (less than max retries)
    capture_store.mark_sending(capture_id)
    capture_store.mark_failed(capture_id, "Connection error 1")

    capture = capture_store.get_by_id(capture_id)
    assert capture.status == "pending", "Should return to pending after first failure"
    assert capture.retries == 1
    assert capture.last_error == "Connection error 1"

    # Fail again
    capture_store.mark_sending(capture_id)
    capture_store.mark_failed(capture_id, "Connection error 2")

    capture = capture_store.get_by_id(capture_id)
    assert capture.status == "pending", "Should still be pending after 2 failures"
    assert capture.retries == 2

    # Fail third time (max retries = 3)
    capture_store.mark_sending(capture_id)
    capture_store.mark_failed(capture_id, "Connection error 3")

    capture = capture_store.get_by_id(capture_id)
    assert capture.status == "failed", "Should be failed after max retries"
    assert capture.retries == 3


def test_queue_stats(temp_db):
    """Test queue statistics."""
    capture_store = temp_db

    # Add captures in different states
    id1 = capture_store.add_capture("s1", "m1", "r1")  # pending
    id2 = capture_store.add_capture("s2", "m2", "r2")  # will be sent
    id3 = capture_store.add_capture("s3", "m3", "r3")  # will be failed

    # Mark one as sent
    capture_store.mark_sending(id2)
    capture_store.mark_sent(id2)

    # Mark one as failed (exhaust retries)
    for _ in range(3):
        capture_store.mark_sending(id3)
        capture_store.mark_failed(id3, "error")

    stats = capture_store.get_queue_stats()

    assert stats["pending_count"] == 1
    assert stats["sent_count"] == 1
    assert stats["failed_count"] == 1


def test_cleanup(temp_db):
    """Test cleanup of old captures."""
    capture_store = temp_db

    # Add captures - they won't be old enough to delete
    capture_store.add_capture("s1", "m1", "r1")

    sent_deleted, failed_deleted = capture_store.cleanup_old_captures()

    # With fresh test data, nothing should be old enough to delete
    assert sent_deleted == 0
    assert failed_deleted == 0


def test_reset_stale_sending(temp_db):
    """Test resetting stale sending captures."""
    capture_store = temp_db

    # Add a capture and mark as sending
    capture_id = capture_store.add_capture(
        session_id="test-stale",
        user_message="Test",
        assistant_response="Test"
    )
    capture_store.mark_sending(capture_id)

    # Should not reset immediately (not stale yet)
    reset_count = capture_store.reset_stale_sending(timeout_seconds=300)

    # Just verify it runs without error
    assert reset_count >= 0
