"""Long-Running Command Feedback - For tasks that take >3 seconds.

Provides intermediate acknowledgement messages to let users know Peter is working.
Based on RESPONSE.md Section 8.
"""

import re
import asyncio
from dataclasses import dataclass
from typing import Optional, Callable, Any
from enum import Enum


class TaskType(Enum):
    """Types of long-running tasks for appropriate ack messages."""
    BRAVE_WEB_SEARCH = 'brave_web_search'
    BRAVE_NEWS_SEARCH = 'brave_news_search'
    BRAVE_IMAGE_SEARCH = 'brave_image_search'
    BRAVE_LOCAL_SEARCH = 'brave_local_search'
    BUILD_TASK = 'build_task'
    FILE_OPERATION = 'file_operation'
    MULTI_STEP = 'multi_step'
    CALENDAR = 'calendar'
    EMAIL = 'email'
    RESEARCH = 'research'
    DEFAULT = 'default'


@dataclass
class LongRunningConfig:
    """Configuration for long-running task feedback (Section 8.2)."""
    ack_delay_ms: int = 3000       # Send "thinking" after 3s
    progress_interval_ms: int = 30000  # Update every 30s
    max_wait_ms: int = 600000      # Timeout after 10 min


# Acknowledgement templates (Section 8.3)
ACK_TEMPLATES = {
    TaskType.BRAVE_WEB_SEARCH: '🔍 Searching the web...',
    TaskType.BRAVE_NEWS_SEARCH: '📰 Checking the latest news...',
    TaskType.BRAVE_IMAGE_SEARCH: '🖼️ Looking for images...',
    TaskType.BRAVE_LOCAL_SEARCH: '📍 Finding local results...',
    TaskType.BUILD_TASK: '⚙️ Working on that...',
    TaskType.FILE_OPERATION: '📂 Updating files...',
    TaskType.MULTI_STEP: '🧠 Thinking through this — might take a moment...',
    TaskType.CALENDAR: '📅 Checking your calendar...',
    TaskType.EMAIL: '📧 Looking at your emails...',
    TaskType.RESEARCH: '🔎 Researching this...',
    TaskType.DEFAULT: '💭 Working on it...',
}


def detect_task_type(user_message: str) -> TaskType:
    """Detect task type from user message for appropriate ack.

    Args:
        user_message: The user's message content

    Returns:
        TaskType for ack message selection
    """
    message_lower = user_message.lower()

    # Search patterns
    search_patterns = [
        (TaskType.BRAVE_NEWS_SEARCH, ['news', 'headlines', 'latest on']),
        (TaskType.BRAVE_IMAGE_SEARCH, ['image', 'picture', 'photo', 'show me what']),
        (TaskType.BRAVE_LOCAL_SEARCH, ['near me', 'nearby', 'local', 'restaurants', 'shops']),
        (TaskType.BRAVE_WEB_SEARCH, [
            'search', 'find', 'look up', 'what is', 'who is', 'price', 'cost',
            'worth', 'ebay', 'amazon', 'weather'
        ]),
    ]

    for task_type, keywords in search_patterns:
        if any(kw in message_lower for kw in keywords):
            return task_type

    # Calendar/email patterns
    if any(kw in message_lower for kw in ['calendar', 'schedule', 'meeting', 'appointment', 'free time']):
        return TaskType.CALENDAR

    if any(kw in message_lower for kw in ['email', 'inbox', 'mail', 'send', 'reply']):
        return TaskType.EMAIL

    # File/code patterns
    if any(kw in message_lower for kw in ['create', 'write', 'update', 'edit', 'file', 'code']):
        return TaskType.FILE_OPERATION

    # Build/compile patterns
    if any(kw in message_lower for kw in ['build', 'compile', 'run', 'test', 'deploy']):
        return TaskType.BUILD_TASK

    # Research patterns (long questions)
    if len(user_message) > 100 or any(kw in message_lower for kw in ['research', 'compare', 'analyse', 'explain']):
        return TaskType.RESEARCH

    # Multi-step patterns
    if any(kw in message_lower for kw in ['and then', 'after that', 'step by step', 'plan']):
        return TaskType.MULTI_STEP

    return TaskType.DEFAULT


def get_ack_message(task_type: TaskType) -> str:
    """Get acknowledgement message for task type."""
    return ACK_TEMPLATES.get(task_type, ACK_TEMPLATES[TaskType.DEFAULT])


def get_progress_message(task_type: TaskType, elapsed_seconds: int) -> str:
    """Get progress update message."""
    base = ACK_TEMPLATES.get(task_type, ACK_TEMPLATES[TaskType.DEFAULT])

    if elapsed_seconds > 60:
        return f"{base}\n-# Still working... ({elapsed_seconds}s)"
    else:
        return f"{base}\n-# Still working..."


def get_timeout_message() -> str:
    """Get timeout message."""
    return "⚠️ This is taking longer than expected. I'll send the result when it's ready."


class FeedbackManager:
    """Manages acknowledgement and progress messages for long-running tasks.

    Usage:
        async with FeedbackManager(message, config) as feedback:
            result = await long_running_task()
        # Ack is auto-deleted, result is returned
    """

    def __init__(
        self,
        send_callback: Callable[[str], Any],
        edit_callback: Optional[Callable[[Any, str], Any]] = None,
        delete_callback: Optional[Callable[[Any], Any]] = None,
        config: Optional[LongRunningConfig] = None
    ):
        self.send = send_callback
        self.edit = edit_callback
        self.delete = delete_callback
        self.config = config or LongRunningConfig()

        self.ack_message = None
        self.ack_task = None
        self.progress_task = None
        self.start_time = None
        self.cancelled = False

    async def start(self, user_message: str):
        """Start the feedback timers."""
        self.start_time = asyncio.get_event_loop().time()
        task_type = detect_task_type(user_message)

        # Start ack timer
        self.ack_task = asyncio.create_task(
            self._send_ack_after_delay(task_type)
        )

    async def _send_ack_after_delay(self, task_type: TaskType):
        """Send acknowledgement after configured delay."""
        try:
            await asyncio.sleep(self.config.ack_delay_ms / 1000)

            if self.cancelled:
                return

            ack_text = get_ack_message(task_type)
            self.ack_message = await self.send(ack_text)

            # Start progress timer
            if self.ack_message and self.edit:
                self.progress_task = asyncio.create_task(
                    self._send_progress_updates(task_type)
                )

        except asyncio.CancelledError:
            pass

    async def _send_progress_updates(self, task_type: TaskType):
        """Send periodic progress updates."""
        try:
            while not self.cancelled:
                await asyncio.sleep(self.config.progress_interval_ms / 1000)

                if self.cancelled or not self.ack_message:
                    return

                elapsed = int(asyncio.get_event_loop().time() - self.start_time)
                progress_text = get_progress_message(task_type, elapsed)

                if self.edit:
                    await self.edit(self.ack_message, progress_text)

                # Check for timeout
                if elapsed * 1000 >= self.config.max_wait_ms:
                    if self.edit:
                        await self.edit(self.ack_message, get_timeout_message())
                    return

        except asyncio.CancelledError:
            pass

    async def complete(self):
        """Mark task as complete, clean up ack message."""
        self.cancelled = True

        # Cancel timers
        if self.ack_task and not self.ack_task.done():
            self.ack_task.cancel()

        if self.progress_task and not self.progress_task.done():
            self.progress_task.cancel()

        # Delete ack message
        if self.ack_message and self.delete:
            try:
                await self.delete(self.ack_message)
            except Exception:
                pass  # Ignore deletion errors

        self.ack_message = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.complete()


# Simple synchronous version for non-async contexts
def should_show_ack(elapsed_ms: int, config: Optional[LongRunningConfig] = None) -> bool:
    """Check if we should show an ack message based on elapsed time."""
    config = config or LongRunningConfig()
    return elapsed_ms >= config.ack_delay_ms


# =============================================================================
# TESTING
# =============================================================================

def test_feedback():
    """Run basic feedback tests."""
    # Test task type detection
    test_cases = [
        ("What's LEGO 42100 worth on eBay?", TaskType.BRAVE_WEB_SEARCH),
        ("Any news about LEGO?", TaskType.BRAVE_NEWS_SEARCH),
        ("Show me pictures of Tokyo Skytree", TaskType.BRAVE_IMAGE_SEARCH),
        ("Restaurants near me", TaskType.BRAVE_LOCAL_SEARCH),
        ("What's on my calendar?", TaskType.CALENDAR),
        ("Check my emails", TaskType.EMAIL),
        ("Create a new file", TaskType.FILE_OPERATION),
        ("Hello", TaskType.DEFAULT),
    ]

    passed = 0
    failed = 0

    for message, expected_type in test_cases:
        result = detect_task_type(message)
        if result == expected_type:
            passed += 1
            print(f"✓ PASS - '{message[:30]}...' → {result.value}")
        else:
            failed += 1
            print(f"✗ FAIL - '{message[:30]}...' → expected {expected_type.value}, got {result.value}")

    # Test ack messages exist
    for task_type in TaskType:
        ack = get_ack_message(task_type)
        if ack and len(ack) > 0:
            passed += 1
        else:
            failed += 1
            print(f"✗ FAIL - No ack message for {task_type.value}")

    print(f"\nResults: {passed} passed, {failed} failed")
    return failed == 0


if __name__ == '__main__':
    test_feedback()
