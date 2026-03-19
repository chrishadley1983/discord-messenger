"""Unified Log Aggregation API for Peter Dashboard.

This module provides endpoints for aggregating and querying logs
from multiple sources: Discord bot, Hadley API, Peter Dashboard,
and job execution outputs.

Features:
- Unified log view across all sources
- Filtering by source, level, time range, and text search
- Log source statistics
- Quick tail view for specific sources
- Error aggregation across all sources
- Performance-optimized lazy loading for large files
- Log volume histogram (F1)
- Pattern grouping with traceback merging (F4, F9)
- Faceted filtering (F3)
- Context view for surrounding logs (F6)
- Noise suppression (F10)

Usage:
    from peter_dashboard.api.logs import router
    app.include_router(router, prefix="/api/logs")
"""

import os
import re
import uuid
import mmap
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any
from collections import defaultdict
from functools import lru_cache
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo
from math import ceil

from fastapi import APIRouter, Query, HTTPException

# UK timezone for timestamps
UK_TZ = ZoneInfo("Europe/London")

# Create router
router = APIRouter(tags=["Logs"])

# Configuration
PROJECT_ROOT = Path(__file__).parent.parent.parent
LOGS_DIR = PROJECT_ROOT / "logs"

# Log sources configuration
LOG_SOURCES = {
    "discord_bot": {
        "pattern": "discord_bot-*.log",
        "display_name": "Discord Bot",
        "description": "Discord bot process logs"
    },
    "hadley_api": {
        "pattern": "hadley_api-*.log",
        "display_name": "Hadley API",
        "description": "REST API server logs"
    },
    "peter_dashboard": {
        "pattern": "peter_dashboard-*.log",
        "display_name": "Peter Dashboard",
        "description": "Dashboard web server logs"
    },
    "bot": {
        "pattern": "bot.log",
        "display_name": "Bot (Legacy)",
        "description": "Legacy bot log file"
    }
}

# Cache for file stats (30 second TTL)
_file_stats_cache: Dict[str, tuple[datetime, dict]] = {}
CACHE_TTL_SECONDS = 30

# Log level mapping
LOG_LEVELS = {
    "DEBUG": 10,
    "INFO": 20,
    "WARNING": 30,
    "WARN": 30,
    "ERROR": 40,
    "CRITICAL": 50
}

# =============================================================================
# Noise Patterns (F10)
# =============================================================================
NOISE_PATTERNS = [
    re.compile(r'GET /health', re.IGNORECASE),
    re.compile(r'GET /api/status', re.IGNORECASE),
    re.compile(r'RequestsDependencyWarning', re.IGNORECASE),
    re.compile(r'BigQuery billing unavailable', re.IGNORECASE),
    re.compile(r'discord\.gateway.*RESUMED', re.IGNORECASE),
    re.compile(r'Heartbeat.*acknowledged', re.IGNORECASE),
    re.compile(r'urllib3.*or chardet.*doesn\'t match', re.IGNORECASE),
]

# Traceback detection pattern
TRACEBACK_START = re.compile(r'Traceback \(most recent call last\)')
TRACEBACK_FRAME = re.compile(r'^\s+File ".*", line \d+')
TRACEBACK_CONT = re.compile(r'^\s+\S')  # indented continuation lines


def _is_noise(message: str) -> bool:
    """Check if a log message matches known noise patterns."""
    for pattern in NOISE_PATTERNS:
        if pattern.search(message):
            return True
    return False


def normalize_message(message: str) -> str:
    """Normalize a log message for grouping by stripping variable parts.

    Used by both /unified?group=true and /errors for consistent grouping.
    """
    normalized = message
    # Strip IP:port
    normalized = re.sub(r'\d+\.\d+\.\d+\.\d+:\d+', '<IP>', normalized)
    # Strip UUIDs
    normalized = re.sub(
        r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',
        '<UUID>', normalized, flags=re.I
    )
    # Strip hex IDs (8+ chars)
    normalized = re.sub(r'\b[0-9a-f]{8,}\b', '<ID>', normalized, flags=re.I)
    # Strip port numbers
    normalized = re.sub(r':\d{4,5}\b', ':<PORT>', normalized)
    # Strip numeric sequences (but keep short ones like status codes)
    normalized = re.sub(r'\b\d{6,}\b', '<NUM>', normalized)
    # Truncate for grouping key
    return normalized[:120]


@dataclass
class LogEntry:
    """Represents a parsed log entry."""
    id: str
    timestamp: datetime
    source: str
    level: str
    message: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    raw_line: str = ""
    extra_lines: List[str] = field(default_factory=list)
    noise: bool = False
    group_key: str = ""
    group_count: int = 1
    group_entries: List[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        result = {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "source": self.source,
            "level": self.level,
            "message": self.message,
            "metadata": self.metadata,
            "noise": self.noise,
        }
        if self.extra_lines:
            result["extra_lines"] = self.extra_lines
            result["traceback_frames"] = len([
                l for l in self.extra_lines if TRACEBACK_FRAME.match(l)
            ])
        if self.group_key:
            result["group_key"] = self.group_key
        if self.group_count > 1:
            result["group_count"] = self.group_count
            result["group_entries"] = self.group_entries
        return result


class LogParser:
    """Parser for various log formats."""

    # Pattern for standard Python logging format
    # Example: [2026-02-04 14:47:49] [INFO    ] discord.client: logging in
    VALID_LEVELS = {'DEBUG', 'INFO', 'WARNING', 'WARN', 'ERROR', 'CRITICAL', 'FATAL', 'FUTURE'}

    PYTHON_LOG_PATTERN = re.compile(
        r'^\[?(\d{4}-\d{2}-\d{2}[\sT]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?)\]?\s*'
        r'\[?\s*(DEBUG|INFO|WARNING|WARN|ERROR|CRITICAL|FATAL|FUTURE)\s*\]?\s*'
        r'(?:(\S+?):\s*)?'
        r'(.+?)$',
        re.MULTILINE
    )

    # Pattern for uvicorn/FastAPI format
    # Example: INFO:     127.0.0.1:60842 - "GET /health HTTP/1.1" 200 OK
    UVICORN_PATTERN = re.compile(
        r'^(INFO|WARNING|ERROR|DEBUG|CRITICAL):\s+(.+)$'
    )

    # Pattern for ANSI escape codes (to strip)
    ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

    @classmethod
    def parse_line(cls, line: str, source: str, line_number: int = 0) -> Optional[LogEntry]:
        """Parse a single log line into a LogEntry."""
        if not line or not line.strip():
            return None

        # Strip ANSI codes
        line = cls.ANSI_ESCAPE.sub('', line)

        # Skip progress bars and similar noise
        if any(x in line for x in ['Loading weights:', '|#', 'Materializing param=']):
            return None

        # Try Python logging format first
        match = cls.PYTHON_LOG_PATTERN.match(line)
        if match:
            timestamp_str, level, module, message = match.groups()
            try:
                # Parse timestamp
                timestamp = None
                for fmt in [
                    "%Y-%m-%d %H:%M:%S,%f",
                    "%Y-%m-%d %H:%M:%S.%f",
                    "%Y-%m-%d %H:%M:%S",
                    "%Y-%m-%dT%H:%M:%S"
                ]:
                    try:
                        timestamp = datetime.strptime(timestamp_str, fmt)
                        # Add timezone info
                        timestamp = timestamp.replace(tzinfo=UK_TZ)
                        break
                    except ValueError:
                        continue

                if timestamp is None:
                    timestamp = datetime.now(UK_TZ)

                entry = LogEntry(
                    id=str(uuid.uuid4())[:8],
                    timestamp=timestamp,
                    source=source,
                    level=level.upper().strip(),
                    message=message.strip(),
                    metadata={"module": module} if module else {},
                    raw_line=line
                )
                entry.noise = _is_noise(entry.message)
                entry.group_key = normalize_message(entry.message)
                return entry
            except Exception:
                pass

        # Try uvicorn format
        match = cls.UVICORN_PATTERN.match(line)
        if match:
            level, message = match.groups()
            # Extract timestamp from message if present
            timestamp = datetime.now(UK_TZ)

            # Parse HTTP request details if present
            metadata = {}
            http_match = re.search(
                r'(\d+\.\d+\.\d+\.\d+):(\d+)\s+-\s+"(\w+)\s+([^\s]+)\s+HTTP/[\d.]+"'
                r'\s+(\d+)',
                message
            )
            if http_match:
                ip, port, method, path, status = http_match.groups()
                metadata = {
                    "ip": ip,
                    "port": port,
                    "method": method,
                    "path": path,
                    "status": int(status)
                }

            entry = LogEntry(
                id=str(uuid.uuid4())[:8],
                timestamp=timestamp,
                source=source,
                level=level.upper(),
                message=message.strip(),
                metadata=metadata,
                raw_line=line
            )
            entry.noise = _is_noise(entry.message)
            entry.group_key = normalize_message(entry.message)
            return entry

        # Fallback: treat as INFO level message
        entry = LogEntry(
            id=str(uuid.uuid4())[:8],
            timestamp=datetime.now(UK_TZ),
            source=source,
            level="INFO",
            message=line.strip(),
            raw_line=line
        )
        entry.noise = _is_noise(entry.message)
        entry.group_key = normalize_message(entry.message)
        return entry


def _get_log_files(source: Optional[str] = None) -> List[tuple[str, Path]]:
    """Get all log files, optionally filtered by source.

    Returns list of (source_name, file_path) tuples.
    """
    files = []

    if not LOGS_DIR.exists():
        return files

    sources_to_check = {source: LOG_SOURCES[source]} if source and source in LOG_SOURCES else LOG_SOURCES

    for src_name, config in sources_to_check.items():
        pattern = config["pattern"]
        for log_file in LOGS_DIR.glob(pattern):
            if log_file.is_file():
                files.append((src_name, log_file))

    # Also check for bot.log in project root
    bot_log = PROJECT_ROOT / "bot.log"
    if bot_log.exists() and (source is None or source == "bot"):
        files.append(("bot", bot_log))

    return files


def _get_file_stats(file_path: Path) -> dict:
    """Get file statistics with caching."""
    cache_key = str(file_path)
    now = datetime.now()

    if cache_key in _file_stats_cache:
        cached_time, cached_stats = _file_stats_cache[cache_key]
        if (now - cached_time).total_seconds() < CACHE_TTL_SECONDS:
            return cached_stats

    try:
        stat = file_path.stat()

        # Count lines efficiently
        line_count = 0
        try:
            with open(file_path, 'rb') as f:
                # Use memory mapping for large files
                if stat.st_size > 0:
                    if stat.st_size > 1024 * 1024:  # > 1MB, use mmap
                        with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                            line_count = mm.count(b'\n')
                    else:
                        line_count = f.read().count(b'\n')
        except Exception:
            line_count = 0

        stats = {
            "size_bytes": stat.st_size,
            "last_modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "line_count": line_count
        }

        _file_stats_cache[cache_key] = (now, stats)
        return stats
    except Exception:
        return {"size_bytes": 0, "last_modified": None, "line_count": 0}


def _read_file_lines(file_path: Path, max_lines: int = 500, from_end: bool = True) -> List[str]:
    """Read lines from a file efficiently.

    Args:
        file_path: Path to the log file
        max_lines: Maximum number of lines to read
        from_end: If True, read last N lines; if False, read first N lines
    """
    lines = []
    try:
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            if from_end:
                # Read from end - use deque for efficiency
                from collections import deque
                lines = list(deque(f, maxlen=max_lines))
            else:
                # Read from beginning
                for i, line in enumerate(f):
                    if i >= max_lines:
                        break
                    lines.append(line)
    except Exception:
        pass

    return lines


def _read_all_lines(file_path: Path) -> List[str]:
    """Read all lines from a file. Used for histogram/facet endpoints."""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            return f.readlines()
    except Exception:
        return []


def _merge_tracebacks(entries: List[LogEntry]) -> List[LogEntry]:
    """Merge multi-line traceback blocks into their preceding error entry.

    Detects 'Traceback (most recent call last):' blocks and attaches
    all frame lines + final exception line to the preceding ERROR entry.
    """
    if not entries:
        return entries

    merged = []
    i = 0
    while i < len(entries):
        entry = entries[i]

        # Check if this entry starts a traceback
        if TRACEBACK_START.search(entry.message):
            # Collect all traceback continuation lines
            tb_lines = [entry.raw_line]
            j = i + 1
            while j < len(entries):
                next_entry = entries[j]
                raw = next_entry.raw_line
                # Traceback continuation: indented lines (File "...", code lines, exception)
                if (TRACEBACK_FRAME.match(raw) or
                        TRACEBACK_CONT.match(raw) or
                        raw.strip().startswith('File "') or
                        (not LogParser.PYTHON_LOG_PATTERN.match(raw) and raw.strip())):
                    tb_lines.append(raw)
                    j += 1
                else:
                    break

            # Find the preceding ERROR entry to attach to
            if merged and merged[-1].level in ("ERROR", "CRITICAL"):
                merged[-1].extra_lines = tb_lines
            else:
                # No preceding error - keep traceback as its own entry
                entry.extra_lines = tb_lines[1:]  # skip the "Traceback..." line itself
                entry.level = "ERROR"
                merged.append(entry)
            i = j
            continue

        merged.append(entry)
        i += 1

    return merged


def _group_consecutive(entries: List[LogEntry]) -> List[LogEntry]:
    """Group consecutive entries with the same group_key into single entries.

    Returns a new list where consecutive same-group entries are collapsed
    with group_count and group_entries populated.
    """
    if not entries:
        return entries

    grouped = []
    current = entries[0]
    current_members = []

    for entry in entries[1:]:
        if (entry.group_key == current.group_key and
                entry.source == current.source and
                not entry.extra_lines and not current.extra_lines):
            # Same group - accumulate
            current.group_count += 1
            current_members.append({
                "id": entry.id,
                "timestamp": entry.timestamp.isoformat() if entry.timestamp else None,
                "message": entry.message,
            })
        else:
            # Different group - flush current
            if current_members:
                current.group_entries = current_members
            grouped.append(current)
            current = entry
            current_members = []

    # Flush last entry
    if current_members:
        current.group_entries = current_members
    grouped.append(current)

    return grouped


def _parse_logs_from_file(
    file_path: Path,
    source: str,
    level_filter: Optional[List[str]] = None,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    search: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
) -> tuple[List[LogEntry], int]:
    """Parse logs from a single file with filtering.

    Returns (entries, total_matching).
    """
    entries = []
    total_matching = 0
    skipped = 0

    # Read more lines than needed to account for filtering
    max_lines = (limit + offset) * 3
    lines = _read_file_lines(file_path, max_lines=max_lines, from_end=True)

    # Reverse to get chronological order
    lines.reverse()

    for line in lines:
        entry = LogParser.parse_line(line.strip(), source)
        if not entry:
            continue

        # Apply filters
        if level_filter and entry.level not in level_filter:
            continue

        if since and entry.timestamp and entry.timestamp < since:
            continue

        if until and entry.timestamp and entry.timestamp > until:
            continue

        if search and search.lower() not in entry.message.lower():
            continue

        total_matching += 1

        # Handle pagination
        if skipped < offset:
            skipped += 1
            continue

        if len(entries) < limit:
            entries.append(entry)

    return entries, total_matching


def _parse_all_entries(
    source_filter: Optional[str] = None,
    level_filter: Optional[List[str]] = None,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    search: Optional[str] = None,
    max_per_file: int = 2000,
) -> List[LogEntry]:
    """Parse entries from all files with filtering but no pagination.

    Used by histogram, facets, and grouping endpoints that need full data.
    """
    log_files = _get_log_files(source_filter)
    all_entries = []

    for src_name, file_path in log_files:
        lines = _read_file_lines(file_path, max_lines=max_per_file, from_end=True)
        lines.reverse()

        for line in lines:
            entry = LogParser.parse_line(line.strip(), src_name)
            if not entry:
                continue

            if level_filter and entry.level not in level_filter:
                continue

            if since and entry.timestamp and entry.timestamp < since:
                continue

            if until and entry.timestamp and entry.timestamp > until:
                continue

            if search and search.lower() not in entry.message.lower():
                continue

            all_entries.append(entry)

    # Sort chronologically
    min_dt = datetime.min.replace(tzinfo=UK_TZ)
    all_entries.sort(
        key=lambda e: e.timestamp.replace(tzinfo=UK_TZ) if e.timestamp and e.timestamp.tzinfo is None
            else (e.timestamp or min_dt)
    )

    return all_entries


# =============================================================================
# API Endpoints
# =============================================================================

@router.get("/unified")
async def get_unified_logs(
    source: Optional[str] = Query(None, description="Filter by source (discord_bot, hadley_api, peter_dashboard, bot)"),
    level: Optional[str] = Query(None, description="Filter by level (DEBUG, INFO, WARNING, ERROR)"),
    since: Optional[str] = Query(None, description="ISO timestamp - only logs after this time"),
    until: Optional[str] = Query(None, description="ISO timestamp - only logs before this time"),
    search: Optional[str] = Query(None, description="Text search in log messages"),
    limit: int = Query(100, ge=1, le=500, description="Max results (default 100, max 500)"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    group: bool = Query(False, description="Group consecutive similar entries"),
    suppress_noise: bool = Query(False, description="Flag noise entries"),
) -> dict:
    """Get aggregated logs from all sources with filtering.

    Returns logs from all configured sources (Discord bot, Hadley API,
    Peter Dashboard) merged and sorted by timestamp.

    Additional params:
    - group: Collapse consecutive identical messages (F4)
    - suppress_noise: Flag entries matching NOISE_PATTERNS (F10)
    """
    # Parse filters
    level_filter = None
    if level:
        level_filter = [l.upper().strip() for l in level.split(',')]

    since_dt = None
    until_dt = None
    try:
        if since:
            since_dt = datetime.fromisoformat(since.replace('Z', '+00:00'))
        if until:
            until_dt = datetime.fromisoformat(until.replace('Z', '+00:00'))
    except ValueError as e:
        raise HTTPException(400, f"Invalid timestamp format: {e}")

    # Get log files
    log_files = _get_log_files(source)

    if not log_files:
        return {"logs": [], "total": 0, "has_more": False}

    # Collect entries from all sources
    all_entries: List[LogEntry] = []
    total_count = 0

    for src_name, file_path in log_files:
        entries, count = _parse_logs_from_file(
            file_path=file_path,
            source=src_name,
            level_filter=level_filter,
            since=since_dt,
            until=until_dt,
            search=search,
            limit=limit * 2,  # Get more than needed for merging
            offset=0
        )
        all_entries.extend(entries)
        total_count += count

    # Sort by timestamp (most recent first)
    min_dt = datetime.min.replace(tzinfo=UK_TZ)
    all_entries.sort(
        key=lambda e: e.timestamp.replace(tzinfo=UK_TZ) if e.timestamp and e.timestamp.tzinfo is None
            else (e.timestamp or min_dt),
        reverse=True
    )

    # Merge tracebacks (F9)
    all_entries = _merge_tracebacks(all_entries)

    # Group consecutive similar entries (F4)
    if group:
        all_entries = _group_consecutive(all_entries)

    # Apply final pagination
    paginated_entries = all_entries[offset:offset + limit]

    return {
        "logs": [e.to_dict() for e in paginated_entries],
        "total": total_count,
        "has_more": (offset + limit) < len(all_entries)
    }


@router.get("/histogram")
async def get_log_histogram(
    hours: int = Query(6, ge=1, le=48, description="Hours to look back (default 6)"),
    buckets: int = Query(60, ge=10, le=120, description="Number of time buckets (default 60)"),
    source: Optional[str] = Query(None, description="Filter by source"),
) -> dict:
    """Get log volume histogram for the stacked bar chart (F1).

    Returns array of time buckets with severity counts per bucket.
    """
    now = datetime.now(UK_TZ)
    since = now - timedelta(hours=hours)
    bucket_duration = timedelta(hours=hours) / buckets

    # Initialize buckets
    histogram = []
    for i in range(buckets):
        bucket_start = since + (bucket_duration * i)
        histogram.append({
            "timestamp": bucket_start.isoformat(),
            "counts": {"DEBUG": 0, "INFO": 0, "WARNING": 0, "ERROR": 0}
        })

    # Parse entries from all files
    entries = _parse_all_entries(
        source_filter=source,
        since=since,
        max_per_file=5000,
    )

    for entry in entries:
        if not entry.timestamp:
            continue

        ts = entry.timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UK_TZ)

        # Calculate bucket index
        elapsed = (ts - since).total_seconds()
        bucket_idx = min(int(elapsed / bucket_duration.total_seconds()), buckets - 1)
        if 0 <= bucket_idx < buckets:
            level = entry.level
            if level in ("CRITICAL", "ERROR"):
                histogram[bucket_idx]["counts"]["ERROR"] += 1
            elif level in ("WARNING", "WARN"):
                histogram[bucket_idx]["counts"]["WARNING"] += 1
            elif level == "DEBUG":
                histogram[bucket_idx]["counts"]["DEBUG"] += 1
            else:
                histogram[bucket_idx]["counts"]["INFO"] += 1

    return {
        "histogram": histogram,
        "hours": hours,
        "buckets": buckets,
        "bucket_seconds": int(bucket_duration.total_seconds()),
    }


@router.get("/facets")
async def get_log_facets(
    hours: int = Query(6, ge=1, le=48, description="Hours to look back"),
    source: Optional[str] = Query(None, description="Filter by source"),
    level: Optional[str] = Query(None, description="Filter by level"),
) -> dict:
    """Get faceted counts for sources, levels, and top patterns (F3)."""
    since = datetime.now(UK_TZ) - timedelta(hours=hours)

    level_filter = None
    if level:
        level_filter = [l.upper().strip() for l in level.split(',')]

    entries = _parse_all_entries(
        source_filter=source,
        level_filter=level_filter,
        since=since,
        max_per_file=3000,
    )

    # Aggregate counts
    source_counts: Dict[str, int] = defaultdict(int)
    level_counts: Dict[str, int] = defaultdict(int)
    pattern_counts: Dict[str, dict] = defaultdict(lambda: {"count": 0, "sample": ""})

    for entry in entries:
        source_counts[entry.source] += 1

        lvl = entry.level
        if lvl in ("WARN",):
            lvl = "WARNING"
        if lvl in ("CRITICAL",):
            lvl = "ERROR"
        level_counts[lvl] += 1

        key = normalize_message(entry.message)
        pattern_counts[key]["count"] += 1
        if not pattern_counts[key]["sample"]:
            pattern_counts[key]["sample"] = entry.message[:200]

    # Build response
    sources = [
        {"name": s, "display_name": LOG_SOURCES.get(s, {}).get("display_name", s), "count": c}
        for s, c in sorted(source_counts.items(), key=lambda x: -x[1])
    ]

    levels = [
        {"name": l, "count": c}
        for l, c in sorted(level_counts.items(), key=lambda x: -LOG_LEVELS.get(x[0], 0))
    ]

    top_patterns = sorted(pattern_counts.values(), key=lambda x: -x["count"])[:10]
    patterns = [
        {"pattern": p["sample"][:100], "count": p["count"], "sample": p["sample"]}
        for p in top_patterns
    ]

    return {
        "sources": sources,
        "levels": levels,
        "top_patterns": patterns,
    }


@router.get("/context")
async def get_log_context(
    source: str = Query(..., description="Log source name"),
    timestamp: str = Query(..., description="ISO timestamp of the target log entry"),
    lines: int = Query(5, ge=1, le=20, description="Lines before/after"),
) -> dict:
    """Get surrounding log lines for context (F6).

    Returns N lines before and after the given timestamp from the same source.
    """
    try:
        target_ts = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
    except ValueError as e:
        raise HTTPException(400, f"Invalid timestamp: {e}")

    log_files = _get_log_files(source)
    if not log_files:
        return {"before": [], "after": [], "source": source}

    # Parse all entries from this source
    all_entries = []
    for src_name, file_path in log_files:
        file_lines = _read_file_lines(file_path, max_lines=2000, from_end=True)
        file_lines.reverse()
        for line in file_lines:
            entry = LogParser.parse_line(line.strip(), src_name)
            if entry:
                all_entries.append(entry)

    # Sort chronologically
    min_dt = datetime.min.replace(tzinfo=UK_TZ)
    all_entries.sort(
        key=lambda e: e.timestamp.replace(tzinfo=UK_TZ) if e.timestamp and e.timestamp.tzinfo is None
            else (e.timestamp or min_dt)
    )

    # Find closest entry to target timestamp
    closest_idx = 0
    min_diff = float('inf')
    for i, entry in enumerate(all_entries):
        if entry.timestamp:
            ts = entry.timestamp
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=UK_TZ)
            diff = abs((ts - target_ts).total_seconds())
            if diff < min_diff:
                min_diff = diff
                closest_idx = i

    # Extract context window
    start = max(0, closest_idx - lines)
    end = min(len(all_entries), closest_idx + lines + 1)

    before = [e.to_dict() for e in all_entries[start:closest_idx]]
    after = [e.to_dict() for e in all_entries[closest_idx + 1:end]]

    return {
        "before": before,
        "target": all_entries[closest_idx].to_dict() if all_entries else None,
        "after": after,
        "source": source,
    }


@router.get("/sources")
async def get_log_sources() -> dict:
    """Get available log sources and their stats."""
    sources = []

    for src_name, config in LOG_SOURCES.items():
        # Find most recent file for this source
        files = list(LOGS_DIR.glob(config["pattern"])) if LOGS_DIR.exists() else []

        if files:
            # Get most recent file
            files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
            most_recent = files[0]
            stats = _get_file_stats(most_recent)

            sources.append({
                "name": src_name,
                "display_name": config["display_name"],
                "description": config["description"],
                "file": str(most_recent.relative_to(PROJECT_ROOT)),
                "file_count": len(files),
                **stats
            })
        else:
            sources.append({
                "name": src_name,
                "display_name": config["display_name"],
                "description": config["description"],
                "file": None,
                "file_count": 0,
                "size_bytes": 0,
                "last_modified": None,
                "line_count": 0
            })

    # Check for bot.log in project root
    bot_log = PROJECT_ROOT / "bot.log"
    if bot_log.exists():
        stats = _get_file_stats(bot_log)
        sources.append({
            "name": "bot",
            "display_name": "Bot (Legacy)",
            "description": "Legacy bot log file",
            "file": "bot.log",
            "file_count": 1,
            **stats
        })

    return {"sources": sources}


@router.get("/tail")
async def get_log_tail(
    source: str = Query(..., description="Log source name"),
    lines: int = Query(50, ge=1, le=500, description="Number of lines to return (default 50)")
) -> dict:
    """Get the last N lines from a specific source."""
    if source not in LOG_SOURCES and source != "bot":
        raise HTTPException(400, f"Unknown source: {source}. Valid sources: {list(LOG_SOURCES.keys())}")

    # Get log files for this source
    log_files = _get_log_files(source)

    if not log_files:
        return {"source": source, "lines": [], "message": "No log files found"}

    # Use most recent file
    _, most_recent_file = max(log_files, key=lambda x: x[1].stat().st_mtime)

    # Read lines
    raw_lines = _read_file_lines(most_recent_file, max_lines=lines, from_end=True)

    # Parse lines
    parsed_lines = []
    for line in raw_lines:
        entry = LogParser.parse_line(line.strip(), source)
        if entry:
            parsed_lines.append({
                "timestamp": entry.timestamp.isoformat() if entry.timestamp else None,
                "level": entry.level,
                "message": entry.message
            })

    return {
        "source": source,
        "file": str(most_recent_file.name),
        "lines": parsed_lines
    }


@router.get("/errors")
async def get_recent_errors(
    hours: int = Query(24, ge=1, le=168, description="Hours to look back (default 24, max 168)")
) -> dict:
    """Get recent errors across all sources."""
    since = datetime.now(UK_TZ) - timedelta(hours=hours)

    # Get all log files
    log_files = _get_log_files()

    # Collect all errors
    error_map: Dict[str, dict] = defaultdict(lambda: {
        "count": 0,
        "first_seen": None,
        "last_seen": None,
        "source": None,
        "sample_message": None
    })

    total_errors = 0

    for src_name, file_path in log_files:
        entries, _ = _parse_logs_from_file(
            file_path=file_path,
            source=src_name,
            level_filter=["ERROR", "CRITICAL", "WARN", "WARNING"],
            since=since,
            limit=1000,
            offset=0
        )

        for entry in entries:
            total_errors += 1

            key_message = normalize_message(entry.message)
            key = f"{entry.source}:{key_message}"

            error_info = error_map[key]
            error_info["count"] += 1
            error_info["source"] = entry.source
            error_info["sample_message"] = entry.message

            if entry.timestamp:
                if error_info["first_seen"] is None or entry.timestamp < error_info["first_seen"]:
                    error_info["first_seen"] = entry.timestamp
                if error_info["last_seen"] is None or entry.timestamp > error_info["last_seen"]:
                    error_info["last_seen"] = entry.timestamp

    # Convert to list and sort by count
    errors_list = []
    for key, info in error_map.items():
        errors_list.append({
            "source": info["source"],
            "message": info["sample_message"],
            "count": info["count"],
            "first_seen": info["first_seen"].isoformat() if info["first_seen"] else None,
            "last_seen": info["last_seen"].isoformat() if info["last_seen"] else None
        })

    errors_list.sort(key=lambda x: x["count"], reverse=True)

    return {
        "errors": errors_list[:50],  # Top 50 error patterns
        "total_errors": total_errors,
        "hours_covered": hours
    }


@router.get("/stats")
async def get_log_stats() -> dict:
    """Get overall log statistics."""
    total_files = 0
    total_size = 0
    by_source: Dict[str, dict] = {}

    for src_name, config in LOG_SOURCES.items():
        files = list(LOGS_DIR.glob(config["pattern"])) if LOGS_DIR.exists() else []
        source_size = sum(f.stat().st_size for f in files if f.exists())

        by_source[src_name] = {
            "files": len(files),
            "size_bytes": source_size,
            "display_name": config["display_name"]
        }

        total_files += len(files)
        total_size += source_size

    # Check bot.log
    bot_log = PROJECT_ROOT / "bot.log"
    if bot_log.exists():
        bot_size = bot_log.stat().st_size
        by_source["bot"] = {
            "files": 1,
            "size_bytes": bot_size,
            "display_name": "Bot (Legacy)"
        }
        total_files += 1
        total_size += bot_size

    # Get recent activity stats (sampling for performance)
    now = datetime.now(UK_TZ)
    one_hour_ago = now - timedelta(hours=1)
    twenty_four_hours_ago = now - timedelta(hours=24)

    logs_1h = 0
    logs_24h = 0
    errors_24h = 0

    # Sample from most recent files
    for src_name, file_path in _get_log_files():
        entries, _ = _parse_logs_from_file(
            file_path=file_path,
            source=src_name,
            since=twenty_four_hours_ago,
            limit=500,
            offset=0
        )

        for entry in entries:
            if entry.timestamp:
                logs_24h += 1
                if entry.timestamp >= one_hour_ago:
                    logs_1h += 1
                if entry.level in ("ERROR", "CRITICAL"):
                    errors_24h += 1

    return {
        "total_files": total_files,
        "total_size_bytes": total_size,
        "by_source": by_source,
        "recent_activity": {
            "logs_1h": logs_1h,
            "logs_24h": logs_24h,
            "errors_24h": errors_24h
        }
    }
