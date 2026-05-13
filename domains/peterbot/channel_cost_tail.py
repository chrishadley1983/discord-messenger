"""Tail Claude Code transcript files for the 3 channel sessions and emit
per-turn cost entries to data/channel_costs.jsonl.

Designed to run on Windows (via APScheduler in bot.py), reading WSL
transcripts over the \\wsl.localhost UNC path. Resumes from saved offsets
so each invocation only processes new entries.

Schema of data/channel_costs.jsonl (matches cli_costs.jsonl plus channel_session):
    {
      "timestamp": "2026-05-13T22:00:01.123Z",
      "source": "channel:jobs-channel",
      "channel": "jobs-channel",
      "channel_session": "a8b51d9b-...",
      "model": "claude-opus-4-6",
      "cost_usd": 0.301540,
      "cost_gbp": 0.238217,
      "input_tokens": 3,
      "output_tokens": 24,
      "cache_creation_input_tokens": 9420,
      "cache_read_input_tokens": 11397
    }
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Iterator

from logger import logger
from domains.peterbot.costs import compute_cost

# Project root (parents[2]: domains -> peterbot -> repo root via ../..)
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Where the channel transcripts live. Override with PETERBOT_TRANSCRIPT_DIR
# if WSL distro name or username changes.
DEFAULT_TRANSCRIPT_DIR = r"\\wsl.localhost\Ubuntu\home\chris_hadley\.claude\projects\-home-chris-hadley-peterbot"
TRANSCRIPT_DIR = Path(os.environ.get("PETERBOT_TRANSCRIPT_DIR", DEFAULT_TRANSCRIPT_DIR))

COST_LOG_PATH = PROJECT_ROOT / "data" / "channel_costs.jsonl"
OFFSETS_PATH = PROJECT_ROOT / "data" / "channel_cost_offsets.json"
CHANNEL_CACHE_PATH = PROJECT_ROOT / "data" / "channel_cost_session_map.json"

# Only consider transcripts modified within this many days. Avoids re-scanning
# the hundreds of stale session files left behind from before this tailer existed.
RECENT_DAYS = 7

USD_TO_GBP = 0.79

VALID_CHANNELS = {
    "peter-channel",
    "whatsapp-channel",
    "jobs-channel",
    "jobs-channel-sonnet",
    "extract-channel",
}


def _load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"channel_cost_tail: failed to load {path.name}: {e}")
        return default


def _save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def _identify_channel(file_path: Path, cache: dict) -> str | None:
    """Find the channel source for a transcript file by scanning early entries.

    Returns one of {peter-channel, whatsapp-channel, jobs-channel} or None
    if no channel tag is found (e.g. dev session, non-channel claude run).
    Caches the result in `cache` keyed by session-id (filename stem).
    """
    sid = file_path.stem
    if sid in cache:
        return cache[sid]

    found = None
    try:
        with open(file_path, encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f):
                if i > 1000:  # don't scan forever
                    break
                # Cheap pre-check before JSON parse
                if "channel source=" not in line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                content = obj.get("content") or ""
                if not isinstance(content, str):
                    continue
                marker = '<channel source="'
                idx = content.find(marker)
                if idx == -1:
                    continue
                start = idx + len(marker)
                end = content.find('"', start)
                if end == -1:
                    continue
                candidate = content[start:end]
                if candidate in VALID_CHANNELS:
                    found = candidate
                    break
    except Exception as e:
        logger.warning(f"channel_cost_tail: identify_channel failed for {file_path.name}: {e}")
        return None

    cache[sid] = found
    return found


def _iter_assistant_entries(file_path: Path, start_offset: int) -> Iterator[tuple[int, dict]]:
    """Yield (new_offset, assistant-entry-dict) starting from byte offset.

    Only yields entries with type == 'assistant' and a usage block.
    Returns the byte offset *after* each yielded line so the caller can
    persist progress incrementally.
    """
    try:
        with open(file_path, "rb") as f:
            f.seek(start_offset)
            while True:
                line = f.readline()
                if not line:
                    return
                new_offset = f.tell()
                try:
                    obj = json.loads(line)
                except Exception:
                    yield new_offset, None  # advance offset even on parse failure
                    continue
                if obj.get("type") != "assistant":
                    yield new_offset, None
                    continue
                msg = obj.get("message") or {}
                if not isinstance(msg, dict) or not msg.get("usage"):
                    yield new_offset, None
                    continue
                yield new_offset, obj
    except FileNotFoundError:
        return
    except Exception as e:
        logger.warning(f"channel_cost_tail: read failed for {file_path.name}: {e}")
        return


def _process_file(
    file_path: Path,
    channel: str,
    start_offset: int,
    out_fh,
) -> tuple[int, int, float]:
    """Process new entries in a single transcript file.

    Returns (new_offset, entries_written, total_cost_usd).
    """
    entries_written = 0
    total_cost = 0.0
    end_offset = start_offset

    for new_offset, obj in _iter_assistant_entries(file_path, start_offset):
        end_offset = new_offset
        if obj is None:
            continue
        msg = obj["message"]
        usage = msg.get("usage") or {}
        model = msg.get("model") or "unknown"
        cost_usd = compute_cost(model, usage)
        if cost_usd <= 0:
            continue
        entry = {
            "timestamp": obj.get("timestamp") or datetime.utcnow().isoformat() + "Z",
            "source": f"channel:{channel}",
            "channel": channel,
            "channel_session": obj.get("sessionId") or file_path.stem,
            "model": model,
            "cost_usd": round(cost_usd, 6),
            "cost_gbp": round(cost_usd * USD_TO_GBP, 6),
            "input_tokens": usage.get("input_tokens", 0) or 0,
            "output_tokens": usage.get("output_tokens", 0) or 0,
            "cache_creation_input_tokens": usage.get("cache_creation_input_tokens", 0) or 0,
            "cache_read_input_tokens": usage.get("cache_read_input_tokens", 0) or 0,
        }
        out_fh.write(json.dumps(entry) + "\n")
        entries_written += 1
        total_cost += cost_usd

    return end_offset, entries_written, total_cost


def tail_all(max_files: int = 50) -> dict:
    """Process all recently-modified transcript files in TRANSCRIPT_DIR.

    Returns a summary dict suitable for logging:
        {
          "files_scanned": int,
          "entries_written": int,
          "cost_usd": float,
          "per_channel": {channel: {"entries": int, "cost_usd": float}},
        }
    """
    if not TRANSCRIPT_DIR.exists():
        logger.warning(f"channel_cost_tail: transcript dir not found: {TRANSCRIPT_DIR}")
        return {"files_scanned": 0, "entries_written": 0, "cost_usd": 0.0, "per_channel": {}}

    offsets = _load_json(OFFSETS_PATH, {})
    channel_cache = _load_json(CHANNEL_CACHE_PATH, {})

    cutoff = time.time() - RECENT_DAYS * 86400
    candidates = []
    for p in TRANSCRIPT_DIR.glob("*.jsonl"):
        try:
            mtime = p.stat().st_mtime
        except OSError:
            continue
        if mtime >= cutoff:
            candidates.append((mtime, p))
    # Process oldest-first so offsets advance in a predictable order
    candidates.sort()
    if len(candidates) > max_files:
        candidates = candidates[-max_files:]

    COST_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    summary = {
        "files_scanned": 0,
        "entries_written": 0,
        "cost_usd": 0.0,
        "per_channel": {},
    }

    with open(COST_LOG_PATH, "a", encoding="utf-8") as out_fh:
        for _, fp in candidates:
            channel = _identify_channel(fp, channel_cache)
            if channel is None:
                # Mark as scanned (so we don't re-identify next run) but skip cost write.
                offsets[fp.name] = fp.stat().st_size
                continue
            summary["files_scanned"] += 1
            start_offset = offsets.get(fp.name, 0)
            # Handle file truncation/replacement defensively
            try:
                size = fp.stat().st_size
            except OSError:
                continue
            if start_offset > size:
                logger.warning(
                    f"channel_cost_tail: {fp.name} shrank ({start_offset}→{size}); resetting offset"
                )
                start_offset = 0
            new_offset, written, cost = _process_file(fp, channel, start_offset, out_fh)
            offsets[fp.name] = new_offset
            summary["entries_written"] += written
            summary["cost_usd"] += cost
            ch_stats = summary["per_channel"].setdefault(channel, {"entries": 0, "cost_usd": 0.0})
            ch_stats["entries"] += written
            ch_stats["cost_usd"] += cost

    _save_json(OFFSETS_PATH, offsets)
    _save_json(CHANNEL_CACHE_PATH, channel_cache)

    if summary["entries_written"]:
        logger.info(
            f"channel_cost_tail: {summary['entries_written']} new turns | "
            f"${summary['cost_usd']:.4f} | per-channel={summary['per_channel']}"
        )
    return summary


if __name__ == "__main__":
    # Manual run for testing
    import sys
    s = tail_all()
    print(json.dumps(s, indent=2))
    sys.exit(0)
