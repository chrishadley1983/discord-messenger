"""Anthropic organization Admin API client — usage & cost reports.

Ground-truth usage/cost for reconciliation against the self-logged
``ai_api_usage`` table. Replaces the brittle cookie-session scraper
(``anthropic_usage.py`` / ``anthropic_scraper.py``) with the official API.

Requires an **Admin API key** (org-admin only), created by an org admin
in the Console (Settings → Admin keys) and stored as ``ANTHROPIC_ADMIN_KEY``.
Without it every function returns ``available=False`` and the caller skips.

Docs:
- https://platform.claude.com/docs/en/api/admin-api/usage-cost/get-messages-usage-report
- https://platform.claude.com/docs/en/api/admin-api/usage-cost/get-cost-report
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import httpx

from logger import logger

_USAGE_URL = "https://api.anthropic.com/v1/organizations/usage_report/messages"
_COST_URL = "https://api.anthropic.com/v1/organizations/cost_report"
_VERSION = "2023-06-01"


def admin_key() -> Optional[str]:
    return os.getenv("ANTHROPIC_ADMIN_KEY") or None


def _headers(key: str) -> dict:
    return {"x-api-key": key, "anthropic-version": _VERSION, "content-type": "application/json"}


def _rfc3339(d: date) -> str:
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _paginate(url: str, key: str, params: dict) -> list[dict]:
    """Follow Admin-API pagination, returning the flat list of time buckets."""
    buckets: list[dict] = []
    page: Optional[str] = None
    with httpx.Client(timeout=30) as client:
        for _ in range(50):  # hard safety cap
            q = dict(params)
            if page:
                q["page"] = page
            resp = client.get(url, headers=_headers(key), params=q)
            resp.raise_for_status()
            body = resp.json()
            buckets.extend(body.get("data") or [])
            if body.get("has_more") and body.get("next_page"):
                page = body["next_page"]
                continue
            break
    return buckets


def fetch_usage(start: date, end: date) -> dict:
    """Daily token usage grouped by model × api_key_id.

    Returns ``{"available": bool, "rows": [{usage_date, model, api_key_id,
    input_tokens, output_tokens, cache_creation_tokens, cache_read_tokens}], ...}``.
    """
    key = admin_key()
    if not key:
        return {"available": False, "note": "ANTHROPIC_ADMIN_KEY not set", "rows": []}

    params = {
        "starting_at": _rfc3339(start),
        "ending_at": _rfc3339(end),
        "bucket_width": "1d",
        "group_by[]": ["model", "api_key_id"],
    }
    try:
        buckets = _paginate(_USAGE_URL, key, params)
    except Exception as e:
        logger.warning(f"anthropic_admin.fetch_usage failed: {e}")
        return {"available": False, "note": str(e)[:200], "rows": []}

    rows: list[dict] = []
    for bucket in buckets:
        bday = (bucket.get("starting_at") or "")[:10]
        for r in bucket.get("results") or []:
            cc = r.get("cache_creation") or {}
            cache_creation = int(
                (cc.get("ephemeral_5m_input_tokens") or 0)
                + (cc.get("ephemeral_1h_input_tokens") or 0)
            ) if isinstance(cc, dict) else int(r.get("cache_creation_input_tokens") or 0)
            rows.append({
                "usage_date": bday,
                "model": r.get("model") or "unknown",
                # api_key_id is null for Workbench/Console usage → sentinel.
                "api_key_id": r.get("api_key_id") or "console",
                "input_tokens": int(r.get("uncached_input_tokens") or r.get("input_tokens") or 0),
                "output_tokens": int(r.get("output_tokens") or 0),
                "cache_creation_tokens": cache_creation,
                "cache_read_tokens": int(r.get("cache_read_input_tokens") or 0),
            })
    return {"available": True, "rows": rows, "buckets": len(buckets)}


def fetch_cost(start: date, end: date) -> dict:
    """Daily USD cost grouped by description (so we can attribute per model).

    Best-effort: the cost_report description schema includes ``model`` when
    grouped by description. Returns ``{"available": bool, "by_day_model":
    {(date, model): usd}, "by_day": {date: usd}}``.
    """
    key = admin_key()
    if not key:
        return {"available": False, "note": "ANTHROPIC_ADMIN_KEY not set",
                "by_day_model": {}, "by_day": {}}

    params = {
        "starting_at": _rfc3339(start),
        "ending_at": _rfc3339(end),
        "bucket_width": "1d",
        "group_by[]": ["description"],
    }
    try:
        buckets = _paginate(_COST_URL, key, params)
    except Exception as e:
        logger.warning(f"anthropic_admin.fetch_cost failed: {e}")
        return {"available": False, "note": str(e)[:200], "by_day_model": {}, "by_day": {}}

    by_day_model: dict[tuple, float] = {}
    by_day: dict[str, float] = {}
    for bucket in buckets:
        bday = (bucket.get("starting_at") or "")[:10]
        for r in bucket.get("results") or []:
            # amount is a decimal string in USD per the cost API.
            try:
                amount = float(r.get("amount") or r.get("cost") or 0)
            except (TypeError, ValueError):
                amount = 0.0
            model = r.get("model") or (r.get("description") or {}).get("model") \
                if isinstance(r.get("description"), dict) else r.get("model") or "unknown"
            model = model or "unknown"
            by_day_model[(bday, model)] = by_day_model.get((bday, model), 0.0) + amount
            by_day[bday] = by_day.get(bday, 0.0) + amount
    return {"available": True, "by_day_model": by_day_model, "by_day": by_day}
