"""Peterbot message routing with memory context injection.

Routes peterbot messages through Claude Code (tmux) with memory context,
unlike the dumb tunnel used by claude-code channel.
"""

import asyncio
import re
import subprocess
import sys
from typing import Optional

from . import memory

# Windows: hide console window when running WSL commands
IS_WINDOWS = sys.platform == "win32"
if IS_WINDOWS:
    STARTUPINFO = subprocess.STARTUPINFO()
    STARTUPINFO.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    STARTUPINFO.wShowWindow = subprocess.SW_HIDE
    CREATE_NO_WINDOW = subprocess.CREATE_NO_WINDOW
else:
    STARTUPINFO = None
    CREATE_NO_WINDOW = 0

# Lock to prevent concurrent access to the Claude Code session
# Shared between conversation handling (handle_message) and scheduled jobs (scheduler.py)
_session_lock = asyncio.Lock()

# Track last channel for context isolation (clear on channel switch)
_last_channel_id: int | None = None

# Track current task for "busy" messages
_current_task: dict | None = None  # {"channel": str, "task": str, "started": float}

from .config import (
    PETERBOT_SESSION,
    PETERBOT_SESSION_PATH,
    RESPONSE_TIMEOUT,
    POLL_INTERVAL,
    STABLE_COUNT_THRESHOLD,
    INTERIM_UPDATE_DELAY,
    INTERIM_UPDATE_INTERVAL,
    CONTEXT_FILE,
    RAW_LOG_PATH,
    CHANNEL_ID_TO_NAME,
)
from typing import Callable, Awaitable

# Spinner characters that appear at start of line when Claude is thinking
# These animated spinners indicate Claude Code is processing
# NOTE: ⏵ removed - it appears in the status line "⏵⏵ bypass permissions"
# NOTE: ↓↑ removed - they appear in status line "↓ to view"
SPINNER_CHARS = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏', '✻']
from .parser import extract_new_response  # New robust parser
from domains.claude_code.tools import (
    _tmux,
    get_sessions,
    strip_ansi,
)
# Note: We don't import start_session - peterbot uses its own headless version
from logger import logger


def create_headless_session() -> str:
    """Create peterbot tmux session without opening Windows Terminal.

    Unlike the shared start_session in claude_code.tools, this runs
    completely headless - no terminal window, no hooks triggering.

    Returns:
        Status message (success or error)
    """
    # Check if path exists in WSL
    check = subprocess.run(
        ["wsl", "test", "-d", PETERBOT_SESSION_PATH],
        capture_output=True,
        startupinfo=STARTUPINFO,
        creationflags=CREATE_NO_WINDOW
    )
    if check.returncode != 0:
        return f"Directory not found: {PETERBOT_SESSION_PATH}"

    # Check if session already exists
    if PETERBOT_SESSION in get_sessions():
        return "Session already exists"

    # Create tmux session (headless - no Windows Terminal)
    result = _tmux("new-session", "-d", "-s", PETERBOT_SESSION, "-c", PETERBOT_SESSION_PATH)
    if result.returncode != 0:
        return f"Failed to create session: {result.stderr}"

    # Start claude in the session with auto-approve permissions
    _tmux("send-keys", "-t", PETERBOT_SESSION, "claude --permission-mode dontAsk", "Enter")

    return "Started"


async def ensure_session() -> tuple[bool, str]:
    """Ensure dedicated peterbot session exists, create if needed.

    Uses headless session creation (no Windows Terminal window).

    Returns:
        Tuple of (success, error_message). error_message is empty on success.
    """
    sessions = get_sessions()
    logger.info(f"Current sessions: {sessions}, looking for: {PETERBOT_SESSION}")

    if PETERBOT_SESSION not in sessions:
        logger.info(f"Creating headless session with path: {PETERBOT_SESSION_PATH}")
        result = create_headless_session()
        logger.info(f"Peterbot session creation result: {result}")

        if "Started" in result:
            # Wait for Claude Code to initialize before sending first prompt
            logger.info("Waiting for Claude Code to initialize...")
            await asyncio.sleep(8)
            return True, ""
        elif "already exists" in result:
            return True, ""
        else:
            # Return the actual error for debugging
            return False, result
    return True, ""


def send_to_session(prompt: str) -> None:
    """Send prompt to dedicated peterbot session."""
    import time
    _tmux("send-keys", "-t", PETERBOT_SESSION, "-l", prompt)
    time.sleep(0.2)  # Small delay to ensure text is fully sent before Enter
    _tmux("send-keys", "-t", PETERBOT_SESSION, "Enter")


def generate_context_filename(operation_id: str) -> str:
    """Generate a unique context filepath for an operation.

    Args:
        operation_id: Unique identifier for this operation (e.g., uuid hex)

    Returns:
        Full WSL path for the context file
    """
    return f"{PETERBOT_SESSION_PATH}/context_{operation_id}.md"


def write_context_file(content: str, filepath: str = None) -> str:
    """Write context to file in WSL for Claude Code to read.

    Args:
        content: Full context string to write
        filepath: Optional custom filepath. Uses CONTEXT_FILE if not specified.

    Returns:
        The filepath written to, or empty string on failure
    """
    target_path = filepath or CONTEXT_FILE

    # Write via WSL bash - escape content properly
    # Use base64 to avoid escaping issues with special characters
    import base64
    encoded = base64.b64encode(content.encode('utf-8')).decode('ascii')

    cmd = f"echo '{encoded}' | base64 -d > '{target_path}'"

    try:
        result = subprocess.run(
            ["wsl", "bash", "-c", cmd],
            capture_output=True,
            text=True,
            startupinfo=STARTUPINFO,
            creationflags=CREATE_NO_WINDOW
        )
        if result.returncode != 0:
            logger.error(f"Failed to write context file: {result.stderr}")
            return ""
        return target_path
    except Exception as e:
        logger.error(f"Error writing context file: {e}")
        return ""


def cleanup_context_file(filepath: str) -> bool:
    """Remove a context file from WSL filesystem.

    Args:
        filepath: Full WSL path to the context file

    Returns:
        True if successful or file doesn't exist, False on error
    """
    cmd = f"rm -f '{filepath}'"

    try:
        result = subprocess.run(
            ["wsl", "bash", "-c", cmd],
            capture_output=True,
            text=True,
            startupinfo=STARTUPINFO,
            creationflags=CREATE_NO_WINDOW
        )
        if result.returncode != 0:
            logger.warning(f"Failed to cleanup context file: {result.stderr}")
            return False
        return True
    except Exception as e:
        logger.warning(f"Error cleaning up context file: {e}")
        return False


def get_session_screen(lines: int = 60) -> str:
    """Get screen from dedicated peterbot session."""
    result = _tmux("capture-pane", "-t", PETERBOT_SESSION, "-p", "-S", f"-{lines}")
    return strip_ansi(result.stdout.strip())


async def handle_message(
    message: str,
    user_id: int,
    channel_id: int,
    interim_callback: Optional[Callable[[str], Awaitable[None]]] = None,
    busy_callback: Optional[Callable[[str], Awaitable[None]]] = None
) -> str:
    """Process peterbot message with memory context.

    Args:
        message: User's Discord message content
        user_id: Discord user ID for session tracking
        channel_id: Discord channel ID for per-channel buffer
        interim_callback: Optional async function to post interim "working on it" messages
        busy_callback: Optional async function to notify when Peter is busy with another task

    Returns:
        Claude Code's response to send back to Discord
    """
    global _last_channel_id, _current_task
    import time

    # 0. Ensure dedicated session exists
    success, error = await ensure_session()
    if not success:
        return f"Failed to create peterbot session: {error}"

    # 1. Add to recent buffer (per-channel)
    memory.add_to_buffer("user", message, channel_id)

    # 2. Fetch memory context (graceful degradation) - can happen outside lock
    try:
        memory_context = await memory.get_memory_context(query=message)
    except Exception as e:
        logger.warning(f"Memory context fetch failed: {e}")
        memory_context = ""  # Continue without memory

    # 2b. Fetch Second Brain knowledge context (graceful degradation)
    knowledge_context = ""
    try:
        from domains.second_brain.surfacing import get_context_for_message
        knowledge_context = await get_context_for_message(message)
    except Exception as e:
        logger.debug(f"Knowledge context fetch failed: {e}")
        # Continue without knowledge context

    # 3. Build full context (with per-channel recent buffer and channel isolation)
    channel_name = CHANNEL_ID_TO_NAME.get(channel_id, f"Channel {channel_id}")
    full_context = memory.build_full_context(
        message,
        memory_context,
        channel_id,
        channel_name,
        knowledge_context=knowledge_context
    )

    # 4-7. CRITICAL SECTION - acquire lock to prevent concurrent tmux access
    # Check if lock is held and notify user if so
    if _session_lock.locked() and busy_callback and _current_task:
        other_channel = _current_task.get("channel", "another channel")
        other_task = _current_task.get("task", "something")
        elapsed = time.time() - _current_task.get("started", time.time())
        try:
            if other_channel != channel_name:
                await busy_callback(f"🔄 Just finishing up in {other_channel} - be with you shortly!")
            else:
                await busy_callback(f"🔄 Still working on that - give me a sec...")
            logger.info(f"Sent busy notification (waiting {elapsed:.1f}s for lock)")
        except Exception as e:
            logger.warning(f"Failed to send busy notification: {e}")

    async with _session_lock:
        # Track current task for busy notifications
        _current_task = {
            "channel": channel_name,
            "task": message[:50] + "..." if len(message) > 50 else message,
            "started": time.time()
        }
        logger.debug("Acquired session lock for conversation")

        # 4a. Clear context if channel changed (prevents cross-channel contamination)
        if _last_channel_id is not None and _last_channel_id != channel_id:
            old_channel = CHANNEL_ID_TO_NAME.get(_last_channel_id, str(_last_channel_id))
            logger.info(f"Channel switch: {old_channel} → {channel_name}, clearing context")
            _tmux("send-keys", "-t", PETERBOT_SESSION, "/clear", "Enter")
            await asyncio.sleep(2)  # Wait for clear confirmation

        _last_channel_id = channel_id

        # 4. Capture screen state BEFORE sending (to diff later)
        screen_before = get_session_screen()
        logger.debug(f"SCREEN_BEFORE ({len(screen_before)} chars)")

        # 5. Write context to file (avoids tmux paste issues with large content)
        if not write_context_file(full_context):
            logger.error("Failed to write context file, sending message directly")
            send_to_session(message)  # Fallback to just the message
        else:
            # Send simple prompt telling Claude Code to read the context file
            send_to_session("Read context.md and respond to the user's latest message in the Current Message section.")

        # 6. Wait for response (poll until stable, with interim updates)
        raw_response = await wait_for_response(interim_callback=interim_callback)
        logger.debug(f"SCREEN_AFTER ({len(raw_response)} chars)")

        # 7. Extract only NEW content (diff from before)
        response = extract_new_response(screen_before, raw_response)
        logger.info(f"Extracted response ({len(response)} chars): {response[:80]}...")

        # Clear current task tracker
        _current_task = None

    logger.debug("Released session lock")

    # 7b. Log raw capture for debugging (async, non-blocking)
    log_raw_capture(message, screen_before, raw_response, response)

    # 8. Add response to buffer (per-channel)
    memory.add_to_buffer("assistant", response, channel_id)

    # 9. Capture pair async (fire-and-forget)
    # Note: Store task reference to prevent garbage collection
    session_id = f"discord-{user_id}"
    task = asyncio.create_task(memory.capture_message_pair(
        session_id, message, response
    ))
    # Add callback to log completion/errors
    task.add_done_callback(lambda t: logger.info(f"Memory capture completed: {t.exception() or 'success'}"))

    return response if response else "(No response captured)"


async def wait_for_response(
    timeout: Optional[int] = None,
    poll_interval: Optional[float] = None,
    interim_callback: Optional[Callable[[str], Awaitable[None]]] = None,
    stable_threshold: Optional[int] = None,
    expect_content: bool = False,
    context_filename: Optional[str] = None
) -> str:
    """Poll screen until output stabilizes AND Claude is ready for input.

    Args:
        timeout: Max seconds to wait (default: RESPONSE_TIMEOUT)
        poll_interval: Seconds between polls (default: POLL_INTERVAL)
        interim_callback: Optional async function to post interim status updates
        stable_threshold: Custom threshold for stability (default: STABLE_COUNT_THRESHOLD)
        expect_content: If True, ensure response contains actual content (not just prompt)
        context_filename: If provided, verify response includes reference to this file

    Returns:
        Final screen content when stable or on timeout
    """
    timeout = timeout or RESPONSE_TIMEOUT
    poll_interval = poll_interval or POLL_INTERVAL
    stable_threshold = stable_threshold or STABLE_COUNT_THRESHOLD

    last_content = ""
    stable_count = 0
    elapsed = 0.0
    last_interim_time = 0.0  # Track when we last posted an interim update
    interim_count = 0  # Track how many interim updates we've sent

    while elapsed < timeout:
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval

        current = get_session_screen()

        # Get the last portion of the screen for state detection
        lines = current.split('\n')
        last_3_lines = lines[-3:] if len(lines) >= 3 else lines
        last_chars = current[-200:] if len(current) > 200 else current

        # Check if still thinking/working - ONLY check last 3 lines for spinner
        # The spinner line format is: "✻ Thinking for 15s" or "⠋ Processing..."
        is_thinking = False
        for line in last_3_lines:
            stripped = line.strip()
            # Check if line starts with spinner character (animated spinner)
            # Only the braille spinners ⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏ and ✻ indicate active processing
            if any(stripped.startswith(char) for char in SPINNER_CHARS):
                is_thinking = True
                break

        # Check if Claude is ready for input (various prompt markers)
        # Claude Code may use different prompts: ❯, >, ●, or end with blank line
        prompt_markers = ['❯', '>', '●', '$ ']
        has_prompt = any(marker in last_chars for marker in prompt_markers)
        is_ready_for_input = has_prompt and not is_thinking

        # Post interim updates ONLY while actively thinking (spinner visible)
        # Don't post if just waiting for stability confirmation
        should_post_interim = False
        if interim_callback and is_thinking:
            if interim_count == 0 and elapsed >= INTERIM_UPDATE_DELAY:
                should_post_interim = True
            elif interim_count > 0 and (elapsed - last_interim_time) >= INTERIM_UPDATE_INTERVAL:
                should_post_interim = True

        if should_post_interim:
            interim_msg = _detect_interim_message(current, interim_count)
            if interim_msg:
                try:
                    await interim_callback(interim_msg)
                    logger.info(f"Posted interim update #{interim_count + 1}: {interim_msg}")
                    last_interim_time = elapsed
                    interim_count += 1
                except Exception as e:
                    logger.warning(f"Failed to post interim update: {e}")

        # Content validation when expect_content is True
        has_actual_content = True
        if expect_content and not is_thinking:
            # Check for actual response content (beyond just prompts/spinners)
            # Filter out lines that are just prompts or status
            content_lines = [
                line for line in lines
                if line.strip() and not any(
                    line.strip().startswith(char) for char in SPINNER_CHARS + prompt_markers
                )
            ]
            has_actual_content = len(content_lines) > 5  # Minimum response content

        # Consider stable when: content unchanged AND not thinking
        # Prompt marker is a bonus but not required for stability
        if current == last_content and not is_thinking and has_actual_content:
            stable_count += 1
            if stable_count >= stable_threshold:
                logger.debug(f"Response stable after {elapsed:.1f}s ({interim_count} interim updates)")
                return current
        else:
            stable_count = 0
            last_content = current

    logger.warning(f"Response timeout after {timeout}s, returning partial")
    return last_content  # Timeout, return what we have


async def wait_for_clear(timeout: float = 8.0) -> bool:
    """Wait for /clear command to complete.

    The /clear command clears the conversation context. This function waits
    until the screen shows a fresh prompt indicating clear completed.

    Args:
        timeout: Max seconds to wait (default: 8.0)

    Returns:
        True if clear completed, False if timed out
    """
    elapsed = 0.0
    poll_interval = 0.3
    stable_count = 0
    last_content = ""

    while elapsed < timeout:
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval

        current = get_session_screen()

        # Check for signs that /clear is complete:
        # - Screen shows fresh Claude prompt
        # - No spinner/thinking indicators
        lines = current.split('\n')
        last_3_lines = lines[-3:] if len(lines) >= 3 else lines

        # Check if still processing (spinner visible)
        is_thinking = False
        for line in last_3_lines:
            stripped = line.strip()
            if any(stripped.startswith(char) for char in SPINNER_CHARS):
                is_thinking = True
                break

        # Check for fresh prompt (indicates clear completed)
        prompt_markers = ['❯', '>', '●']
        has_prompt = any(marker in ''.join(last_3_lines) for marker in prompt_markers)

        # Stable when content unchanged, has prompt, and not thinking
        if current == last_content and has_prompt and not is_thinking:
            stable_count += 1
            if stable_count >= 2:  # Quick stability check for /clear
                logger.debug(f"/clear completed after {elapsed:.1f}s")
                return True
        else:
            stable_count = 0
            last_content = current

    logger.warning(f"/clear verification timeout after {timeout}s")
    return False


def _detect_interim_message(screen_content: str, update_count: int = 0) -> str:
    """Detect what Claude is doing and return appropriate interim message.

    Args:
        screen_content: Current screen content
        update_count: How many interim updates have been sent (for varying messages)

    Returns:
        Interim message string, or empty if none needed
    """
    content_lower = screen_content.lower()

    # Context-specific messages (first update is detailed, subsequent are brief)
    if 'gmail' in content_lower or 'email' in content_lower:
        if update_count == 0:
            return "📧 Checking your emails, give me a moment..."
        else:
            return "📧 Still searching emails..."
    elif 'calendar' in content_lower:
        if update_count == 0:
            return "📅 Looking at your calendar..."
        else:
            return "📅 Still checking calendar..."
    elif 'brave' in content_lower or 'web_search' in content_lower:
        if update_count == 0:
            return "🔍 Searching the web..."
        else:
            return "🔍 Still searching..."
    elif 'drive' in content_lower:
        if update_count == 0:
            return "📁 Searching Google Drive..."
        else:
            return "📁 Still searching Drive..."
    elif 'notion' in content_lower:
        if update_count == 0:
            return "📝 Checking Notion..."
        else:
            return "📝 Still on it..."
    elif 'traffic' in content_lower or 'directions' in content_lower:
        if update_count == 0:
            return "🚗 Getting traffic info..."
        else:
            return "🚗 Still fetching routes..."
    elif 'weather' in content_lower:
        if update_count == 0:
            return "🌤️ Checking the weather..."
        else:
            return "🌤️ Almost there..."

    # Check for general tool usage
    if any(p in screen_content for p in ['Read(', 'Bash(', 'WebFetch(', 'Grep(']):
        if update_count == 0:
            return "🔧 Working on it, one moment..."
        elif update_count == 1:
            return "🔧 Still working..."
        elif update_count == 2:
            return "🔧 Taking a bit longer than expected..."
        else:
            return "🔧 Bear with me, almost there..."

    # Generic working message - check for spinner characters
    if any(char in screen_content for char in SPINNER_CHARS):
        if update_count == 0:
            return "🤔 Thinking..."
        elif update_count == 1:
            return "🤔 Still thinking..."
        elif update_count == 2:
            return "🤔 This is a tricky one..."
        else:
            return "🤔 Nearly there..."

    return ""  # No interim message needed


def log_raw_capture(message: str, screen_before: str, screen_after: str, response: str) -> None:
    """Async log raw captures for debugging. Fire-and-forget."""
    import tempfile
    import os
    from datetime import datetime

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"""
{'='*80}
TIMESTAMP: {timestamp}
MESSAGE: {message[:100]}...
{'='*80}

--- SCREEN BEFORE ({len(screen_before)} chars) ---
{screen_before[-500:]}

--- SCREEN AFTER ({len(screen_after)} chars) ---
{screen_after[-1000:]}

--- EXTRACTED RESPONSE ({len(response)} chars) ---
{response[:500]}

"""
    try:
        # Write to Windows temp file, then copy to WSL
        with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False, encoding='utf-8') as f:
            f.write(log_entry)
            temp_path = f.name

        # Convert to WSL path and append
        wsl_temp = temp_path.replace('\\', '/').replace('C:', '/mnt/c')
        cmd = f"cat '{wsl_temp}' >> '{RAW_LOG_PATH}' && tail -c 50000 '{RAW_LOG_PATH}' > '{RAW_LOG_PATH}.tmp' && mv '{RAW_LOG_PATH}.tmp' '{RAW_LOG_PATH}' && rm -f '{wsl_temp}'"

        subprocess.Popen(
            ["wsl", "bash", "-c", cmd],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            startupinfo=STARTUPINFO,
            creationflags=CREATE_NO_WINDOW
        )
    except Exception:
        pass  # Silent fail - don't impact response


def on_startup() -> None:
    """Called on bot startup - start retry task."""
    memory.start_retry_task()
