"""Vercel usage history for the daily Vercel Usage job — no MCP required.

The `vercel-usage` skill used to read `vercel_usage_history` through the
Supabase MCP inside the jobs-channel session. When that session's MCP servers
fail to start (all four stdio/npx servers timed out after the 2026-09-06 WSL
restart) the job had no data for two mornings running. This endpoint reads the
same table with the service key on the API side, so the skill has a
deterministic primary source and the MCP becomes the fallback.

    GET /vercel/usage-history?days=14

Returns the latest snapshot (every metric on the newest scrape_date) plus a
per-day series for the critical metrics, with limits and percentages already
computed so the skill only has to narrate.
"""
from __future__ import annotations

import os
from collections import defaultdict
from datetime import date, timedelta

import httpx
from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/vercel", tags=["vercel", "peter"])

# Hobby plan limits (rolling 30 days) — mirror of the table in the skill.
LIMITS: dict[str, tuple[float, str]] = {
    "vercel_fluid_active_cpu": (4 * 3600, "seconds"),          # 4 h
    "vercel_fluid_provisioned_memory": (360, "GB-Hrs"),
    "vercel_function_invocations": (1_000_000, "count"),
    "vercel_edge_requests": (1_000_000, "count"),
    "vercel_function_duration": (100, "GB-Hrs"),
    "vercel_edge_request_cpu_duration": (3600, "seconds"),      # 1 h
}
TREND_KEYS = ("vercel_fluid_active_cpu", "vercel_fluid_provisioned_memory")


def _sb() -> tuple[str, dict]:
    url = os.getenv("SUPABASE_URL", "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY", "")
    if not url or not key:
        raise HTTPException(503, "SUPABASE_URL / SUPABASE_KEY not configured")
    return url, {"apikey": key, "Authorization": f"Bearer {key}"}


@router.get("/usage-history")
async def usage_history(days: int = Query(14, ge=1, le=90)):
    url, headers = _sb()
    since = (date.today() - timedelta(days=days)).isoformat()
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{url}/rest/v1/vercel_usage_history",
            params={
                "select": "scrape_date,scraped_at,key,value,unit",
                "scrape_date": f"gte.{since}",
                "order": "scrape_date.asc,key.asc",
                "limit": "5000",
            },
            headers=headers,
        )
    if resp.status_code != 200:
        raise HTTPException(502, f"vercel_usage_history query failed: {resp.text[:200]}")
    rows = resp.json()
    if not rows:
        return {"days": days, "latest_date": None, "snapshot": [], "trend": {}, "note": "no rows in window"}

    latest_date = max(r["scrape_date"] for r in rows)
    snapshot = []
    for r in rows:
        if r["scrape_date"] != latest_date:
            continue
        limit, unit = LIMITS.get(r["key"], (None, r.get("unit")))
        pct = round(float(r["value"]) / limit * 100, 1) if limit else None
        snapshot.append({"key": r["key"], "value": r["value"], "unit": r.get("unit") or unit,
                         "limit": limit, "pct_of_limit": pct})

    series: dict[str, list] = defaultdict(list)
    for r in rows:
        if r["key"] in TREND_KEYS:
            series[r["key"]].append({"date": r["scrape_date"], "value": r["value"]})
    trend = {}
    for k, pts in series.items():
        first, last = pts[0], pts[-1]
        span = max(1, (date.fromisoformat(last["date"]) - date.fromisoformat(first["date"])).days)
        trend[k] = {
            "points": pts,
            "first": first, "last": last,
            "delta": round(float(last["value"]) - float(first["value"]), 2),
            "per_day": round((float(last["value"]) - float(first["value"])) / span, 2),
            "limit": LIMITS.get(k, (None, None))[0],
        }

    scraped_at = max((r.get("scraped_at") or "") for r in rows if r["scrape_date"] == latest_date)
    return {
        "days": days,
        "latest_date": latest_date,
        "scraped_at": scraped_at,
        "stale": latest_date < date.today().isoformat(),
        "snapshot": snapshot,
        "trend": trend,
    }
