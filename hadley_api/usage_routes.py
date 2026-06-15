"""AI API-usage audit + reconciliation endpoints.

Reads the shared ``ai_api_usage`` table (every project's raw Anthropic-API-key
calls) and ``ai_usage_reconciliation`` (daily diff vs Anthropic's Admin usage
report). See domains/api_usage/audit_log.py and domains/api_usage/reconcile.py.

  GET  /usage/audit?hours=24        — logged spend, broken down by project/feature/model
  GET  /usage/reconcile?days=7      — latest reconciliation rows + any gaps
  POST /usage/reconcile/run?days=3  — run reconciliation now (needs ANTHROPIC_ADMIN_KEY)
"""

from __future__ import annotations

import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, Query

from hadley_api.auth import require_auth
from logger import logger

router = APIRouter(prefix="/usage", tags=["usage"])

_SUPABASE_URL = (os.getenv("SUPABASE_URL") or "").rstrip("/")
_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""


def _sb_get(table: str, params: dict) -> list[dict]:
    if not _SUPABASE_URL or not _SERVICE_KEY:
        return []
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.get(
                f"{_SUPABASE_URL}/rest/v1/{table}",
                headers={"apikey": _SERVICE_KEY, "Authorization": f"Bearer {_SERVICE_KEY}"},
                params=params,
            )
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.warning(f"usage_routes: read {table} failed: {e}")
        return []


@router.get("/audit", dependencies=[Depends(require_auth)])
async def usage_audit(hours: int = Query(24, ge=1, le=24 * 90)):
    """Logged Anthropic-API-key spend for the window, by project / feature / model."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    rows = _sb_get("ai_api_usage", {
        "select": "project,feature,model,input_tokens,output_tokens,cost_usd,status,created_at",
        "created_at": f"gte.{cutoff}",
        "limit": "200000",
    })

    def _bucket():
        return {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}

    by_project, by_feature, by_model = defaultdict(_bucket), defaultdict(_bucket), defaultdict(_bucket)
    total = _bucket()
    errors = 0
    for r in rows:
        cost = float(r.get("cost_usd") or 0.0)
        inp, out = int(r.get("input_tokens") or 0), int(r.get("output_tokens") or 0)
        if r.get("status") == "error":
            errors += 1
        for key, store in ((r.get("project") or "?", by_project),
                           (r.get("feature") or "?", by_feature),
                           (r.get("model") or "?", by_model)):
            b = store[key]
            b["calls"] += 1
            b["input_tokens"] += inp
            b["output_tokens"] += out
            b["cost_usd"] += cost
        total["calls"] += 1
        total["input_tokens"] += inp
        total["output_tokens"] += out
        total["cost_usd"] += cost

    def _fmt(d):
        return dict(sorted(
            ((k, {**v, "cost_usd": round(v["cost_usd"], 4)}) for k, v in d.items()),
            key=lambda kv: kv[1]["cost_usd"], reverse=True))

    total["cost_usd"] = round(total["cost_usd"], 4)
    return {
        "window_hours": hours,
        "total": total,
        "errors": errors,
        "by_project": _fmt(by_project),
        "by_feature": _fmt(by_feature),
        "by_model": _fmt(by_model),
        "note": "Estimated cost (client-side rates). Anthropic cost_report is the source of truth — see /usage/reconcile.",
    }


@router.get("/reconcile", dependencies=[Depends(require_auth)])
async def usage_reconcile(days: int = Query(7, ge=1, le=90)):
    """Latest reconciliation rows (Anthropic truth vs logged), highlighting gaps."""
    since = (datetime.now(timezone.utc).date() - timedelta(days=days)).isoformat()
    rows = _sb_get("ai_usage_reconciliation", {
        "select": "*",
        "usage_date": f"gte.{since}",
        "order": "usage_date.desc,gap_output_tokens.desc",
        "limit": "5000",
    })
    gaps = [r for r in rows if r.get("api_key_id") == "shared" and (r.get("gap_output_tokens") or 0) > 0]
    console = [r for r in rows if r.get("api_key_id") == "console"]
    return {
        "days": days,
        "rows": len(rows),
        "gaps": gaps[:50],
        "console_rows": len(console),
        "note": "Empty rows mean reconciliation hasn't run yet (needs ANTHROPIC_ADMIN_KEY). "
                "'console' rows are Workbench/manual usage with no api_key_id — expected, not a gap.",
    }


@router.post("/reconcile/run", dependencies=[Depends(require_auth)])
async def usage_reconcile_run(days: int = Query(3, ge=1, le=31)):
    """Run reconciliation now (used by the scheduler too)."""
    import asyncio

    from domains.api_usage.reconcile import reconcile

    result = await asyncio.to_thread(reconcile, days)
    return result
