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
from typing import Optional, Callable, Awaitable, Union

import aiohttp

from logger import logger
from . import memory
from .config import (
    CHANNEL_ID_TO_NAME,
    CLI_COMMAND,
    CLI_CC_CONFIG_DIR,
    CLI_CC2_CONFIG_DIR,
    CLI_TOTAL_TIMEOUT,
    CLI_MAX_TURNS,
    CLI_SCHEDULED_MAX_TURNS,
    CLI_MODEL,
    CLI_SCHEDULED_MODEL,
    CLI_WORKING_DIR,
    DOCUMENT_MIN_LENGTH,
    DOCUMENT_MIN_HEADERS,
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


# Tool name → emoji mapping for activity log
TOOL_EMOJI = {
    "Read": "📄",
    "Edit": "✏️",
    "Write": "📝",
    "Bash": "⚙️",
    "Grep": "🔎",
    "Glob": "📂",
    "WebSearch": "🔍",
    "WebFetch": "🌐",
    "Task": "🤖",
    "mcp__searxng__search": "🔍",
    "mcp__brave-search__brave_web_search": "🔍",
    "mcp__context7__query-docs": "📚",
    "mcp__supabase__execute_sql": "🗄️",
    "mcp__playwright__browser_navigate": "🌐",
    "mcp__playwright__browser_click": "🖱️",
    "mcp__playwright__browser_type": "⌨️",
    "mcp__playwright__browser_snapshot": "📸",
}


def _tool_emoji(tool_name: str) -> str:
    """Get emoji for a tool name."""
    if tool_name in TOOL_EMOJI:
        return TOOL_EMOJI[tool_name]
    for prefix, emoji in TOOL_EMOJI.items():
        if "__" in prefix and tool_name.startswith(prefix.rsplit("__", 1)[0]):
            return emoji
    return "🔧"


def _tool_context(tool_name: str, tool_input: dict) -> str:
    """Extract a short human-readable context string from tool input."""
    if tool_name == "Read":
        fp = tool_input.get("file_path", "")
        return _short_path(fp) if fp else ""
    if tool_name in ("Edit", "Write"):
        fp = tool_input.get("file_path", "")
        return _short_path(fp) if fp else ""
    if tool_name == "Bash":
        cmd = tool_input.get("command", "")
        return f"`{cmd[:80]}{'…' if len(cmd) > 80 else ''}`" if cmd else ""
    if tool_name == "Grep":
        pat = tool_input.get("pattern", "")
        return f'"{pat[:40]}"' if pat else ""
    if tool_name == "Glob":
        pat = tool_input.get("pattern", "")
        return f"`{pat}`" if pat else ""
    if tool_name == "WebSearch":
        q = tool_input.get("query", "")
        return f'"{q[:60]}"' if q else ""
    if tool_name == "WebFetch":
        url = tool_input.get("url", "")
        return url[:60] if url else ""
    if tool_name == "Task":
        desc = tool_input.get("description", "")
        return desc[:60] if desc else ""
    if "execute_sql" in tool_name:
        q = tool_input.get("query", "")
        return f"`{q[:60]}{'…' if len(q) > 60 else ''}`" if q else ""
    return ""


def _short_path(fp: str) -> str:
    """Shorten a file path to just filename or last 2 segments."""
    parts = fp.replace("\\", "/").split("/")
    if len(parts) <= 2:
        return fp
    return "/".join(parts[-2:])


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


_DEFAULT_APPEND_PROMPT = (
    "Respond to the user message in the Current Message section. "
    "RESILIENCE RULES: "
    "If a tool call, API endpoint, or command fails, do NOT retry the same thing more than twice. "
    "After 2 failures, STOP and try an alternative approach: use a different tool, build the missing "
    "functionality yourself, work around the problem, or tell the user what went wrong and what you tried. "
    "You have full autonomy — you can create files, write code, build endpoints, install packages. "
    "Never burn turns retrying something that is clearly broken."
)


def _build_cli_command(
    append_prompt: str = _DEFAULT_APPEND_PROMPT,
    config_dir: str = "",
    model: str = "",
) -> tuple[list[str], str]:
    """Build the WSL command to invoke Claude CLI.

    Args:
        append_prompt: System prompt suffix for Claude
        config_dir: WSL path to CLAUDE_CONFIG_DIR (empty = default ~/.claude)
        model: Model to use (empty = CLI_MODEL default)

    Returns (command_list, pid_file_path) for asyncio.create_subprocess_exec().
    Uses `exec` so bash replaces itself with Claude, inheriting the PID.
    """
    invocation_id = uuid.uuid4().hex[:12]
    pid_file = f"{WSL_PID_DIR}/{invocation_id}.pid"

    use_model = model or CLI_MODEL
    config_export = f"export CLAUDE_CONFIG_DIR='{config_dir}' && " if config_dir else ""
    claude_cmd = (
        f"mkdir -p {WSL_PID_DIR} && "
        f"echo $$ > {pid_file} && "
        f"cd {CLI_WORKING_DIR} && "
        f"{config_export}"
        f"exec {CLI_COMMAND} -p "
        f"--output-format stream-json "
        f"--verbose "
        f"--append-system-prompt '{append_prompt}' "
        f"--permission-mode bypassPermissions "
        f"--no-session-persistence "
        f"--model {use_model}"
    )

    return ["wsl", "bash", "-c", claude_cmd], pid_file


async def _stream_response(
    proc: asyncio.subprocess.Process,
    context_bytes: bytes,
    meta: CLIResultMeta,
    interim_callback: Optional[Callable[[Union[str, dict]], Awaitable[None]]] = None,
    max_turns: int = 0,
) -> CLIResultMeta:
    """Write stdin and read stdout concurrently, parsing NDJSON events.

    Args:
        proc: The subprocess running claude CLI
        context_bytes: UTF-8 encoded context to pipe via stdin
        meta: Shared CLIResultMeta — updated incrementally so timeout captures partial data
        interim_callback: Optional async function for interim status updates
        max_turns: Max agentic turns before aborting (0 = unlimited)

    Returns:
        CLIResultMeta with result text and cost/usage metadata
    """
    # Write context to stdin
    proc.stdin.write(context_bytes)
    await proc.stdin.drain()
    proc.stdin.close()

    last_assistant_text = ""  # Fallback: last text from assistant events
    non_json_lines = []  # Capture non-JSON output for credit error detection
    start_time = time.monotonic()
    tool_call_counts: dict[str, int] = {}  # Track repeated tool calls for loop detection
    TOOL_REPEAT_LIMIT = 10  # Abort if same tool+context called this many times
    # Only detect loops on tools that can fail in retry-worthy ways.
    # Read/Glob/Grep are idempotent and safe to repeat (Claude re-reads files normally).
    LOOP_DETECT_TOOLS = {"Bash", "WebFetch", "WebSearch", "mcp__searxng__search"}

    async for raw_line in proc.stdout:
        line = raw_line.decode("utf-8", errors="replace").strip()
        if not line:
            continue

        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            logger.debug(f"CLI non-JSON line: {line[:200]}")
            non_json_lines.append(line)
            continue

        etype = event.get("type")
        esubtype = event.get("subtype")

        if etype == "system" and esubtype == "init":
            mcp = event.get("mcp_servers", [])
            meta.model = event.get("model", "unknown")
            logger.info(f"CLI init: {len(mcp)} MCP servers, model={meta.model}")

        elif etype == "assistant":
            meta.num_turns += 1

            # Enforce max turns to prevent runaway tool chains
            if max_turns and meta.num_turns > max_turns:
                logger.warning(
                    f"Max turns ({max_turns}) exceeded at turn {meta.num_turns} — "
                    f"aborting with last response ({len(last_assistant_text)} chars)"
                )
                if last_assistant_text:
                    meta.result_text = last_assistant_text
                else:
                    meta.result_text = "I got a bit carried away there. Could you try rephrasing your request?"
                return meta

            # Extract text content blocks (fallback if result field is empty)
            for block in event.get("message", {}).get("content", []):
                if block.get("type") == "text":
                    text = block.get("text", "").strip()
                    if text:
                        last_assistant_text = text

                # Track tool use and post interim updates (update meta incrementally)
                if block.get("type") == "tool_use":
                    tool_name = block.get("name", "")
                    tool_input = block.get("input", {})
                    meta.tools_used.append(tool_name)

                    # Loop detection: only for tools that can fail in retry-worthy ways
                    sig_context = _tool_context(tool_name, tool_input)
                    call_sig = f"{tool_name}:{sig_context}"
                    if tool_name in LOOP_DETECT_TOOLS:
                        tool_call_counts[call_sig] = tool_call_counts.get(call_sig, 0) + 1
                    if tool_call_counts.get(call_sig, 0) >= TOOL_REPEAT_LIMIT:
                        logger.warning(
                            f"Loop detected: {call_sig!r} called {TOOL_REPEAT_LIMIT} times — "
                            f"aborting at turn {meta.num_turns}"
                        )
                        abort_msg = (
                            f"⚠️ I got stuck retrying the same action ({tool_name}: {sig_context}). "
                            "I've stopped to avoid wasting turns. "
                            "Could you rephrase or tell me how to approach this differently?"
                        )
                        meta.result_text = abort_msg
                        return meta

                    if interim_callback:
                        elapsed = time.monotonic() - start_time
                        tool_info = {
                            "tool_name": tool_name,
                            "tool_input": tool_input,
                            "emoji": _tool_emoji(tool_name),
                            "context": _tool_context(tool_name, tool_input),
                            "turn": meta.num_turns,
                            "elapsed_seconds": elapsed,
                        }
                        try:
                            await interim_callback(tool_info)
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

                # Check for credit/billing exhaustion — return sentinel for invoke_llm
                from .provider_manager import is_credit_exhaustion_error
                if is_credit_exhaustion_error(error_msg):
                    logger.warning(f"Credit exhaustion detected: {error_msg[:100]}")
                    meta.result_text = "__CREDIT_EXHAUSTED__"
                    return meta

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

    # Process exited without a result event — log diagnostics
    if not meta.result_text:
        exit_code = proc.returncode
        if non_json_lines:
            combined = " ".join(non_json_lines)
            logger.warning(
                f"CLI exited without result event | exit_code={exit_code} | "
                f"turns={meta.num_turns} | non-JSON output: {combined[:500]}"
            )
            from .provider_manager import is_credit_exhaustion_error
            if is_credit_exhaustion_error(combined):
                logger.warning(f"Credit exhaustion detected in non-JSON output")
                meta.result_text = "__CREDIT_EXHAUSTED__"
        else:
            logger.warning(
                f"CLI exited silently — no result, no output | exit_code={exit_code} | "
                f"turns={meta.num_turns} | tools={meta.tools_used}"
            )

    return meta


async def invoke_claude_cli(
    context: str,
    append_prompt: str = _DEFAULT_APPEND_PROMPT,
    timeout: int = CLI_TOTAL_TIMEOUT,
    interim_callback: Optional[Callable[[Union[str, dict]], Awaitable[None]]] = None,
    cost_source: str = "unknown",
    cost_channel: str = "",
    cost_message: str = "",
    config_dir: str = "",
    max_turns: int = 0,
    model: str = "",
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
        config_dir: WSL path to CLAUDE_CONFIG_DIR (empty = default ~/.claude)
        max_turns: Max agentic turns before aborting (0 = unlimited)

    Returns:
        Clean response text, or error message string
    """
    cmd, pid_file = _build_cli_command(append_prompt=append_prompt, config_dir=config_dir, model=model)
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
        logger.error(
            f"Failed to spawn Claude CLI: {e} | "
            f"source={cost_source} | message={cost_message[:80]}"
        )
        return "⚠️ Could not start Claude. Please try again."

    context_bytes = context.encode("utf-8")
    logger.debug(
        f"CLI started | context_bytes={len(context_bytes)} | "
        f"source={cost_source} | message={cost_message[:80]}"
    )

    # Shared meta object — updated incrementally by _stream_response
    # so we can log partial data on timeout
    meta = CLIResultMeta()

    try:
        meta = await asyncio.wait_for(
            _stream_response(proc, context_bytes, meta, interim_callback, max_turns=max_turns),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        meta.duration_ms = (time.monotonic() - wall_start) * 1000
        logger.error(
            f"CLI timed out after {timeout}s | "
            f"turns={meta.num_turns} | model={meta.model or 'none'} | "
            f"tools={meta.tools_used} | context_bytes={len(context_bytes)} | "
            f"source={cost_source} | message={cost_message[:80]}"
        )
        _log_cost(meta, cost_source, cost_channel, f"TIMEOUT: {cost_message}")
        # Kill both Windows wrapper AND the WSL-side Claude process
        proc.kill()
        await proc.wait()
        await _kill_wsl_process(pid_file)

        # Check if timeout was caused by rate limit (CLI hangs on interactive menu)
        # meta.result_text may contain __CREDIT_EXHAUSTED__ from non-JSON line detection
        if meta.result_text == CREDIT_EXHAUSTED_SENTINEL:
            return CREDIT_EXHAUSTED_SENTINEL

        # Also check stderr for rate limit clues
        try:
            stderr_bytes = await asyncio.wait_for(proc.stderr.read(), timeout=2)
            stderr_text = stderr_bytes.decode("utf-8", errors="replace").strip()
            if stderr_text:
                logger.error(f"CLI stderr (after timeout): {stderr_text[:300]}")
                from .provider_manager import is_credit_exhaustion_error
                if is_credit_exhaustion_error(stderr_text):
                    return CREDIT_EXHAUSTED_SENTINEL
        except Exception:
            pass

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

    # If no result text, capture stderr and log detailed diagnostics
    if not meta.result_text:
        stderr_text = ""
        try:
            stderr_bytes = await asyncio.wait_for(proc.stderr.read(), timeout=2)
            stderr_text = stderr_bytes.decode("utf-8", errors="replace").strip()
        except Exception:
            pass

        exit_code = proc.returncode
        logger.error(
            f"CLI produced no result text | exit_code={exit_code} | "
            f"wall_ms={wall_ms:.0f} | turns={meta.num_turns} | "
            f"model={meta.model or 'none'} | tools={meta.tools_used} | "
            f"stderr={stderr_text[:500] if stderr_text else '(empty)'} | "
            f"source={cost_source} | message={cost_message[:80]}"
        )

        from .provider_manager import is_credit_exhaustion_error
        if is_credit_exhaustion_error(stderr_text):
            logger.warning(f"Credit exhaustion detected in stderr: {stderr_text[:100]}")
            return CREDIT_EXHAUSTED_SENTINEL

        return "⚠️ Claude encountered an issue. Please try again."

    return meta.result_text


# Sentinel value returned by invoke_claude_cli when credits are exhausted
CREDIT_EXHAUSTED_SENTINEL = "__CREDIT_EXHAUSTED__"


def _get_config_dir_for_provider(provider: str) -> str:
    """Return the CLAUDE_CONFIG_DIR for a Claude provider."""
    if provider == "claude_cc":
        return CLI_CC_CONFIG_DIR
    elif provider == "claude_cc2":
        return CLI_CC2_CONFIG_DIR
    return ""


# Display labels for user-facing messages and cost logs
PROVIDER_LABELS = {
    "claude_cc": "Claude (cc)",
    "claude_cc2": "Claude (cc2)",
    "kimi": "Kimi 2.5",
}


async def invoke_llm(
    context: str,
    append_prompt: str = _DEFAULT_APPEND_PROMPT,
    timeout: int = CLI_TOTAL_TIMEOUT,
    interim_callback: Optional[Callable[[Union[str, dict]], Awaitable[None]]] = None,
    cost_source: str = "unknown",
    cost_channel: str = "",
    cost_message: str = "",
    max_turns: int = 0,
    model: str = "",
) -> tuple[str, str]:
    """Route to active provider with automatic cascade on credit exhaustion.

    Priority: claude_cc → claude_cc2 → kimi
    On credit exhaustion, tries the next provider and persists the switch.

    Args:
        context: Full context string to send
        append_prompt: System prompt suffix (Claude only)
        timeout: Max seconds for execution
        interim_callback: Optional async function for interim status updates
        cost_source: Label for cost log
        cost_channel: Channel name for cost log
        cost_message: Message preview for cost log
        max_turns: Max agentic turns before aborting (0 = unlimited)

    Returns:
        Tuple of (response_text, provider_name)
    """
    from .provider_manager import get_active_provider, get_next_provider, set_active_provider
    from .kimi_provider import invoke_kimi
    from .config import KIMI_TIMEOUT

    provider = get_active_provider()

    # Walk the cascade until we get a response or exhaust all providers
    while provider:
        if provider == "kimi":
            response = await invoke_kimi(
                context=context,
                timeout=KIMI_TIMEOUT,
                interim_callback=interim_callback,
                cost_source=cost_source,
                cost_channel=cost_channel,
                cost_message=cost_message,
            )
            return response, "kimi"

        # Claude provider (cc or cc2)
        config_dir = _get_config_dir_for_provider(provider)
        label = PROVIDER_LABELS.get(provider, provider)

        response = await invoke_claude_cli(
            context=context,
            append_prompt=append_prompt,
            timeout=timeout,
            interim_callback=interim_callback,
            cost_source=cost_source,
            cost_channel=cost_channel,
            cost_message=cost_message,
            config_dir=config_dir,
            max_turns=max_turns,
            model=model,
        )

        # Success — return the response
        if response != CREDIT_EXHAUSTED_SENTINEL:
            return response, provider

        # Credit exhaustion — try next provider in cascade
        next_provider = get_next_provider(provider)
        if next_provider:
            next_label = PROVIDER_LABELS.get(next_provider, next_provider)
            logger.warning(f"{label} credits exhausted — failing over to {next_label}")
            set_active_provider(next_provider, f"auto_failover_from_{provider}")

            if interim_callback:
                try:
                    await interim_callback(f"⚠️ {label} credits exhausted — switching to {next_label}...")
                except Exception:
                    pass

            provider = next_provider
        else:
            # All providers exhausted (shouldn't happen — kimi is terminal)
            logger.error("All providers exhausted")
            return "⚠️ All model providers are currently unavailable. Please try again later.", provider


import re as _re

# Casual opening phrases that indicate conversational reply (not a document)
_CASUAL_PREFIXES = (
    "sure", "here", "hey", "hi ", "ok", "yeah", "yep", "no,", "no ", "yes,",
    "yes ", "i ", "i'", "thanks", "alright", "great", "good", "hmm",
)


def _is_generated_document(response: str) -> bool:
    """Check if a response looks like a generated document worth saving.

    Must meet ALL criteria:
    - Length > DOCUMENT_MIN_LENGTH
    - Contains >= DOCUMENT_MIN_HEADERS markdown headers
    - Does not start with casual conversational phrases
    """
    if len(response) < DOCUMENT_MIN_LENGTH:
        return False

    # Count markdown headers (lines starting with # or ##)
    header_count = len(_re.findall(r"^#{1,3}\s+\S", response, _re.MULTILINE))
    if header_count < DOCUMENT_MIN_HEADERS:
        return False

    # Check first non-empty line for casual phrasing
    first_line = ""
    for line in response.split("\n"):
        stripped = line.strip()
        if stripped:
            first_line = stripped.lower()
            break

    if any(first_line.startswith(p) for p in _CASUAL_PREFIXES):
        return False

    return True


async def _save_document_to_brain(response: str) -> None:
    """Fire-and-forget: save a detected document to Second Brain."""
    try:
        from domains.second_brain import process_capture, CaptureType

        item = await process_capture(
            source=response,
            capture_type=CaptureType.EXPLICIT,
            user_note="[Generated document from conversation]",
            user_tags=["generated", "document"],
            source_system="peterbot:conversation",
        )
        if item:
            logger.info(f"Auto-saved document to Second Brain: {item.id}")
        else:
            logger.debug("Document auto-save returned None (too short or duplicate)")
    except Exception as e:
        logger.warning(f"Failed to auto-save document to Second Brain: {e}")


async def handle_message(
    message: str,
    user_id: int,
    channel_id: int,
    interim_callback: Optional[Callable[[Union[str, dict]], Awaitable[None]]] = None,
    busy_callback: Optional[Callable[[str], Awaitable[None]]] = None,
    attachment_urls: Optional[list[dict]] = None,
    message_id: int | None = None,
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
        # 2. Fetch Second Brain knowledge context (graceful degradation)
        # Single semantic search via surfacing module (has decay filtering,
        # access boosting, and pre-filtering via should_surface)
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
            channel_id,
            channel_name,
            knowledge_context=knowledge_context,
            attachment_urls=attachment_urls,
        )

        # 4. Send to LLM (routes to Claude or Kimi based on active provider)
        response, provider_used = await invoke_llm(
            context=full_context,
            append_prompt=_DEFAULT_APPEND_PROMPT,
            interim_callback=interim_callback,
            cost_source="conversation",
            cost_channel=channel_name,
            cost_message=message,
            max_turns=CLI_MAX_TURNS,
        )

        # Prepend fallback banner if not on primary provider
        if provider_used == "claude_cc2":
            response = f"> *Using secondary account (cc2)*\n\n{response}"
        elif provider_used == "kimi":
            response = f"> **Running in fallback mode (Kimi 2.5)** — Claude credits unavailable\n\n{response}"
    finally:
        # Clean up temp image files regardless of success/failure
        if temp_files:
            _cleanup_temp_files(temp_files)

    # 5. Add response to buffer (per-channel)
    memory.add_to_buffer("assistant", response, channel_id)

    # 6. Capture pair async (fire-and-forget)
    session_id = f"discord-{user_id}"
    task = asyncio.create_task(memory.capture_message_pair(
        session_id, message, response,
        channel_id=str(channel_id),
        message_id=str(message_id) if message_id else None,
    ))
    task.add_done_callback(
        lambda t: logger.info(f"Memory capture completed: {t.exception() or 'success'}")
    )

    # 7. Auto-save generated documents to Second Brain (fire-and-forget)
    if response and _is_generated_document(response):
        logger.info("Document detected in response, auto-saving to Second Brain")
        asyncio.create_task(_save_document_to_brain(response))

    return response if response else "(No response captured)"


def on_startup() -> None:
    """Called on bot startup - clean up orphaned processes."""
    _cleanup_stale_pids()
