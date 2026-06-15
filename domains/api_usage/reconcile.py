"""Reconcile the shared ``ai_api_usage`` audit log against Anthropic's truth.

For each (day × model) it compares:
  * **Anthropic** Admin usage_report (ground truth), split into keyed usage
    (the shared API key) vs ``console`` (Workbench, ``api_key_id`` is null and
    so unattributable to any project), and
  * the **sum of our logged calls** (``ai_api_usage`` where billing_source='api_key').

The gap (Anthropic − logged) on the keyed bucket is the signal: a positive gap
means un-instrumented usage — a project/call-site not yet wired. Results upsert
into ``ai_usage_reconciliation``; a gap over threshold alerts #alerts.

Run manually:  ``python -m domains.api_usage.reconcile --days 3``
Scheduled daily via domains/api_usage/schedules.py.
"""

from __future__ import annotations

import os
import threading
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import httpx

from logger import logger
from domains.api_usage.services import anthropic_admin

_SUPABASE_URL = (os.getenv("SUPABASE_URL") or "").rstrip("/")
_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
_USAGE_TABLE = "ai_api_usage"
_RECON_TABLE = "ai_usage_reconciliation"

# Alert when a day's keyed output-token gap exceeds this (tokens) AND >25% of truth.
_GAP_TOKEN_THRESHOLD = 5000
_GAP_PCT_THRESHOLD = 25.0


def _sb_headers(extra: Optional[dict] = None) -> dict:
    h = {
        "apikey": _SERVICE_KEY,
        "Authorization": f"Bearer {_SERVICE_KEY}",
        "Content-Type": "application/json",
    }
    if extra:
        h.update(extra)
    return h


def _fetch_logged(start: date) -> dict[tuple, dict]:
    """Sum logged api_key calls by (usage_date, model) from start (inclusive)."""
    out: dict[tuple, dict] = defaultdict(lambda: {"input": 0, "output": 0, "cost": 0.0})
    if not _SUPABASE_URL or not _SERVICE_KEY:
        return out
    params = {
        "select": "created_at,model,input_tokens,output_tokens,cost_usd,billing_source",
        "created_at": f"gte.{start.isoformat()}",
        "billing_source": "eq.api_key",
        "limit": "200000",
    }
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.get(f"{_SUPABASE_URL}/rest/v1/{_USAGE_TABLE}",
                              headers=_sb_headers(), params=params)
            resp.raise_for_status()
            rows = resp.json()
    except Exception as e:
        logger.warning(f"reconcile: failed reading {_USAGE_TABLE}: {e}")
        return out
    for r in rows:
        day = (r.get("created_at") or "")[:10]
        model = r.get("model") or "unknown"
        b = out[(day, model)]
        b["input"] += int(r.get("input_tokens") or 0)
        b["output"] += int(r.get("output_tokens") or 0)
        b["cost"] += float(r.get("cost_usd") or 0.0)
    return out


def _upsert_recon(rows: list[dict]) -> bool:
    if not rows or not _SUPABASE_URL or not _SERVICE_KEY:
        return False
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.post(
                f"{_SUPABASE_URL}/rest/v1/{_RECON_TABLE}",
                headers=_sb_headers({"Prefer": "resolution=merge-duplicates,return=minimal"}),
                params={"on_conflict": "usage_date,model,api_key_id"},
                json=rows,
            )
            resp.raise_for_status()
        return True
    except Exception as e:
        logger.warning(f"reconcile: upsert to {_RECON_TABLE} failed: {e}")
        return False


def reconcile(days: int = 3) -> dict:
    """Pull Anthropic truth + logged sums for the last `days`, compute & store gaps.

    Returns a summary dict; if the Admin key is missing it returns
    ``{"available": False, ...}`` so callers can skip quietly.
    """
    end = datetime.now(timezone.utc).date() + timedelta(days=1)   # exclusive
    start = end - timedelta(days=days + 1)

    usage = anthropic_admin.fetch_usage(start, end)
    if not usage.get("available"):
        return {"available": False, "note": usage.get("note", "admin key missing")}
    cost = anthropic_admin.fetch_cost(start, end)
    cost_by_dm = cost.get("by_day_model", {})

    # Aggregate Anthropic rows into keyed ('shared') vs 'console' buckets.
    truth: dict[tuple, dict] = defaultdict(
        lambda: {"input": 0, "output": 0, "cache_create": 0, "cache_read": 0})
    for r in usage["rows"]:
        bucket = "console" if r["api_key_id"] == "console" else "shared"
        t = truth[(r["usage_date"], r["model"], bucket)]
        t["input"] += r["input_tokens"]
        t["output"] += r["output_tokens"]
        t["cache_create"] += r["cache_creation_tokens"]
        t["cache_read"] += r["cache_read_tokens"]

    logged = _fetch_logged(start)

    recon_rows: list[dict] = []
    gaps: list[dict] = []
    keys = set(truth.keys()) | {(d, m, "shared") for (d, m) in logged.keys()}
    for (day, model, bucket) in sorted(keys):
        t = truth.get((day, model, bucket), {"input": 0, "output": 0, "cache_create": 0, "cache_read": 0})
        lg = logged.get((day, model), {"input": 0, "output": 0, "cost": 0.0}) if bucket == "shared" else {"input": 0, "output": 0, "cost": 0.0}
        gap_in = t["input"] - lg["input"]
        gap_out = t["output"] - lg["output"]
        gap_pct = round(100.0 * gap_out / t["output"], 1) if t["output"] else (0.0 if gap_out <= 0 else 100.0)
        note = "console_usage (unattributable — Workbench/manual)" if bucket == "console" else None
        recon_rows.append({
            "usage_date": day,
            "model": model,
            "api_key_id": bucket,
            "anthropic_input_tokens": t["input"],
            "anthropic_output_tokens": t["output"],
            "anthropic_cache_creation_tokens": t["cache_create"],
            "anthropic_cache_read_tokens": t["cache_read"],
            "anthropic_cost_usd": round(cost_by_dm.get((day, model), 0.0), 4) if bucket == "shared" else None,
            "logged_input_tokens": lg["input"],
            "logged_output_tokens": lg["output"],
            "logged_cost_usd": round(lg["cost"], 6),
            "gap_input_tokens": gap_in,
            "gap_output_tokens": gap_out,
            "gap_pct": gap_pct,
            "note": note,
        })
        if bucket == "shared" and gap_out > _GAP_TOKEN_THRESHOLD and gap_pct > _GAP_PCT_THRESHOLD:
            gaps.append({"date": day, "model": model, "gap_out": gap_out, "gap_pct": gap_pct})

    stored = _upsert_recon(recon_rows)
    if gaps:
        _alert_gaps(gaps)
    return {"available": True, "days": days, "rows": len(recon_rows),
            "stored": stored, "gaps": gaps,
            "cost_available": cost.get("available", False)}


def _alert_gaps(gaps: list[dict]) -> None:
    """Post a throttled #alerts message naming the un-instrumented (day, model) gaps."""
    webhook = os.environ.get("DISCORD_WEBHOOK_ALERTS", "")
    if not webhook:
        return
    lines = [f"• {g['date']} `{g['model']}` — {g['gap_out']:,} output tokens unlogged ({g['gap_pct']}%)"
             for g in gaps[:10]]
    content = (
        "⚠️ **AI-usage reconciliation gap**\n"
        "Anthropic billed more than the `ai_api_usage` audit log captured — "
        "an un-instrumented call-site or project:\n" + "\n".join(lines) +
        "\n(See `ai_usage_reconciliation`. `console` rows are Workbench/manual and expected.)"
    )

    def _send():
        try:
            httpx.post(webhook, json={"content": content[:1900]}, timeout=10)
        except Exception:
            pass

    threading.Thread(target=_send, daemon=True).start()


if __name__ == "__main__":
    import argparse
    import json

    ap = argparse.ArgumentParser(description="Reconcile ai_api_usage vs Anthropic Admin usage report")
    ap.add_argument("--days", type=int, default=3)
    args = ap.parse_args()
    result = reconcile(days=args.days)
    print(json.dumps(result, indent=2, default=str))
