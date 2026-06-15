"""Shared writer for the cross-project `ai_api_usage` audit log.

Every project that calls the Anthropic API with the shared key writes one row
per call here (fire-and-forget). The table lives in Supabase
``modjoikyuhqzouxvieua`` (``public.ai_api_usage``) and is RLS-locked to the
service role, so writes use ``SUPABASE_SERVICE_ROLE_KEY``.

This is the reference implementation; the TS/Deno projects carry a ~25-line
equivalent. The daily reconciliation (``domains.api_usage.reconcile``) diffs
the sum of these rows against Anthropic's Admin usage_report to expose gaps.

Usage::

    from domains.api_usage.audit_log import log_ai_usage

    resp = client.messages.create(model=MODEL, ...)
    log_ai_usage(feature="japan_scraper", model=MODEL, usage=resp.usage,
                 anthropic_message_id=resp.id)
"""

from __future__ import annotations

import os
import threading
from typing import Any, Optional

import httpx

from logger import logger

try:
    # Reuse the canonical rate table so cost_usd estimates match the rest of the system.
    from domains.peterbot.costs import compute_cost
except Exception:  # pragma: no cover - costs module optional at import time
    compute_cost = None  # type: ignore

PROJECT = "discord-messenger"
_TABLE = "ai_api_usage"

_SUPABASE_URL = (os.getenv("SUPABASE_URL") or "").rstrip("/")
# Prefer the service-role key (table is RLS-locked to service_role); fall back to
# the anon key only so a misconfig degrades to a logged no-op rather than a crash.
_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""


def _usage_fields(usage: Any) -> dict:
    """Normalise an Anthropic ``usage`` object/dict into our integer columns."""
    if usage is None:
        return {"input_tokens": 0, "output_tokens": 0,
                "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
    get = usage.get if isinstance(usage, dict) else (lambda k, d=0: getattr(usage, k, d))
    return {
        "input_tokens": int(get("input_tokens", 0) or 0),
        "output_tokens": int(get("output_tokens", 0) or 0),
        "cache_creation_input_tokens": int(get("cache_creation_input_tokens", 0) or 0),
        "cache_read_input_tokens": int(get("cache_read_input_tokens", 0) or 0),
    }


def _usage_to_dict(usage: Any) -> dict:
    if usage is None:
        return {}
    if isinstance(usage, dict):
        return usage
    # Anthropic SDK Usage object → dict for compute_cost()
    out = {}
    for k in ("input_tokens", "output_tokens", "cache_read_input_tokens",
              "cache_creation_input_tokens"):
        out[k] = getattr(usage, k, 0) or 0
    cc = getattr(usage, "cache_creation", None)
    if cc is not None:
        out["cache_creation"] = {
            "ephemeral_5m_input_tokens": getattr(cc, "ephemeral_5m_input_tokens", 0) or 0,
            "ephemeral_1h_input_tokens": getattr(cc, "ephemeral_1h_input_tokens", 0) or 0,
        }
    return out


def log_ai_usage(
    *,
    feature: str,
    model: str,
    usage: Any = None,
    project: str = PROJECT,
    billing_source: str = "api_key",
    request_ms: Optional[float] = None,
    status: str = "success",
    error: Optional[str] = None,
    anthropic_message_id: Optional[str] = None,
    request_id: Optional[str] = None,
    metadata: Optional[dict] = None,
    cost_usd: Optional[float] = None,
) -> None:
    """Fire-and-forget insert of one Anthropic call into ``ai_api_usage``.

    Never raises and never blocks the caller's request — the insert runs on a
    daemon thread with a short timeout. A failed insert is logged at debug only.
    """
    tokens = _usage_fields(usage)
    if cost_usd is None and compute_cost is not None:
        try:
            cost_usd = round(compute_cost(model or "", _usage_to_dict(usage)), 6)
        except Exception:
            cost_usd = None

    row = {
        "project": project,
        "feature": feature,
        "model": model or "",
        "billing_source": billing_source,
        **tokens,
        "cost_usd": cost_usd,
        "request_ms": int(request_ms) if request_ms is not None else None,
        "status": status,
        "error": (str(error)[:500] if error else None),
        "anthropic_message_id": anthropic_message_id,
        "request_id": request_id,
        "metadata": metadata,
    }

    if not _SUPABASE_URL or not _SERVICE_KEY:
        logger.debug("ai_api_usage: SUPABASE_URL/key missing — skipping audit insert")
        return

    payload = {k: v for k, v in row.items() if v is not None}
    threading.Thread(target=_insert, args=(payload,), daemon=True).start()


def _insert(payload: dict) -> None:
    try:
        httpx.post(
            f"{_SUPABASE_URL}/rest/v1/{_TABLE}",
            headers={
                "apikey": _SERVICE_KEY,
                "Authorization": f"Bearer {_SERVICE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            },
            json=payload,
            timeout=10,
        )
    except Exception as e:  # pragma: no cover - network best-effort
        logger.debug(f"ai_api_usage insert failed: {e}")
