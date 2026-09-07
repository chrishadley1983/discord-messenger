"""Scan Claude Code channel transcripts for MCP servers that failed to start.

Runs INSIDE WSL (``python3 /mnt/c/.../channel_mcp_scan.py``) because the
transcripts live on the ext4 side; pure stdlib so it works with the distro
python. Also imported on Windows by the tests and by
``channel_mcp_watchdog`` for the decision logic.

Every channel session (peter / whatsapp / jobs / jobs-sonnet / extract) runs
with cwd ``~/peterbot``, so all of their transcripts share one project dir.
A transcript identifies its channel, looking only at its HEAD (the injected
channel message is the first user turn), by the injected
``<channel source="…">`` tag, then its ``mcp__<name>__reply`` tool calls, then
the ``server:<name>`` banner. Only the head is used so that a transcript that
merely *mentions* another channel later (or reads this file) is never
misattributed.

MCP startup failures surface in the transcript as the note ToolSearch appends
to its tool_result::

    "content":"No matching deferred tools found. Note: these configured MCP
    servers failed to connect, so their tools are unavailable for this session:
    playwright (CONNECT_TIMEOUT): \"MCP server playwright connection timed out
    after 30000ms\"; \ncontext7 (CONNECT_TIMEOUT): ..."

Only that note, anchored at the start of a tool_result content string, counts.
The same words inside a Read of this file / the tests / a scraper's output are
numbered lines in the middle of a content string and do not match.

Output: one JSON object per transcript (see ``parse_file``). Results are cached
per (path, size, mtime) in /tmp so a multi-MB transcript is only re-read when
it changes.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime

CHANNEL_NAMES = ("peter-channel", "whatsapp-channel", "jobs-channel",
                 "jobs-channel-sonnet", "extract-channel")
# The <channel source="…"> value each server injects (whatsapp differs).
SOURCE_TAGS = {
    "peter-channel": "peter-channel",
    "whatsapp-channel": "whatsapp",
    "jobs-channel": "jobs-channel",
    "jobs-channel-sonnet": "jobs-channel-sonnet",
    "extract-channel": "extract-channel",
}
HEAD_LINES = 300
CACHE_PATH = "/tmp/channel_mcp_scan_cache.json"

# ToolSearch's failure note, anchored at the start of a tool_result content
# string so the words in a Read/Grep result never count.
_NOTE_RE = re.compile(
    r'"content":"(?:No matching deferred tools found\. )?'
    r'Note: these configured MCP servers failed to connect, so their tools are '
    r'unavailable for this session: '
)
# Server names inside the note: "playwright (CONNECT_TIMEOUT): …". Entries are
# separated by "; " and a literal backslash-n (two characters) in the raw
# file, so anchor on those separators or "\nplaywright" reads as "nplaywright".
_SERVER_RE = re.compile(r"(?:^|\s|;|:|\\n)([A-Za-z0-9_-]+) \((?:CONNECT_TIMEOUT|CONNECT_ERROR)\):")
_TS_RE = re.compile(r'"timestamp":"([^"]+)"')


def _iso_to_epoch(ts: str) -> float | None:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def identify_channel(head: str) -> str | None:
    """Channel name from the transcript head, strongest marker first."""
    names = sorted(CHANNEL_NAMES, key=len, reverse=True)
    for name in names:
        if f'source=\\"{SOURCE_TAGS[name]}\\"' in head:
            return name
    for name in names:
        if f"mcp__{name}__reply" in head:
            return name
    for name in names:  # longest first: "server:jobs-channel" prefixes the sonnet name
        if f"server:{name}" in head:
            return name
    return None


def failed_servers(text: str) -> list[str]:
    """Server names from every genuine ToolSearch failure note in the text."""
    servers: list[str] = []
    for m in _NOTE_RE.finditer(text):
        window = text[m.end(): m.end() + 4000]
        # the note ends at the content string's closing quote (an unescaped ")
        end = re.search(r'(?<!\\)"', window)
        note = window[: end.start()] if end else window
        for s in _SERVER_RE.findall(note):
            if s and s not in servers:
                servers.append(s)
    return servers


def parse_text(text: str) -> dict:
    """Pure parser over the raw transcript text."""
    head = "\n".join(text.splitlines()[:HEAD_LINES])
    m = _TS_RE.search(head)
    servers = failed_servers(text)
    return {
        "channel": identify_channel(head),
        "first_ts": _iso_to_epoch(m.group(1)) if m else None,
        "mcp_failed": bool(servers) or bool(_NOTE_RE.search(text)),
        "failed_servers": servers,
    }


def parse_file(path: str) -> dict:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    out = parse_text(text)
    st = os.stat(path)
    out.update({"file": os.path.basename(path), "session_id": os.path.basename(path).rsplit(".", 1)[0],
                "mtime": st.st_mtime, "size": st.st_size})
    return out


def _load_cache() -> dict:
    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_cache(cache: dict) -> None:
    try:
        tmp = CACHE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cache, f)
        os.replace(tmp, CACHE_PATH)
    except OSError:
        pass


def scan_dir(directory: str, max_age_h: float = 36.0, use_cache: bool = True) -> list[dict]:
    cutoff = time.time() - max_age_h * 3600
    rows: list[dict] = []
    try:
        names = os.listdir(directory)
    except OSError:
        return rows
    cache = _load_cache() if use_cache else {}
    fresh: dict = {}
    for n in names:
        if not n.endswith(".jsonl"):
            continue
        p = os.path.join(directory, n)
        try:
            st = os.stat(p)
            if st.st_mtime < cutoff:
                continue
            key = f"{p}|{st.st_size}|{st.st_mtime}"
            row = cache.get(key)
            if row is None:
                row = parse_file(p)
            fresh[key] = row
            rows.append(row)
        except OSError:
            continue
    if use_cache:
        _save_cache(fresh)
    return rows


if __name__ == "__main__":
    d = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/.claude/projects/-home-chris-hadley-peterbot")
    hours = float(sys.argv[2]) if len(sys.argv) > 2 else 36.0
    print(json.dumps(scan_dir(d, hours)))
