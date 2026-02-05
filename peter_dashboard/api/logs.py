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

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "source": self.source,
            "level": self.level,
            "message": self.message,
            "metadata": self.metadata
        }


class LogParser:
    """Parser for various log formats."""

    # Pattern for standard Python logging format
    # Example: [2026-02-04 14:47:49] [INFO    ] discord.client: logging in
    PYTHON_LOG_PATTERN = re.compile(
        r'^\[?(\d{4}-\d{2}-\d{2}[\sT]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?)\]?\s*'
        r'\[?\s*(\w+)\s*\]?\s*'
        r'(?:(\S+?):\s*)?'
        r'(.+?)$',
        re.MULTILINE
    )

    # Pattern for uvicorn/FastAPI format
    # Example: INFO:     127.0.0.1:60842 - "GET /health HTTP/1.1" 200 OK
    UVICORN_PATTERN = re.compile(
        r'^(\w+):\s+(.+)$'
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

                return LogEntry(
                    id=str(uuid.uuid4())[:8],
                    timestamp=timestamp,
                    source=source,
                    level=level.upper().strip(),
                    message=message.strip(),
                    metadata={"module": module} if module else {},
                    raw_line=line
                )
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

            return LogEntry(
                id=str(uuid.uuid4())[:8],
                timestamp=timestamp,
                source=source,
                level=level.upper(),
                message=message.strip(),
                metadata=metadata,
                raw_line=line
            )

        # Fallback: treat as INFO level message
        return LogEntry(
            id=str(uuid.uuid4())[:8],
            timestamp=datetime.now(UK_TZ),
            source=source,
            level="INFO",
            message=line.strip(),
            raw_line=line
        )


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
    offset: int = Query(0, ge=0, description="Pagination offset")
) -> dict:
    """Get aggregated logs from all sources with filtering.

    Returns logs from all configured sources (Discord bot, Hadley API,
    Peter Dashboard) merged and sorted by timestamp.

    Query Parameters:
    - source: Filter by source (discord_bot, hadley_api, peter_dashboard, bot)
    - level: Filter by level (DEBUG, INFO, WARNING, ERROR)
    - since: ISO timestamp, only logs after this time
    - until: ISO timestamp, only logs before this time
    - search: Text search in log messages
    - limit: Max results (default 100, max 500)
    - offset: Pagination offset

    Returns:
    ```json
    {
      "logs": [
        {
          "id": "uuid",
          "timestamp": "2026-02-05T12:00:00Z",
          "source": "discord_bot",
          "level": "INFO",
          "message": "Message received from #peterbot",
          "metadata": {}
        }
      ],
      "total": 1000,
      "has_more": true
    }
    ```
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
    # Use timezone-aware minimum datetime for comparison
    min_dt = datetime.min.replace(tzinfo=UK_TZ)
    all_entries.sort(
        key=lambda e: e.timestamp.replace(tzinfo=UK_TZ) if e.timestamp and e.timestamp.tzinfo is None
            else (e.timestamp or min_dt),
        reverse=True
    )

    # Apply final pagination
    paginated_entries = all_entries[offset:offset + limit]

    return {
        "logs": [e.to_dict() for e in paginated_entries],
        "total": total_count,
        "has_more": (offset + limit) < total_count
    }


@router.get("/sources")
async def get_log_sources() -> dict:
    """Get available log sources and their stats.

    Returns information about each log source including file size,
    last modified time, and line count.

    Returns:
    ```json
    {
      "sources": [
        {
          "name": "discord_bot",
          "display_name": "Discord Bot",
          "file": "logs/discord_bot-20260205.log",
          "size_bytes": 1234567,
          "last_modified": "2026-02-05T12:00:00Z",
          "line_count": 5000
        }
      ]
    }
    ```
    """
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
    """Get the last N lines from a specific source.

    Provides quick access to recent log entries for a specific source
    without full parsing and filtering.

    Query Parameters:
    - source: Log source name (required)
    - lines: Number of lines to return (default 50, max 500)

    Returns:
    ```json
    {
      "source": "discord_bot",
      "lines": [
        {"timestamp": "...", "level": "INFO", "message": "..."}
      ]
    }
    ```
    """
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
    """Get recent errors across all sources.

    Aggregates error-level log entries from the specified time period
    and groups them by message pattern to show frequency.

    Query Parameters:
    - hours: Hours to look back (default 24, max 168 = 1 week)

    Returns:
    ```json
    {
      "errors": [
        {
          "timestamp": "...",
          "source": "hadley_api",
          "message": "Connection refused to database",
          "count": 3,
          "first_seen": "...",
          "last_seen": "..."
        }
      ],
      "total_errors_24h": 15
    }
    ```
    """
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

            # Create a simplified key for grouping similar errors
            # Remove specific values like IDs, timestamps, ports
            key_message = re.sub(r'\d+\.\d+\.\d+\.\d+:\d+', '<IP>', entry.message)
            key_message = re.sub(r':\d+', ':<PORT>', key_message)
            key_message = re.sub(r'\b[0-9a-f]{8,}\b', '<ID>', key_message, flags=re.I)
            key_message = key_message[:100]  # Truncate for grouping

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
    """Get overall log statistics.

    Returns summary statistics about log volume and error rates
    across all sources.

    Returns:
    ```json
    {
      "total_files": 15,
      "total_size_bytes": 12345678,
      "by_source": {
        "discord_bot": {"files": 5, "size_bytes": 1234567},
        "hadley_api": {"files": 5, "size_bytes": 2345678}
      },
      "recent_activity": {
        "logs_1h": 150,
        "logs_24h": 5000,
        "errors_24h": 12
      }
    }
    ```
    """
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
