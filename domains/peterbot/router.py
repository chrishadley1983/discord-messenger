"""Peterbot message routing with memory context injection.

Routes peterbot messages through Claude Code (tmux) with memory context,
unlike the dumb tunnel used by claude-code channel.
"""

import asyncio
import re
from typing import Optional

from . import memory
from .config import (
    PETERBOT_SESSION,
    PETERBOT_SESSION_PATH,
    RESPONSE_TIMEOUT,
    POLL_INTERVAL,
    STABLE_COUNT_THRESHOLD,
    CONTEXT_FILE,
)
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
    import subprocess

    # Check if path exists in WSL
    check = subprocess.run(
        ["wsl", "test", "-d", PETERBOT_SESSION_PATH],
        capture_output=True
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

    # Start claude in the session
    _tmux("send-keys", "-t", PETERBOT_SESSION, "claude", "Enter")

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
    _tmux("send-keys", "-t", PETERBOT_SESSION, "-l", prompt)
    _tmux("send-keys", "-t", PETERBOT_SESSION, "Enter")


def write_context_file(content: str) -> bool:
    """Write context to file in WSL for Claude Code to read.

    Args:
        content: Full context string to write

    Returns:
        True if successful, False otherwise
    """
    import subprocess

    # Write via WSL bash - escape content properly
    # Use base64 to avoid escaping issues with special characters
    import base64
    encoded = base64.b64encode(content.encode('utf-8')).decode('ascii')

    cmd = f"echo '{encoded}' | base64 -d > '{CONTEXT_FILE}'"

    try:
        result = subprocess.run(
            ["wsl", "bash", "-c", cmd],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            logger.error(f"Failed to write context file: {result.stderr}")
            return False
        return True
    except Exception as e:
        logger.error(f"Error writing context file: {e}")
        return False


def get_session_screen(lines: int = 60) -> str:
    """Get screen from dedicated peterbot session."""
    result = _tmux("capture-pane", "-t", PETERBOT_SESSION, "-p", "-S", f"-{lines}")
    return strip_ansi(result.stdout.strip())


def extract_response(raw_screen: str) -> str:
    """Extract Claude's response from raw screen output.

    Peterbot-specific extraction that strips Claude Code UI elements:
    - Input prompt lines (>, ❯)
    - Status lines (tokens, cost, file reads, hooks)
    - Keyboard shortcut hints (ctrl+o, ? for shortcuts)
    - Nested output markers (⎿)

    Args:
        raw_screen: Raw captured screen content

    Returns:
        Cleaned response text (just the message content)
    """
    lines = raw_screen.split('\n')
    response_lines = []
    in_response = False

    for line in lines:
        stripped = line.strip()

        # Skip prompt lines - marks start of response
        if stripped.startswith('>') or stripped.startswith('❯'):
            in_response = True
            continue

        # Skip empty lines before we're in response
        if not in_response and not stripped:
            continue

        # Skip Claude Code UI elements
        if 'ctrl+' in line.lower() or 'ctrl-' in line.lower():
            continue
        if '? for shortcuts' in line.lower():
            continue
        if re.match(r'.*Read \d+ file', line, re.I):
            continue
        if re.match(r'.*Ran \d+ .*(hook|tool)', line, re.I):
            continue
        if re.match(r'.*\d+ (stop |start )?hook', line, re.I):
            continue
        if 'hook error' in line.lower():
            continue
        if stripped.startswith('⎿'):
            continue

        # Skip status/token lines
        if re.match(r'^\s*\d+[kK]?\s*(tokens?|input|output)', line, re.I):
            continue
        if 'cost:' in line.lower() or 'tokens:' in line.lower():
            continue

        if in_response:
            # Remove leading ● bullet if present (Claude Code formatting)
            cleaned = re.sub(r'^●\s*', '', stripped)
            if cleaned:  # Only add non-empty lines
                # Skip prompt bleed-through
                if cleaned.lower() in ('output', 'input'):
                    continue
                if 'message section' in cleaned.lower():
                    continue
                if 'context.md' in cleaned.lower():
                    continue
                response_lines.append(cleaned)

    return '\n'.join(response_lines).strip()


def extract_new_response(screen_before: str, screen_after: str) -> str:
    """Extract only the NEW content from screen diff.

    Compares before/after screen captures and returns only new lines,
    then applies response extraction/cleaning.

    Args:
        screen_before: Screen content before sending message
        screen_after: Screen content after response stabilized

    Returns:
        Cleaned new response text
    """
    # Get lines from before (as a set for fast lookup)
    before_lines = set(screen_before.split('\n'))

    # Find new lines in after
    after_lines = screen_after.split('\n')
    new_lines = []

    for line in after_lines:
        if line not in before_lines:
            new_lines.append(line)

    # Join new lines and apply extraction/cleaning
    new_content = '\n'.join(new_lines)
    return extract_response(new_content)


async def handle_message(message: str, user_id: int) -> str:
    """Process peterbot message with memory context.

    Args:
        message: User's Discord message content
        user_id: Discord user ID for session tracking

    Returns:
        Claude Code's response to send back to Discord
    """
    # 0. Ensure dedicated session exists
    success, error = await ensure_session()
    if not success:
        return f"Failed to create peterbot session: {error}"

    # 1. Add to recent buffer
    memory.add_to_buffer("user", message)

    # 2. Fetch memory context (graceful degradation)
    try:
        memory_context = await memory.get_memory_context(query=message)
    except Exception as e:
        logger.warning(f"Memory context fetch failed: {e}")
        memory_context = ""  # Continue without memory

    # 3. Build full context
    full_context = memory.build_full_context(message, memory_context)

    # 4. Capture screen state BEFORE sending (to diff later)
    screen_before = get_session_screen()

    # 5. Write context to file (avoids tmux paste issues with large content)
    if not write_context_file(full_context):
        logger.error("Failed to write context file, sending message directly")
        send_to_session(message)  # Fallback to just the message
    else:
        # Send simple prompt telling Claude Code to read the context file
        send_to_session("Read context.md and respond to the user's latest message in the Current Message section.")

    # 6. Wait for response (poll until stable)
    raw_response = await wait_for_response()

    # 7. Extract only NEW content (diff from before)
    response = extract_new_response(screen_before, raw_response)

    # 8. Add response to buffer
    memory.add_to_buffer("assistant", response)

    # 9. Capture pair async (fire-and-forget)
    session_id = f"discord-{user_id}"
    asyncio.create_task(memory.capture_message_pair(
        session_id, message, response
    ))

    return response if response else "(No response captured)"


async def wait_for_response(
    timeout: Optional[int] = None,
    poll_interval: Optional[float] = None
) -> str:
    """Poll screen until output stabilizes.

    Args:
        timeout: Max seconds to wait (default: RESPONSE_TIMEOUT)
        poll_interval: Seconds between polls (default: POLL_INTERVAL)

    Returns:
        Final screen content when stable or on timeout
    """
    timeout = timeout or RESPONSE_TIMEOUT
    poll_interval = poll_interval or POLL_INTERVAL

    last_content = ""
    stable_count = 0
    elapsed = 0.0

    while elapsed < timeout:
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval

        current = get_session_screen()
        if current == last_content:
            stable_count += 1
            if stable_count >= STABLE_COUNT_THRESHOLD:  # Stable for 1.5s
                return current
        else:
            stable_count = 0
            last_content = current

    logger.warning(f"Response timeout after {timeout}s, returning partial")
    return last_content  # Timeout, return what we have


def on_startup() -> None:
    """Called on bot startup - start retry task."""
    memory.start_retry_task()
