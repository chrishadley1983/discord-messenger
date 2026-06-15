"""Reconcile logged `ai_api_usage` against an Anthropic Console **cost CSV export**.

Anthropic's Admin API (usage_report/cost_report) is unavailable on individual /
API-plan accounts, so the ground-truth side comes from the Console's cost CSV
export (platform.claude.com → Usage → Export). This is account-tier-independent
and needs no admin key.

CSV columns: usage_date_utc, model, workspace, api_key, usage_type,
context_window, token_type, cost_usd, list_price_usd, cost_type, inference_geo, speed

Each CSV `api_key` maps to a project; we sum Anthropic cost by (date, project),
sum our logged `ai_api_usage` cost by (date, project) over the same window, and
report the gap. A positive gap (Anthropic > logged) = un-instrumented spend
(a project/key not yet wired, or pre-instrumentation history).

Run:  python -m domains.api_usage.reconcile_csv <path-to-csv> [--store]
"""

from __future__ import annotations

import csv
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone

import httpx

from logger import logger

_SUPABASE_URL = (os.getenv("SUPABASE_URL") or "https://modjoikyuhqzouxvieua.supabase.co").rstrip("/")
_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("AI_USAGE_SERVICE_KEY") or ""
_USAGE_TABLE = "ai_api_usage"
_RECON_TABLE = "ai_usage_reconciliation"

# Map Anthropic Console api_key name -> our project label. Unknown keys fall
# back to the api_key name itself (and are surfaced as such in the report).
API_KEY_TO_PROJECT = {
    "HB_2026": "hadley-bricks",
    "football-pred": "football-predictor",
    # extend as more keys appear in exports:
    # "family-fuel": "family-fuel", "finance": "finance-tracker", ...
}

# Alert when a project's gap exceeds this absolute USD AND fraction of Anthropic cost.
_GAP_USD_THRESHOLD = 0.25
_GAP_FRAC_THRESHOLD = 0.5


def _project_for_key(api_key: str) -> str:
    return API_KEY_TO_PROJECT.get(api_key, api_key or "unknown")


def _parse_csv(path: str) -> tuple[dict, list[str]]:
    """Return ({(date, project): anthropic_cost}, sorted_dates)."""
    by_dp: dict[tuple, float] = defaultdict(float)
    dates: set[str] = set()
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            day = (row.get("usage_date_utc") or "")[:10]
            if not day:
                continue
            proj = _project_for_key(row.get("api_key") or "")
            try:
                cost = float(row.get("cost_usd") or 0)
            except (TypeError, ValueError):
                cost = 0.0
            by_dp[(day, proj)] += cost
            dates.add(day)
    return by_dp, sorted(dates)


def _fetch_logged_cost(start: str, end: str) -> dict[tuple, float]:
    """Sum logged ai_api_usage cost_usd by (date, project) over [start, end]."""
    out: dict[tuple, float] = defaultdict(float)
    if not _SUPABASE_URL or not _SERVICE_KEY:
        logger.warning("reconcile_csv: no Supabase service key — logged side will be 0")
        return out
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.get(
                f"{_SUPABASE_URL}/rest/v1/{_USAGE_TABLE}",
                headers={"apikey": _SERVICE_KEY, "Authorization": f"Bearer {_SERVICE_KEY}"},
                params={"select": "created_at,project,cost_usd,billing_source",
                        "created_at": f"gte.{start}", "billing_source": "eq.api_key",
                        "limit": "200000"},
            )
            resp.raise_for_status()
            rows = resp.json()
    except Exception as e:
        logger.warning(f"reconcile_csv: failed reading {_USAGE_TABLE}: {e}")
        return out
    for r in rows:
        day = (r.get("created_at") or "")[:10]
        if day and day <= end:
            out[(day, r.get("project") or "?")] += float(r.get("cost_usd") or 0.0)
    return out


def _upsert(rows: list[dict]) -> bool:
    if not rows or not _SUPABASE_URL or not _SERVICE_KEY:
        return False
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.post(
                f"{_SUPABASE_URL}/rest/v1/{_RECON_TABLE}",
                headers={"apikey": _SERVICE_KEY, "Authorization": f"Bearer {_SERVICE_KEY}",
                         "Content-Type": "application/json",
                         "Prefer": "resolution=merge-duplicates,return=minimal"},
                params={"on_conflict": "usage_date,model,api_key_id"},
                json=rows,
            )
            resp.raise_for_status()
        return True
    except Exception as e:
        logger.warning(f"reconcile_csv: upsert failed: {e}")
        return False


def reconcile_csv(path: str, store: bool = False) -> dict:
    """Reconcile the cost CSV at `path` against logged ai_api_usage. Returns a summary."""
    anthropic, dates = _parse_csv(path)
    if not dates:
        return {"error": "no rows parsed from CSV", "path": path}
    start, end = dates[0], dates[-1]
    logged = _fetch_logged_cost(start, end)

    # Aggregate to per-project totals across the window.
    proj_anthropic: dict[str, float] = defaultdict(float)
    proj_logged: dict[str, float] = defaultdict(float)
    for (d, p), c in anthropic.items():
        proj_anthropic[p] += c
    for (d, p), c in logged.items():
        proj_logged[p] += c

    projects = sorted(set(proj_anthropic) | set(proj_logged))
    report = []
    gaps = []
    for p in projects:
        a = round(proj_anthropic.get(p, 0.0), 4)
        l = round(proj_logged.get(p, 0.0), 4)
        gap = round(a - l, 4)
        frac = (gap / a) if a > 0 else 0.0
        report.append({"project": p, "anthropic_usd": a, "logged_usd": l, "gap_usd": gap,
                       "gap_pct": round(100 * frac, 1)})
        if gap > _GAP_USD_THRESHOLD and frac > _GAP_FRAC_THRESHOLD:
            gaps.append(p)

    recon_rows = []
    if store:
        for (d, p), a in anthropic.items():
            recon_rows.append({
                "usage_date": d, "model": "(all)", "api_key_id": p,
                "anthropic_cost_usd": round(a, 4),
                "logged_cost_usd": round(logged.get((d, p), 0.0), 6),
                "note": "from Console cost CSV export",
            })
        _upsert(recon_rows)

    return {"window": [start, end], "total_anthropic_usd": round(sum(proj_anthropic.values()), 2),
            "total_logged_usd": round(sum(proj_logged.values()), 2),
            "by_project": report, "gap_projects": gaps, "stored": bool(recon_rows)}


if __name__ == "__main__":
    import argparse
    import json

    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path")
    ap.add_argument("--store", action="store_true", help="upsert results into ai_usage_reconciliation")
    args = ap.parse_args()
    res = reconcile_csv(args.csv_path, store=args.store)

    print(f"\n=== AI-usage reconciliation (Console CSV vs logged) — {res.get('window')} ===\n")
    print(f"{'project':<22} {'anthropic$':>11} {'logged$':>10} {'gap$':>9} {'gap%':>7}")
    print("-" * 64)
    for r in res.get("by_project", []):
        print(f"{r['project']:<22} {r['anthropic_usd']:>11.4f} {r['logged_usd']:>10.4f} "
              f"{r['gap_usd']:>9.4f} {r['gap_pct']:>6.1f}%")
    print("-" * 64)
    print(f"{'TOTAL':<22} {res.get('total_anthropic_usd',0):>11.2f} {res.get('total_logged_usd',0):>10.2f}")
    if res.get("gap_projects"):
        print(f"\n⚠️  Un-instrumented / unexplained gap in: {', '.join(res['gap_projects'])}")
        print("    (Anthropic billed materially more than we logged — a key/project not yet")
        print("     instrumented, or spend predating instrumentation.)")
    print(json.dumps(res, indent=2))
