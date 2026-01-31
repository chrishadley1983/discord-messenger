#!/usr/bin/env python3
"""
Single-instance bot launcher.
Ensures only one bot.py process runs at a time.
Logs startup/skip to bot.log.
"""
import os
import sys
import subprocess
from datetime import datetime
from pathlib import Path

BOT_DIR = Path(__file__).parent
LOCK_FILE = BOT_DIR / "bot.lock"
LOG_FILE = BOT_DIR / "bot.log"


def log(message: str):
    """Append timestamped message to bot.log."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {message}\n")


def is_process_running(pid: int) -> bool:
    """Check if a process with given PID is running."""
    try:
        # Windows-specific check
        import ctypes
        kernel32 = ctypes.windll.kernel32
        SYNCHRONIZE = 0x00100000
        handle = kernel32.OpenProcess(SYNCHRONIZE, False, pid)
        if handle:
            kernel32.CloseHandle(handle)
            return True
        return False
    except Exception:
        return False


def get_existing_bot_pid() -> int | None:
    """Check if bot is already running via lock file."""
    if LOCK_FILE.exists():
        try:
            pid = int(LOCK_FILE.read_text().strip())
            if is_process_running(pid):
                return pid
            # Stale lock file - remove it
            LOCK_FILE.unlink()
        except (ValueError, OSError):
            # Invalid lock file - remove it
            try:
                LOCK_FILE.unlink()
            except OSError:
                pass
    return None


def main():
    os.chdir(BOT_DIR)

    # Check for existing instance
    existing_pid = get_existing_bot_pid()
    if existing_pid:
        log(f"Bot already running (PID: {existing_pid}) - skipping startup")
        print(f"Bot already running (PID: {existing_pid})")
        sys.exit(0)

    # Start the bot
    log("Starting Discord-Messenger Bot...")

    # Start bot.py as subprocess, redirect output to log
    with open(LOG_FILE, "a", encoding="utf-8") as log_handle:
        process = subprocess.Popen(
            [sys.executable, "bot.py"],
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            cwd=BOT_DIR,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )

    # Write PID to lock file
    LOCK_FILE.write_text(str(process.pid))
    log(f"Bot started with PID: {process.pid}")
    print(f"Bot started (PID: {process.pid})")


if __name__ == "__main__":
    main()
