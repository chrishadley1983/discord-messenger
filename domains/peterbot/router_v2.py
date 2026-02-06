"""Peterbot router v2 - Claude CLI --print mode (no tmux).

Routes messages through `claude -p --output-format stream-json --verbose`,
eliminating tmux screen-scraping, parser.py, and sanitiser.py entirely.

Each call is an independent process — no session lock, no contention.
"""

import asyncio
import json
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable, Awaitable

import aiohttp

from logger import logger
from . import memory
from .config import (
    CHANNEL_ID_TO_NAME,
    CLI_TOTAL_TIMEOUT,
    CLI_MODEL,
    CLI_WORKING_DIR,
)

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

# Approximate USD to GBP conversion rate (updated periodically)
USD_TO_GBP = 0.79

# Directory for WSL-side PID files (used to kill orphaned processes)
WSL_PID_DIR = "/tmp/peterbot_pids"

# Temp directory for downloaded attachments (images, files)
ATTACHMENT_TEMP_DIR = Path(__file__).parent.parent.parent / "data" / "tmp" / "attachments"

# Cost log file — JSONL for easy analysis
COST_LOG_PATH = Path(__file__).parent.parent.parent / "data" / "cli_costs.jsonl"


@dataclass
class CLIResultMeta:
    """Metadata from a CLI result event for cost logging."""
    result_text: str = ""
    cost_usd: float = 0.0
    model: str = ""
    duration_ms: float = 0.0
    num_turns: int = 0
    tools_used: list = field(default_factory=list)
    # Raw fields from the result event we might not know about yet
    raw_fields: dict = field(default_factory=dict)


def _log_cost(meta: CLIResultMeta, source: str, channel_name: str, message_preview: str):
    """Append cost entry to JSONL log for analysis.

    Args:
        meta: CLI result metadata
        source: "conversation" or "scheduled:<skill-name>"
        channel_name: Discord channel name
        message_preview: First 80 chars of user message or skill context
    """
    cost_gbp = meta.cost_usd * USD_TO_GBP

    entry = {
        "timestamp": datetime.now().isoformat(),
        "source": source,
        "channel": channel_name,
        "message": message_preview[:80],
        "cost_usd": round(meta.cost_usd, 6),
        "cost_gbp": round(cost_gbp, 6),
        "model": meta.model,
        "duration_ms": round(meta.duration_ms, 1),
        "num_turns": meta.num_turns,
        "tools_used": meta.tools_used,
        "response_chars": len(meta.result_text),
    }

    try:
        COST_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(COST_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        logger.debug(f"Cost log write failed: {e}")

    logger.info(
        f"CLI cost: ${meta.cost_usd:.4f} (£{cost_gbp:.4f}) | "
        f"{meta.duration_ms:.0f}ms | {len(meta.result_text)} chars | "
        f"tools={meta.tools_used} | {source}"
    )


# Tool name → interim message mapping
TOOL_INTERIM_MESSAGES = {
    "WebSearch": "🔍 Searching the web...",
    "WebFetch": "🌐 Fetching page...",
    "Read": "📄 Reading file...",
    "Bash": "⚙️ Running command...",
    "mcp__searxng__search": "🔍 Searching via SearXNG...",
    "mcp__brave-search__brave_web_search": "🔍 Searching via Brave...",
    "mcp__context7__query-docs": "📚 Looking up docs...",
    "mcp__supabase__execute_sql": "🗄️ Querying database...",
}


def _tool_to_interim(tool_name: str) -> str:
    """Map a tool name to an interim update message."""
    # Direct match first
    if tool_name in TOOL_INTERIM_MESSAGES:
        return TOOL_INTERIM_MESSAGES[tool_name]

    # Prefix match for MCP tools (e.g., mcp__searxng__anything)
    for prefix, msg in TOOL_INTERIM_MESSAGES.items():
        if "__" in prefix and tool_name.startswith(prefix.rsplit("__", 1)[0]):
            return msg

    # Generic fallback for any tool use
    if tool_name:
        return "🔧 Working on it..."
    return ""


def _windows_to_wsl_path(win_path: Path) -> str:
    """Convert a Windows path to a WSL-accessible /mnt/ path."""
    posix = str(win_path).replace("\\", "/")
    if len(posix) >= 2 and posix[1] == ":":
        drive = posix[0].lower()
        return f"/mnt/{drive}{posix[2:]}"
    return posix


async def _download_attachments(
    attachment_urls: list[dict],
) -> tuple[list[dict], list[Path]]:
    """Download image attachments to local temp files.

    Discord CDN URLs expire quickly, so we download images before invoking
    Claude and reference local file paths instead.

    Returns:
        (updated_attachments, temp_files_to_cleanup)
    """
    ATTACHMENT_TEMP_DIR.mkdir(parents=True, exist_ok=True)
    updated = []
    temp_files = []

    for att in attachment_urls:
        is_image = att.get("content_type", "").startswith("image/")
        if not is_image:
            updated.append(att)
            continue

        # Download image to temp file
        ext = Path(att.get("filename", "image.jpg")).suffix or ".jpg"
        temp_name = f"{uuid.uuid4().hex[:12]}{ext}"
        temp_path = ATTACHMENT_TEMP_DIR / temp_name

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(att["url"], timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status == 200:
                        data = await resp.read()
                        temp_path.write_bytes(data)
                        temp_files.append(temp_path)

                        wsl_path = _windows_to_wsl_path(temp_path)
                        updated.append({
                            **att,
                            "local_path": wsl_path,
                        })
                        logger.info(f"Downloaded attachment {att['filename']} ({len(data)} bytes)")
                    else:
                        logger.warning(f"Attachment download failed: HTTP {resp.status}")
                        updated.append(att)  # Fall back to URL
        except Exception as e:
            logger.warning(f"Attachment download failed: {e}")
            updated.append(att)  # Fall back to URL

    return updated, temp_files


def _cleanup_temp_files(temp_files: list[Path]) -> None:
    """Remove temporary attachment files."""
    for f in temp_files:
        try:
            f.unlink(missing_ok=True)
        except Exception:
            pass


async def _kill_wsl_process(pid_file: str) -> None:
    """Kill a Claude process inside WSL using its tracked PID file.

    proc.kill() only kills the Windows wsl.exe wrapper — the actual Claude
    process inside WSL continues running. This function reads the PID from
    the file and sends SIGKILL directly to the WSL-side process.
    """
    kill_cmd = (
        f"pid=$(cat {pid_file} 2>/dev/null) && "
        f"kill $pid 2>/dev/null; "
        f"sleep 0.2; "
        f"kill -9 $pid 2>/dev/null; "
        f"rm -f {pid_file}"
    )
    try:
        kill_proc = await asyncio.create_subprocess_exec(
            "wsl", "bash", "-c", kill_cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(kill_proc.wait(), timeout=5)
    except Exception as e:
        logger.debug(f"WSL process kill failed: {e}")


def _cleanup_stale_pids() -> None:
    """Kill any orphaned Claude processes from previous bot runs.

    Called once at startup to clean up PID files and their processes.
    """
    cleanup_cmd = (
        f"if [ -d {WSL_PID_DIR} ]; then "
        f"  for f in {WSL_PID_DIR}/*.pid; do "
        f"    [ -f \"$f\" ] && pid=$(cat \"$f\") && kill -9 $pid 2>/dev/null; "
        f"    rm -f \"$f\"; "
        f"  done; "
        f"fi"
    )
    try:
        subprocess.run(
            ["wsl", "bash", "-c", cleanup_cmd],
            timeout=10,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        logger.info("Cleaned up stale WSL Claude processes")
    except Exception as e:
        logger.debug(f"Stale PID cleanup failed: {e}")


def _build_cli_command(
    append_prompt: str = "Respond to the user message in the Current Message section.",
) -> tuple[list[str], str]:
    """Build the WSL command to invoke Claude CLI.

    Returns (command_list, pid_file_path) for asyncio.create_subprocess_exec().
    Uses `exec` so bash replaces itself with Claude, inheriting the PID.
    No --max-budget-usd: CLI runs on subscription, not API billing.
    """
    invocation_id = uuid.uuid4().hex[:12]
    pid_file = f"{WSL_PID_DIR}/{invocation_id}.pid"

    # Build the claude command that runs inside WSL
    # mkdir -p ensures pid dir exists; echo $$ writes bash PID;
    # exec replaces bash with claude so the PID stays the same
    claude_cmd = (
        f"mkdir -p {WSL_PID_DIR} && "
        f"echo $$ > {pid_file} && "
        f"cd {CLI_WORKING_DIR} && "
        f"exec claude -p "
        f"--output-format stream-json "
        f"--verbose "
        f"--append-system-prompt '{append_prompt}' "
        f"--permission-mode bypassPermissions "
        f"--no-session-persistence "
        f"--model {CLI_MODEL}"
    )

    return ["wsl", "bash", "-c", claude_cmd], pid_file


async def _stream_response(
    proc: asyncio.subprocess.Process,
    context_bytes: bytes,
    meta: CLIResultMeta,
    interim_callback: Optional[Callable[[str], Awaitable[None]]] = None,
) -> CLIResultMeta:
    """Write stdin and read stdout concurrently, parsing NDJSON events.

    Args:
        proc: The subprocess running claude CLI
        context_bytes: UTF-8 encoded context to pipe via stdin
        meta: Shared CLIResultMeta — updated incrementally so timeout captures partial data
        interim_callback: Optional async function for interim status updates

    Returns:
        CLIResultMeta with result text and cost/usage metadata
    """
    # Write context to stdin
    proc.stdin.write(context_bytes)
    await proc.stdin.drain()
    proc.stdin.close()

    last_assistant_text = ""  # Fallback: last text from assistant events
    posted_tools = set()  # Avoid duplicate interim messages for same tool type

    async for raw_line in proc.stdout:
        line = raw_line.decode("utf-8", errors="replace").strip()
        if not line:
            continue

        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            logger.debug(f"CLI non-JSON line: {line[:100]}")
            continue

        etype = event.get("type")
        esubtype = event.get("subtype")

        if etype == "system" and esubtype == "init":
            mcp = event.get("mcp_servers", [])
            meta.model = event.get("model", "unknown")
            logger.info(f"CLI init: {len(mcp)} MCP servers, model={meta.model}")

        elif etype == "assistant":
            meta.num_turns += 1
            # Extract text content blocks (fallback if result field is empty)
            for block in event.get("message", {}).get("content", []):
                if block.get("type") == "text":
                    text = block.get("text", "").strip()
                    if text:
                        last_assistant_text = text

                # Track tool use and post interim updates (update meta incrementally)
                if block.get("type") == "tool_use":
                    tool_name = block.get("name", "")
                    meta.tools_used.append(tool_name)

                    if interim_callback:
                        tool_prefix = tool_name.split("__")[0] if "__" in tool_name else tool_name
                        if tool_prefix not in posted_tools:
                            interim_msg = _tool_to_interim(tool_name)
                            if interim_msg:
                                try:
                                    await interim_callback(interim_msg)
                                    posted_tools.add(tool_prefix)
                                except Exception as e:
                                    logger.warning(f"Interim callback failed: {e}")

        # Detect hook feedback loop: synthetic user messages mean Stop hooks
        # are injecting errors. The real response is already in last_assistant_text.
        # Return immediately — the result event will never arrive.
        elif etype == "user" and event.get("isSynthetic"):
            logger.warning("Hook feedback loop detected — returning with captured response")
            if last_assistant_text:
                meta.result_text = last_assistant_text
            return meta

        elif etype == "result":
            if event.get("is_error") or esubtype == "error":
                error_msg = event.get("result", "Unknown error")
                logger.error(f"CLI error result: {error_msg}")
                meta.result_text = f"⚠️ Something went wrong: {error_msg[:200]}"
                return meta

            meta.result_text = event.get("result", "")
            meta.cost_usd = event.get("total_cost_usd", 0)
            meta.duration_ms = event.get("duration_ms", 0)

            # Capture any extra fields we don't know about yet
            known_keys = {"type", "subtype", "result", "total_cost_usd", "duration_ms",
                          "is_error", "num_turns", "session_id", "cost_usd"}
            meta.raw_fields = {k: v for k, v in event.items() if k not in known_keys}

            # Fallback: if result is empty but we captured assistant text, use that
            if not meta.result_text and last_assistant_text:
                logger.warning(f"Empty result field, using last assistant text ({len(last_assistant_text)} chars)")
                meta.result_text = last_assistant_text

            # Return immediately after result — do NOT continue reading stdout.
            # Claude Code's Stop hooks (e.g., claude-mem summarize) can create
            # infinite loops when --no-session-persistence means no transcript file.
            # The caller will kill the process to clean up.
            return meta

    return meta


async def invoke_claude_cli(
    context: str,
    append_prompt: str = "Respond to the user message in the Current Message section.",
    timeout: int = CLI_TOTAL_TIMEOUT,
    interim_callback: Optional[Callable[[str], Awaitable[None]]] = None,
    cost_source: str = "unknown",
    cost_channel: str = "",
    cost_message: str = "",
) -> str:
    """Invoke Claude CLI with context via stdin and return the result.

    This is the shared helper used by both handle_message() and the scheduler.

    Args:
        context: Full context string to send
        append_prompt: System prompt suffix
        timeout: Max seconds for full execution
        interim_callback: Optional async function for interim status updates
        cost_source: Label for cost log (e.g., "conversation", "scheduled:hydration")
        cost_channel: Channel name for cost log
        cost_message: Message preview for cost log

    Returns:
        Clean response text, or error message string
    """
    cmd, pid_file = _build_cli_command(append_prompt=append_prompt)
    wall_start = time.monotonic()

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=10 * 1024 * 1024,  # 10MB — image tool results can be large
        )
    except Exception as e:
        logger.error(f"Failed to spawn Claude CLI: {e}")
        return "⚠️ Could not start Claude. Please try again."

    context_bytes = context.encode("utf-8")

    # Shared meta object — updated incrementally by _stream_response
    # so we can log partial data on timeout
    meta = CLIResultMeta()

    try:
        meta = await asyncio.wait_for(
            _stream_response(proc, context_bytes, meta, interim_callback),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        meta.duration_ms = (time.monotonic() - wall_start) * 1000
        logger.error(
            f"CLI timed out after {timeout}s | "
            f"turns={meta.num_turns} | tools={meta.tools_used}"
        )
        _log_cost(meta, cost_source, cost_channel, f"TIMEOUT: {cost_message}")
        # Kill both Windows wrapper AND the WSL-side Claude process
        proc.kill()
        await proc.wait()
        await _kill_wsl_process(pid_file)
        return "⚠️ Response timed out. Try a simpler question or try again."

    wall_ms = (time.monotonic() - wall_start) * 1000

    # Kill process immediately — _stream_response returns after the result event
    # but the CLI may still be running Stop hooks (claude-mem summarize loop).
    # We have our result, so kill both Windows and WSL processes.
    try:
        proc.kill()
    except ProcessLookupError:
        pass  # Already exited
    await proc.wait()
    await _kill_wsl_process(pid_file)

    # Use wall clock if CLI didn't report duration
    if not meta.duration_ms:
        meta.duration_ms = wall_ms

    # Log cost data
    _log_cost(meta, cost_source, cost_channel, cost_message)

    if not meta.result_text:
        logger.error("CLI produced no result text")
        return "⚠️ Claude encountered an issue. Please try again."

    return meta.result_text


async def handle_message(
    message: str,
    user_id: int,
    channel_id: int,
    interim_callback: Optional[Callable[[str], Awaitable[None]]] = None,
    busy_callback: Optional[Callable[[str], Awaitable[None]]] = None,
    attachment_urls: Optional[list[dict]] = None,
) -> str:
    """Process peterbot message with memory context via Claude CLI.

    Drop-in replacement for router.handle_message() — same signature, same return type.
    No session lock needed; each call is an independent process.

    Args:
        message: User's Discord message content
        user_id: Discord user ID for session tracking
        channel_id: Discord channel ID for per-channel buffer
        interim_callback: Optional async function to post interim "working on it" messages
        busy_callback: Not used in v2 (no lock contention), kept for signature compat
        attachment_urls: Optional list of attachment dicts with url, filename, content_type, size

    Returns:
        Claude's response to send back to Discord
    """
    # 1. Add to recent buffer (per-channel)
    memory.add_to_buffer("user", message, channel_id)

    # 1b. Download image attachments to local files (Discord CDN URLs expire)
    temp_files = []
    if attachment_urls:
        has_images = any(a.get("content_type", "").startswith("image/") for a in attachment_urls)
        if has_images:
            attachment_urls, temp_files = await _download_attachments(attachment_urls)

    try:
        # 2. Fetch memory context (graceful degradation)
        try:
            memory_context = await memory.get_memory_context(query=message)
        except Exception as e:
            logger.warning(f"Memory context fetch failed: {e}")
            memory_context = ""

        # 2b. Fetch Second Brain knowledge context (graceful degradation)
        knowledge_context = ""
        try:
            from domains.second_brain.surfacing import get_context_for_message
            knowledge_context = await get_context_for_message(message)
        except Exception as e:
            logger.debug(f"Knowledge context fetch failed: {e}")

        # 3. Build full context (with per-channel recent buffer and channel isolation)
        channel_name = CHANNEL_ID_TO_NAME.get(channel_id, f"Channel {channel_id}")
        full_context = memory.build_full_context(
            message,
            memory_context,
            channel_id,
            channel_name,
            knowledge_context=knowledge_context,
            attachment_urls=attachment_urls,
        )

        # 4. Send to Claude CLI (no lock needed — independent process)
        response = await invoke_claude_cli(
            context=full_context,
            append_prompt="Respond to the user message in the Current Message section.",
            interim_callback=interim_callback,
            cost_source="conversation",
            cost_channel=channel_name,
            cost_message=message,
        )
    finally:
        # Clean up temp image files regardless of success/failure
        if temp_files:
            _cleanup_temp_files(temp_files)

    # 5. Add response to buffer (per-channel)
    memory.add_to_buffer("assistant", response, channel_id)

    # 6. Capture pair async (fire-and-forget)
    session_id = f"discord-{user_id}"
    task = asyncio.create_task(memory.capture_message_pair(
        session_id, message, response
    ))
    task.add_done_callback(
        lambda t: logger.info(f"Memory capture completed: {t.exception() or 'success'}")
    )

    return response if response else "(No response captured)"


def on_startup() -> None:
    """Called on bot startup - start retry task and clean up orphaned processes."""
    _cleanup_stale_pids()
    memory.start_retry_task()
