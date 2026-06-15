#!/usr/bin/env python3
"""Production-validation workflow for discord-messenger's AI-usage audit path.

Confirms the discord-messenger writer reaches the shared `ai_api_usage` table
and that the Hadley API read/reconcile endpoints respond. Run locally (needs
the service-role key, since the table is RLS insert-only for the publishable key).

Steps:
  1. Insert a probe row via domains.api_usage.audit_log.log_ai_usage.
  2. Read it back via the service-role key, assert it landed, then delete it.
  3. (Optional) GET /usage/audit + /usage/reconcile on Hadley API if it's up.

Usage:
  python scripts/validate_ai_audit.py
Env (from .env): SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, HADLEY_API_BASE (optional).
"""

from __future__ import annotations

import os
import sys
import time

import httpx
from dotenv import load_dotenv

# Allow running as `python scripts/validate_ai_audit.py` (repo root on sys.path).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

URL = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SERVICE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or ""
API_BASE = os.getenv("HADLEY_API_BASE", "http://127.0.0.1:8100")
PROBE_FEATURE = "_validate_dm"


def _svc_headers() -> dict:
    return {"apikey": SERVICE_KEY, "Authorization": f"Bearer {SERVICE_KEY}"}


def main() -> int:
    if not URL or not SERVICE_KEY:
        print("FAIL: SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set")
        return 2

    print("1) Inserting probe row via log_ai_usage()...")
    from domains.api_usage.audit_log import log_ai_usage

    log_ai_usage(
        feature=PROBE_FEATURE,
        model="claude-haiku-4-5",
        usage={"input_tokens": 5, "output_tokens": 3, "cache_read_input_tokens": 1},
        anthropic_message_id="msg_validate_dm",
        request_ms=10.0,
        metadata={"source": "validate_ai_audit.py"},
    )
    time.sleep(3)  # fire-and-forget daemon thread

    print("2) Reading it back (service-role)...")
    with httpx.Client(timeout=20) as client:
        resp = client.get(
            f"{URL}/rest/v1/ai_api_usage",
            headers=_svc_headers(),
            params={"select": "project,feature,model,input_tokens,output_tokens,cost_usd",
                    "feature": f"eq.{PROBE_FEATURE}", "project": "eq.discord-messenger"},
        )
        rows = resp.json() if resp.status_code == 200 else []
        # cleanup regardless
        client.delete(f"{URL}/rest/v1/ai_api_usage",
                      headers=_svc_headers(),
                      params={"feature": f"eq.{PROBE_FEATURE}"})

    if not rows:
        print("FAIL: probe row not found in ai_api_usage")
        return 1
    print(f"   PASS: row landed -> {rows[0]}")

    print("3) Hitting Hadley API /usage endpoints (best-effort)...")
    try:
        with httpx.Client(timeout=10) as client:
            a = client.get(f"{API_BASE}/usage/audit", params={"hours": 24})
            r = client.get(f"{API_BASE}/usage/reconcile", params={"days": 7})
        print(f"   /usage/audit -> HTTP {a.status_code}; /usage/reconcile -> HTTP {r.status_code}")
    except Exception as e:
        print(f"   (skipped — Hadley API not reachable: {e})")

    print("\nPASS: discord-messenger audit path validated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
