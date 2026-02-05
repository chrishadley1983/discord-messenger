"""Tests for the refactored memory capture module."""

import asyncio
import os
import sys
import tempfile

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Override config before importing
import domains.peterbot.config as config

# Use temp database for testing - create unique path
_temp_db = tempfile.mktemp(suffix="_capture_test.db")
config.CAPTURE_STORE_DB = _temp_db
config.CAPTURE_MAX_RETRIES = 3

# Mock the worker endpoint to fail (no actual worker running)
config.MESSAGES_ENDPOINT = "http://localhost:99999/api/sessions/messages"

# Import modules AFTER config is set
from domains.peterbot import capture_store
from domains.peterbot import memory

# Force close any cached connection and reset
capture_store.close()
capture_store._connection = None


def test_capture_persists_locally():
    """Test that captures are persisted to local DB even when worker is down."""
    print("Test: capture_persists_locally...")

    # Check stats before
    stats_before = capture_store.get_queue_stats()
    print(f"  Stats BEFORE: {stats_before}")

    async def run_test():
        # Capture a message (worker is unreachable)
        result = await memory.capture_message_pair(
            session_id="test-session-1",
            user_message="Hello, test message",
            assistant_response="Hello, test response",
            channel="test-channel"
        )

        # Should return True because it's persisted locally
        assert result is True, "capture_message_pair should return True"

        # Give the background task a moment to attempt send and fail
        await asyncio.sleep(1.0)

        # Check local store
        stats = capture_store.get_queue_stats()
        print(f"  Stats AFTER: {stats}")

        # We should have exactly 1 more capture than before
        # It should be pending (failed immediate send, returned to pending for retry)
        # or failed (if max retries exceeded - shouldn't happen on first try)
        total_before = stats_before["pending_count"] + stats_before["failed_count"]
        total_after = stats["pending_count"] + stats["failed_count"]

        # The capture should exist in pending or failed state
        assert total_after >= total_before + 1 or stats["sending_count"] >= 1, \
            f"Should have at least 1 more capture. Before: {stats_before}, After: {stats}"

    asyncio.run(run_test())
    print("  PASSED")


def test_empty_messages_skipped():
    """Test that empty messages are not captured."""
    print("Test: empty_messages_skipped...")

    async def run_test():
        # Initial stats
        stats_before = capture_store.get_queue_stats()
        total_before = sum(stats_before.values()) - stats_before["oldest_pending_age"]

        # Try to capture empty message
        result = await memory.capture_message_pair(
            session_id="test-empty",
            user_message="",
            assistant_response="Response"
        )

        # Should return True (skipped, not an error)
        assert result is True

        # Try to capture empty response
        result = await memory.capture_message_pair(
            session_id="test-empty",
            user_message="Message",
            assistant_response="   "  # whitespace only
        )

        assert result is True

        # Stats should not increase
        stats_after = capture_store.get_queue_stats()
        total_after = sum(stats_after.values()) - stats_after["oldest_pending_age"]
        assert total_after == total_before, "Empty messages should not create captures"

    asyncio.run(run_test())
    print("  PASSED")


def test_buffer_operations():
    """Test conversation buffer operations."""
    print("Test: buffer_operations...")

    channel_id = 12345

    # Initially empty
    assert memory.is_buffer_empty(channel_id)

    # Add messages
    memory.add_to_buffer("user", "Hello", channel_id)
    memory.add_to_buffer("assistant", "Hi there!", channel_id)

    # No longer empty
    assert not memory.is_buffer_empty(channel_id)

    # Get context
    context = memory.get_recent_context(channel_id)
    assert "Hello" in context
    assert "Hi there!" in context
    assert "User" in context
    assert "Assistant" in context

    print("  PASSED")


def test_build_full_context():
    """Test context building."""
    print("Test: build_full_context...")

    channel_id = 99999
    memory.add_to_buffer("user", "Previous message", channel_id)
    memory.add_to_buffer("assistant", "Previous response", channel_id)

    context = memory.build_full_context(
        message="Current message",
        memory_context="Some memory context here",
        channel_id=channel_id,
        channel_name="#test-channel",
        knowledge_context="Knowledge context",
        skill_context="Skill context"
    )

    # Should contain all sections
    assert "CHANNEL CONTEXT" in context
    assert "#test-channel" in context
    assert "Memory Context" in context
    assert "Some memory context here" in context
    assert "Knowledge context" in context
    assert "Skill context" in context
    assert "Recent Conversation" in context
    assert "Previous message" in context
    assert "Current Message" in context
    assert "Current message" in context

    print("  PASSED")


def test_get_queue_stats():
    """Test queue statistics function."""
    print("Test: get_queue_stats...")

    stats = memory.get_queue_stats()

    assert "pending_count" in stats
    assert "sent_count" in stats
    assert "failed_count" in stats
    assert "oldest_pending_age" in stats

    print(f"  Stats: {stats}")
    print("  PASSED")


def test_start_retry_task():
    """Test that start_retry_task doesn't crash (legacy compat)."""
    print("Test: start_retry_task...")

    # Should not raise an exception
    memory.start_retry_task()

    print("  PASSED")


def cleanup_test_db():
    """Remove test database."""
    capture_store.close()
    try:
        os.unlink(_temp_db)
        for suffix in ["-wal", "-shm"]:
            try:
                os.unlink(_temp_db + suffix)
            except FileNotFoundError:
                pass
    except Exception as e:
        print(f"  Warning: Could not delete test DB: {e}")


def main():
    print("=" * 60)
    print("Memory Capture Tests")
    print("=" * 60)
    print(f"Using temp database: {_temp_db}")
    print()

    try:
        test_buffer_operations()
        test_build_full_context()
        test_empty_messages_skipped()
        test_capture_persists_locally()
        test_get_queue_stats()
        test_start_retry_task()

        print()
        print("=" * 60)
        print("ALL TESTS PASSED")
        print("=" * 60)

    finally:
        cleanup_test_db()


if __name__ == "__main__":
    main()
