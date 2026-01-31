"""Tmux interaction tools for Claude Code sessions.

Supports both Windows (via WSL) and native Linux.
"""

import subprocess
import os
import re
from typing import Optional
from .config import SESSION_PREFIX


def strip_ansi(text: str) -> str:
    """Remove ANSI escape codes and box-drawing characters for cleaner output."""
    # Remove ANSI escape sequences
    ansi_pattern = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]|\x1b\][^\x07]*\x07')
    text = ansi_pattern.sub('', text)
    # Remove common box-drawing characters
    box_chars = '─│┌┐└┘├┤┬┴┼╭╮╯╰═║╔╗╚╝╠╣╦╩╬▐▛▜▌▝▀▄█▓░╌╍┄┅'
    text = ''.join(c if c not in box_chars else ' ' for c in text)
    # Collapse multiple spaces and blank lines
    text = re.sub(r' {2,}', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

# Detect platform - prefix tmux commands with 'wsl' on Windows
IS_WINDOWS = os.name == 'nt'

# Windows: hide console window when running WSL commands
if IS_WINDOWS:
    STARTUPINFO = subprocess.STARTUPINFO()
    STARTUPINFO.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    STARTUPINFO.wShowWindow = subprocess.SW_HIDE
    CREATE_NO_WINDOW = subprocess.CREATE_NO_WINDOW
else:
    STARTUPINFO = None
    CREATE_NO_WINDOW = 0


def _tmux(*args) -> subprocess.CompletedProcess:
    """Run a tmux command, using WSL on Windows."""
    if IS_WINDOWS:
        # Wrap in bash -c and quote ALL args to preserve spaces and special chars
        # Escape single quotes within args by replacing ' with '\''
        def quote_arg(arg):
            escaped = arg.replace("'", "'\\''")
            return f"'{escaped}'"
        cmd = "tmux " + " ".join(quote_arg(arg) for arg in args)
        return subprocess.run(
            ["wsl", "bash", "-c", cmd],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            startupinfo=STARTUPINFO,
            creationflags=CREATE_NO_WINDOW
        )
    else:
        return subprocess.run(
            ["tmux", *args],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace'
        )


def get_sessions() -> list[str]:
    """List active Claude Code tmux sessions."""
    try:
        result = _tmux("list-sessions", "-F", "#{session_name}")
        if result.returncode != 0:
            return []
        return [
            s for s in result.stdout.strip().split("\n")
            if s.startswith(SESSION_PREFIX)
        ]
    except FileNotFoundError:
        return []


def short_name(session: str) -> str:
    """Get display name without prefix."""
    return session.replace(SESSION_PREFIX, "")


def send_prompt(prompt: str, session: Optional[str] = None) -> str:
    """Send a prompt to Claude Code session via tmux."""
    sessions = get_sessions()
    if not sessions:
        return "No active Claude Code sessions"

    target = session if session in sessions else sessions[0]

    # Send the text (literal mode to handle special chars)
    _tmux("send-keys", "-t", target, "-l", prompt)
    # Press enter
    _tmux("send-keys", "-t", target, "Enter")

    return f"**[{short_name(target)}]** Sent"


def get_screen(session: Optional[str] = None, lines: int = 40, clean: bool = True) -> str:
    """Capture recent output from Claude Code session."""
    sessions = get_sessions()
    if not sessions:
        return "No active Claude Code sessions"

    target = session if session in sessions else sessions[0]

    result = _tmux("capture-pane", "-t", target, "-p", "-S", f"-{lines}")

    output = result.stdout.strip()
    if not output:
        output = "(empty)"

    # Clean ANSI codes if requested
    if clean:
        output = strip_ansi(output)

    # Truncate for Discord (2000 char limit minus formatting)
    if len(output) > 1850:
        output = output[-1850:]

    return f"**[{short_name(target)}]**\n```\n{output}\n```"


def start_session(path: str) -> str:
    """Start a new Claude Code session in tmux.

    On Windows:
    - Paths are converted to WSL format
    - Opens a Windows Terminal window attached to the session
    """
    # Handle path conversion for Windows
    if IS_WINDOWS:
        # Convert Windows path to WSL path
        # C:\Users\Chris -> /mnt/c/Users/Chris
        path = path.replace("\\", "/")
        if len(path) > 1 and path[1] == ":":
            drive = path[0].lower()
            path = f"/mnt/{drive}{path[2:]}"

        # Check if path exists in WSL
        check = subprocess.run(
            ["wsl", "test", "-d", path],
            capture_output=True
        )
        if check.returncode != 0:
            return f"Directory not found in WSL: `{path}`"
    else:
        path = os.path.expanduser(path)
        if not os.path.isdir(path):
            return f"Directory not found: `{path}`"

    name = f"{SESSION_PREFIX}{os.path.basename(path)}"

    if name in get_sessions():
        return f"⚠️ Session `{name}` already exists"

    result = _tmux("new-session", "-d", "-s", name, "-c", path)

    if result.returncode != 0:
        return f"❌ Failed to create session: {result.stderr}"

    _tmux("send-keys", "-t", name, "claude", "Enter")

    # On Windows, open Windows Terminal attached to the session
    if IS_WINDOWS:
        try:
            subprocess.Popen(
                ["wt.exe", "wsl", "tmux", "attach", "-t", name],
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
            )
        except FileNotFoundError:
            # wt.exe not available, session still works headless
            pass

    return f"🚀 Started `{name}`"


def stop_session(session: str) -> str:
    """Stop a Claude Code tmux session."""
    if not session.startswith(SESSION_PREFIX):
        session = f"{SESSION_PREFIX}{session}"

    sessions = get_sessions()
    if session not in sessions:
        return f"Session `{session}` not found"

    _tmux("kill-session", "-t", session)
    return f"Stopped `{session}`"


def approve(session: Optional[str] = None) -> str:
    """Send 'y' to approve a permission request."""
    sessions = get_sessions()
    if not sessions:
        return "No active Claude Code sessions"

    target = session if session in sessions else sessions[0]
    _tmux("send-keys", "-t", target, "y")
    return f"**[{short_name(target)}]** Approved"


def deny(session: Optional[str] = None) -> str:
    """Send 'n' to deny a permission request."""
    sessions = get_sessions()
    if not sessions:
        return "No active Claude Code sessions"

    target = session if session in sessions else sessions[0]
    _tmux("send-keys", "-t", target, "n")
    return f"**[{short_name(target)}]** Denied"


def escape(session: Optional[str] = None) -> str:
    """Send Escape key (cancel/interrupt)."""
    sessions = get_sessions()
    if not sessions:
        return "No active Claude Code sessions"

    target = session if session in sessions else sessions[0]
    _tmux("send-keys", "-t", target, "Escape")
    return f"**[{short_name(target)}]** Escaped"


def interrupt(session: Optional[str] = None) -> str:
    """Send Ctrl+C to interrupt Claude Code."""
    sessions = get_sessions()
    if not sessions:
        return "No active Claude Code sessions"

    target = session if session in sessions else sessions[0]
    _tmux("send-keys", "-t", target, "C-c")
    return f"**[{short_name(target)}]** Interrupted (Ctrl+C)"


def scroll_up(session: Optional[str] = None, lines: int = 10) -> str:
    """Scroll up in tmux history and capture output."""
    sessions = get_sessions()
    if not sessions:
        return "No active Claude Code sessions"

    target = session if session in sessions else sessions[0]
    # Capture from further back in history
    result = _tmux("capture-pane", "-t", target, "-p", "-S", f"-{lines + 50}", "-E", f"-{lines}")

    output = result.stdout.strip()
    if not output:
        output = "(no earlier output)"

    output = strip_ansi(output)
    if len(output) > 1850:
        output = output[-1850:]

    return f"**[{short_name(target)}]** (history)\n```\n{output}\n```"


def attach_session(session: Optional[str] = None) -> str:
    """Open a Windows Terminal window attached to an existing tmux session."""
    sessions = get_sessions()
    if not sessions:
        return "No active Claude Code sessions"

    target = session if session in sessions else sessions[0]

    if not IS_WINDOWS:
        return f"Attach only works on Windows. Use `tmux attach -t {target}` directly."

    try:
        subprocess.Popen(
            ["wt.exe", "wsl", "tmux", "attach", "-t", target],
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
        )
        return f"📺 Opened terminal for **[{short_name(target)}]**"
    except FileNotFoundError:
        return "❌ Windows Terminal (wt.exe) not found"


def get_status(session: Optional[str] = None) -> str:
    """Check if Claude is thinking or idle based on screen content."""
    sessions = get_sessions()
    if not sessions:
        return "No active Claude Code sessions"

    target = session if session in sessions else sessions[0]

    # Get the last few lines to check status
    result = _tmux("capture-pane", "-t", target, "-p", "-S", "-5")
    output = result.stdout.strip().lower()

    # Detect various states
    if "thinking" in output or "working" in output or "..." in output:
        status = "🔄 **Thinking**"
    elif "permission" in output or "allow" in output:
        status = "⚠️ **Needs Permission**"
    elif "❯" in result.stdout or ">" in result.stdout:
        status = "✅ **Idle** (ready for input)"
    else:
        status = "❓ **Unknown**"

    return f"**[{short_name(target)}]** {status}"
