"""USD -> GBP rate cache.

Prolific shows rewards in USD for some researchers. The Discord embed should
display GBP since that's what Chris thinks in. We cache a single rate for 24h
and refresh from open.er-api.com (free, no key). On any fetch failure we keep
serving the previous value rather than killing the alert flow.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import httpx

from logger import logger

_CACHE_PATH = Path(__file__).resolve().parents[2] / "data" / "fx_usd_gbp.json"
_TTL_SECONDS = 24 * 60 * 60
_FALLBACK_RATE = 0.79  # rough mid-rate used only if we never managed a live fetch


def _load() -> tuple[float | None, float | None]:
    if not _CACHE_PATH.exists():
        return None, None
    try:
        data = json.loads(_CACHE_PATH.read_text())
        return float(data["rate"]), float(data["fetched_at"])
    except (json.JSONDecodeError, KeyError, ValueError):
        return None, None


def _save(rate: float) -> None:
    _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CACHE_PATH.write_text(json.dumps({"rate": rate, "fetched_at": time.time()}))


def _fetch_live() -> float | None:
    try:
        r = httpx.get("https://open.er-api.com/v6/latest/USD", timeout=5.0)
        r.raise_for_status()
        data = r.json()
        rate = data["rates"]["GBP"]
        if not isinstance(rate, (int, float)) or rate <= 0:
            return None
        return float(rate)
    except (httpx.HTTPError, KeyError, ValueError, TypeError) as e:
        logger.warning(f"USD->GBP fetch failed: {e}")
        return None


def usd_to_gbp_rate() -> float:
    """Return USD->GBP multiplier. Caches for 24h, falls back to last-known value."""
    cached, fetched_at = _load()
    fresh = cached is not None and fetched_at is not None and (time.time() - fetched_at) < _TTL_SECONDS
    if fresh:
        return cached  # type: ignore[return-value]

    live = _fetch_live()
    if live is not None:
        _save(live)
        return live

    if cached is not None:
        # Stale but better than the hardcoded fallback
        return cached
    return _FALLBACK_RATE


def usd_pence_to_gbp_pence(usd_pence: int) -> int:
    return int(round(usd_pence * usd_to_gbp_rate()))
