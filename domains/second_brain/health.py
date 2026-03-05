"""Second Brain health monitoring.

Provides a single get_health_report() that runs all diagnostic queries
and returns a HealthReport dataclass. Used by:
- admin.py CLI (health subcommand)
- bot.py scheduler (daily check + weekly digest)
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from config import SUPABASE_URL, SUPABASE_KEY
from logger import logger
from .config import (
    SEARCH_MIN_DECAY,
    HEALTH_PENDING_WARN,
    HEALTH_ORPHANED_WARN,
    HEALTH_DECAY_CRITICAL_PCT,
    HEALTH_EMBED_FAIL_RATE,
)
from .db import (
    _get_http_client,
    _get_headers,
    _get_rest_url,
    get_total_active_count,
    get_total_connection_count,
    get_most_accessed_item_since,
)
from .embed import get_embedding_stats
from .types import KnowledgeItem


@dataclass
class HealthReport:
    """Complete health diagnostic for the Second Brain."""
    # Totals
    total_active: int
    total_connections: int

    # Pending items (embedding failures stuck in PENDING)
    pending_count: int
    pending_items: list[KnowledgeItem]

    # Orphaned items (ACTIVE but zero chunks — unsearchable)
    orphaned_count: int
    orphaned_items: list[KnowledgeItem]

    # Decay distribution
    decay_below_02: int
    decay_02_to_05: int
    decay_above_05: int

    # Embedding pipeline stats (in-memory counters, reset on bot restart)
    embedding_stats: dict

    # Connection coverage
    items_with_zero_connections: int
    connection_type_breakdown: dict[str, int]

    # Recent capture success rate (last 7 days)
    items_created_7d: int
    items_pending_7d: int

    # Timestamps
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Diagnostic queries
# ---------------------------------------------------------------------------

async def _query_pending_items() -> tuple[int, list[KnowledgeItem]]:
    """Q1: Get pending items count and first 5 for display."""
    try:
        client = _get_http_client()
        response = await client.get(
            f"{_get_rest_url()}/knowledge_items"
            f"?status=eq.pending&select=id,title,created_at,content_type,capture_type,"
            f"source_url,full_text,summary,topics,base_priority,decay_score,"
            f"access_count,last_accessed_at,status"
            f"&order=created_at.desc&limit=5",
            headers={**_get_headers(), "Prefer": "count=exact"},
        )
        response.raise_for_status()
        count = int(response.headers.get("content-range", "0-0/0").split("/")[-1])
        items = [KnowledgeItem.from_db_row(row) for row in response.json()]
        return count, items
    except Exception as e:
        logger.error(f"Health: pending items query failed: {e}")
        return 0, []


async def _query_orphaned_items() -> tuple[int, list[KnowledgeItem]]:
    """Q2: Get orphaned items via RPC (active but zero chunks)."""
    try:
        client = _get_http_client()
        response = await client.post(
            f"{_get_rest_url()}/rpc/get_orphaned_items",
            headers=_get_headers(),
            json={"item_limit": 5},
        )
        response.raise_for_status()
        data = response.json()
        items = [KnowledgeItem.from_db_row(row) for row in data]
        # RPC returns up to 5; for count, query separately
        count_resp = await client.post(
            f"{_get_rest_url()}/rpc/get_orphaned_items",
            headers=_get_headers(),
            json={"item_limit": 10000},
        )
        count_resp.raise_for_status()
        count = len(count_resp.json())
        return count, items
    except Exception as e:
        logger.error(f"Health: orphaned items query failed: {e}")
        return 0, []


async def _query_decay_distribution() -> tuple[int, int, int]:
    """Q3: Get decay score distribution via RPC."""
    try:
        client = _get_http_client()
        response = await client.post(
            f"{_get_rest_url()}/rpc/get_decay_distribution",
            headers=_get_headers(),
            json={},
        )
        response.raise_for_status()
        data = response.json()
        buckets = {row["bucket"]: int(row["item_count"]) for row in data}
        return (
            buckets.get("below_02", 0),
            buckets.get("02_to_05", 0),
            buckets.get("above_05", 0),
        )
    except Exception as e:
        logger.error(f"Health: decay distribution query failed: {e}")
        return 0, 0, 0


async def _query_connection_coverage() -> tuple[int, dict[str, int]]:
    """Q5: Get connection coverage via RPC."""
    try:
        client = _get_http_client()
        response = await client.post(
            f"{_get_rest_url()}/rpc/get_connection_coverage",
            headers=_get_headers(),
            json={},
        )
        response.raise_for_status()
        data = response.json()
        no_connections = 0
        type_breakdown: dict[str, int] = {}
        for row in data:
            if row["metric"] == "items_no_connections":
                no_connections = int(row["value"])
            else:
                type_breakdown[row["metric"]] = int(row["value"])
        return no_connections, type_breakdown
    except Exception as e:
        logger.error(f"Health: connection coverage query failed: {e}")
        return 0, {}


async def _query_recent_capture_rate() -> tuple[int, int]:
    """Q6: Items created in last 7 days and how many are still pending."""
    seven_days_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    try:
        client = _get_http_client()
        # All items created in last 7 days
        resp1 = await client.get(
            f"{_get_rest_url()}/knowledge_items"
            f"?created_at=gte.{seven_days_ago}&select=id&limit=1",
            headers={**_get_headers(), "Prefer": "count=exact"},
        )
        resp1.raise_for_status()
        total_7d = int(resp1.headers.get("content-range", "0-0/0").split("/")[-1])

        # Still pending from last 7 days
        resp2 = await client.get(
            f"{_get_rest_url()}/knowledge_items"
            f"?created_at=gte.{seven_days_ago}&status=eq.pending&select=id&limit=1",
            headers={**_get_headers(), "Prefer": "count=exact"},
        )
        resp2.raise_for_status()
        pending_7d = int(resp2.headers.get("content-range", "0-0/0").split("/")[-1])

        return total_7d, pending_7d
    except Exception as e:
        logger.error(f"Health: recent capture rate query failed: {e}")
        return 0, 0


# ---------------------------------------------------------------------------
# Main report builder
# ---------------------------------------------------------------------------

async def get_health_report() -> HealthReport:
    """Run all health diagnostics and return a populated HealthReport."""
    import asyncio

    # Run independent queries concurrently
    (
        total_active,
        total_connections,
        (pending_count, pending_items),
        (orphaned_count, orphaned_items),
        (decay_below_02, decay_02_to_05, decay_above_05),
        (no_connections, type_breakdown),
        (items_created_7d, items_pending_7d),
    ) = await asyncio.gather(
        get_total_active_count(),
        get_total_connection_count(),
        _query_pending_items(),
        _query_orphaned_items(),
        _query_decay_distribution(),
        _query_connection_coverage(),
        _query_recent_capture_rate(),
    )

    embed_stats = get_embedding_stats()

    return HealthReport(
        total_active=total_active,
        total_connections=total_connections,
        pending_count=pending_count,
        pending_items=pending_items,
        orphaned_count=orphaned_count,
        orphaned_items=orphaned_items,
        decay_below_02=decay_below_02,
        decay_02_to_05=decay_02_to_05,
        decay_above_05=decay_above_05,
        embedding_stats=embed_stats,
        items_with_zero_connections=no_connections,
        connection_type_breakdown=type_breakdown,
        items_created_7d=items_created_7d,
        items_pending_7d=items_pending_7d,
    )


# ---------------------------------------------------------------------------
# Warning detection
# ---------------------------------------------------------------------------

def _get_warnings(report: HealthReport) -> list[str]:
    """Return list of warning strings for breached thresholds."""
    warnings = []

    if report.pending_count > HEALTH_PENDING_WARN:
        warnings.append(f":warning: {report.pending_count} pending items (embedding failures)")

    if report.orphaned_count > HEALTH_ORPHANED_WARN:
        warnings.append(f":warning: {report.orphaned_count} orphaned item(s) (active but unsearchable)")

    total_decay = report.decay_below_02 + report.decay_02_to_05 + report.decay_above_05
    if total_decay > 0:
        below_pct = (report.decay_below_02 / total_decay) * 100
        if below_pct > HEALTH_DECAY_CRITICAL_PCT:
            warnings.append(
                f":chart_with_downwards_trend: {below_pct:.0f}% of items below search threshold (decay < 0.2)"
            )

    stats = report.embedding_stats
    total_attempts = (
        stats.get("edge_ok", 0) + stats.get("edge_fail", 0)
        + stats.get("hf_single_ok", 0) + stats.get("hf_single_fail", 0)
    )
    if total_attempts > 0:
        fail_rate = (stats.get("edge_fail", 0) + stats.get("hf_single_fail", 0)) / total_attempts * 100
        if fail_rate > HEALTH_EMBED_FAIL_RATE:
            warnings.append(f":warning: Embedding failure rate {fail_rate:.0f}% (session)")

    return warnings


# ---------------------------------------------------------------------------
# Discord formatters
# ---------------------------------------------------------------------------

def format_daily_discord(report: HealthReport) -> str:
    """Format health report as a compact daily Discord message."""
    warnings = _get_warnings(report)

    if not warnings:
        return f":white_check_mark: Second Brain healthy — {report.total_active} items, {report.total_connections} connections"

    lines = [":brain: **Second Brain Health Check**", ""]
    lines.extend(warnings)
    lines.append("")
    lines.append(f"Totals: {report.total_active} items | {report.total_connections} connections")
    return "\n".join(lines)


def format_weekly_discord(report: HealthReport, digest_data=None) -> str:
    """Format health report as a detailed weekly Discord message.

    Args:
        report: HealthReport from get_health_report()
        digest_data: Optional DigestData from generate_weekly_digest()
    """
    lines = [":brain: **Weekly Second Brain Health Digest**", ""]

    # Overview
    lines.append("**Overview**")
    new_this_week = report.items_created_7d
    lines.append(
        f"{report.total_active} active items | {report.total_connections} connections | "
        f"{new_this_week} new this week"
    )
    lines.append("")

    # Decay distribution
    total_decay = report.decay_below_02 + report.decay_02_to_05 + report.decay_above_05
    if total_decay > 0:
        lines.append("**Decay Distribution**")
        pct = lambda n: f"{n / total_decay * 100:.0f}%"
        lines.append(f":green_circle: Healthy (>0.5): {report.decay_above_05} ({pct(report.decay_above_05)})")
        lines.append(f":yellow_circle: Fading (0.2-0.5): {report.decay_02_to_05} ({pct(report.decay_02_to_05)})")
        lines.append(f":red_circle: Below threshold (<0.2): {report.decay_below_02} ({pct(report.decay_below_02)})")
        lines.append("")

    # Connections
    connected = report.total_active - report.items_with_zero_connections
    if report.total_active > 0:
        coverage_pct = connected / report.total_active * 100
        lines.append("**Connections**")
        lines.append(
            f"Coverage: {connected}/{report.total_active} items connected ({coverage_pct:.0f}%)"
        )
        if report.connection_type_breakdown:
            types_str = " | ".join(
                f"{t} {c}" for t, c in sorted(report.connection_type_breakdown.items())
            )
            lines.append(f"By type: {types_str}")
        lines.append("")

    # Most accessed (from digest data if available)
    if digest_data and digest_data.most_accessed_item:
        item = digest_data.most_accessed_item
        title = item.title[:50] if item.title else "Untitled"
        lines.append("**Most Accessed This Week**")
        lines.append(f":star: {title} ({item.access_count} accesses)")
        lines.append("")

    # Fading items (from digest data if available)
    if digest_data and digest_data.fading_items:
        lines.append("**Faded Below Threshold**")
        for item in digest_data.fading_items[:5]:
            title = item.title[:50] if item.title else "Untitled"
            lines.append(f"- {title} (decay {item.decay_score:.2f})")
        lines.append("")

    # Embedding pipeline
    stats = report.embedding_stats
    total_attempts = (
        stats.get("edge_ok", 0) + stats.get("edge_fail", 0)
        + stats.get("hf_single_ok", 0) + stats.get("hf_single_fail", 0)
    )
    if total_attempts > 0:
        lines.append("**Embedding Pipeline** (since last restart)")
        lines.append(f"Edge function: {stats.get('edge_ok', 0)} ok / {stats.get('edge_fail', 0)} fail")
        lines.append(f"HuggingFace: {stats.get('hf_single_ok', 0)} ok / {stats.get('hf_single_fail', 0)} fail")
        lines.append(f"Retries: {stats.get('retries', 0)} | Cache hits: {stats.get('cache_hits', 0)}")
        lines.append("")

    # New this week
    lines.append("**New This Week**")
    active_7d = report.items_created_7d - report.items_pending_7d
    lines.append(f":inbox_tray: {report.items_created_7d} items captured ({active_7d} active, {report.items_pending_7d} pending)")
    if digest_data and digest_data.new_connections:
        lines.append(f":link: {len(digest_data.new_connections)} new connections discovered")
    lines.append("")

    # Quiet week message
    if report.items_created_7d == 0:
        lines.append("No new items or connections this week.")
        lines.append("Use `/save` to capture knowledge!")
        lines.append("")

    lines.append("---")
    lines.append("Next digest: Sunday 9:00 AM")

    return "\n".join(lines)
