#!/usr/bin/env python3
"""Consolidated PRODUCTION validation for the shared AI-usage audit log.

This is the cross-project "completeness meter". After each project is deployed
and takes traffic, run this to see which projects are actually logging into
`ai_api_usage` (Supabase modjoikyuhqzouxvieua) — and which are silent (not yet
deployed, or genuinely idle).

It needs a key that can READ the table (the publishable key is insert-only).
Reads `AI_USAGE_SERVICE_KEY`, else falls back to `SUPABASE_SERVICE_ROLE_KEY`
(discord-messenger's own .env already has the latter, pointed at this project).

Usage:
  python scripts/validate_ai_audit_prod.py [--hours 24]
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import httpx
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()

URL = (os.getenv("SUPABASE_URL") or "https://modjoikyuhqzouxvieua.supabase.co").rstrip("/")
KEY = os.getenv("AI_USAGE_SERVICE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY") or ""
API_BASE = os.getenv("HADLEY_API_BASE", "http://127.0.0.1:8100")

# Every project we instrumented. Presence of recent rows = it's live in prod.
EXPECTED = [
    "discord-messenger", "hadley-bricks", "football-predictor", "family-fuel",
    "finance-tracker", "gainai", "poker", "instagram-automation",
    "factorio", "japan-family-guide",
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=int, default=24)
    args = ap.parse_args()

    if not KEY:
        print("FAIL: no read key. Set AI_USAGE_SERVICE_KEY (or SUPABASE_SERVICE_ROLE_KEY) "
              "to the modjoikyuhqzouxvieua service-role key.")
        return 2

    cutoff = (datetime.now(timezone.utc) - timedelta(hours=args.hours)).isoformat()
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.get(
                f"{URL}/rest/v1/ai_api_usage",
                headers={"apikey": KEY, "Authorization": f"Bearer {KEY}"},
                params={"select": "project,feature,model,input_tokens,output_tokens,cost_usd,status",
                        "created_at": f"gte.{cutoff}", "limit": "200000"},
            )
            resp.raise_for_status()
            rows = resp.json()
    except Exception as e:
        print(f"FAIL: could not read ai_api_usage: {e}")
        return 2

    per_project = defaultdict(lambda: {"calls": 0, "in": 0, "out": 0, "cost": 0.0, "errors": 0, "features": set()})
    for r in rows:
        p = per_project[r.get("project") or "?"]
        p["calls"] += 1
        p["in"] += int(r.get("input_tokens") or 0)
        p["out"] += int(r.get("output_tokens") or 0)
        p["cost"] += float(r.get("cost_usd") or 0.0)
        p["features"].add(r.get("feature") or "?")
        if r.get("status") == "error":
            p["errors"] += 1

    print(f"\n=== AI-usage prod coverage — last {args.hours}h (total rows: {len(rows)}) ===\n")
    print(f"{'project':<22} {'calls':>6} {'in_tok':>9} {'out_tok':>9} {'~$':>8}  features")
    print("-" * 80)
    live = 0
    for proj in EXPECTED:
        p = per_project.get(proj)
        if p:
            live += 1
            feats = ", ".join(sorted(p["features"]))[:30]
            print(f"{proj:<22} {p['calls']:>6} {p['in']:>9} {p['out']:>9} {p['cost']:>8.3f}  {feats}")
        else:
            print(f"{proj:<22} {'—':>6} {'':>9} {'':>9} {'':>8}  (no rows — not deployed / idle)")
    # any unexpected project labels
    for proj, p in per_project.items():
        if proj not in EXPECTED:
            print(f"{proj:<22} {p['calls']:>6} {p['in']:>9} {p['out']:>9} {p['cost']:>8.3f}  (UNEXPECTED label)")

    print(f"\n{live}/{len(EXPECTED)} projects logging in the last {args.hours}h.")

    print("\n=== Hadley API endpoints ===")
    try:
        with httpx.Client(timeout=10) as client:
            a = client.get(f"{API_BASE}/usage/audit", params={"hours": args.hours})
            rec = client.get(f"{API_BASE}/usage/reconcile", params={"days": 7})
        print(f"/usage/audit -> HTTP {a.status_code}    /usage/reconcile -> HTTP {rec.status_code}")
        if a.status_code == 404:
            print("  (404 = HadleyAPI not yet restarted to load usage_routes)")
    except Exception as e:
        print(f"  (Hadley API unreachable: {e})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
