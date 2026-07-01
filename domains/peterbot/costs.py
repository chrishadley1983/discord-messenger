"""Per-model token pricing for Claude usage estimation.

Used by data_collectors/channel_cost_tail.py to convert transcript `usage`
blocks into USD cost estimates.

router_v2.py does NOT use this — it receives `cost_usd` directly from
Claude's `result` event over stream-json.

Rates from anthropic.com/pricing as of 2026-05.
"""

from __future__ import annotations

# Per-million-token rates in USD. Cache write rates are derived from input rate.
# Keep input rate as the authoritative number; cache_5m = input × 1.25, cache_1h = input × 2.0.
_RATES_PER_MTOK = {
    "claude-opus-4-8":     {"input": 5.00,  "output": 25.00, "cache_read": 0.50},
    "claude-opus-4-7":     {"input": 15.00, "output": 75.00, "cache_read": 1.50},
    "claude-opus-4-6":     {"input": 15.00, "output": 75.00, "cache_read": 1.50},
    "claude-sonnet-5":     {"input": 3.00,  "output": 15.00, "cache_read": 0.30},
    "claude-sonnet-4-6":   {"input": 3.00,  "output": 15.00, "cache_read": 0.30},
    "claude-sonnet-4-5":   {"input": 3.00,  "output": 15.00, "cache_read": 0.30},
    "claude-haiku-4-5":    {"input": 1.00,  "output": 5.00,  "cache_read": 0.10},
}

CACHE_5M_MULTIPLIER = 1.25
CACHE_1H_MULTIPLIER = 2.0


def _resolve_rates(model: str) -> dict:
    """Resolve rates for a model. Strip date suffixes (e.g. -20251001) before lookup."""
    if model in _RATES_PER_MTOK:
        return _RATES_PER_MTOK[model]
    # Strip trailing -YYYYMMDD-like suffix
    base = model.rsplit("-", 1)[0] if model and model[-1].isdigit() else model
    if base in _RATES_PER_MTOK:
        return _RATES_PER_MTOK[base]
    # Family fallback (last resort)
    for family, rates in _RATES_PER_MTOK.items():
        if model and (family in model or model in family):
            return rates
    # Unknown model — use Sonnet rates so we don't silently zero-out
    return _RATES_PER_MTOK["claude-sonnet-4-6"]


def compute_cost(model: str, usage: dict) -> float:
    """Compute USD cost for a single assistant turn from its `usage` block.

    Args:
        model: e.g. "claude-opus-4-6"
        usage: the `message.usage` dict from a Claude Code transcript entry.
            Required keys: input_tokens, output_tokens, cache_read_input_tokens,
            cache_creation_input_tokens. Optional: cache_creation.ephemeral_5m_input_tokens
            and ephemeral_1h_input_tokens for accurate cache-write split.

    Returns:
        Cost in USD (float). Returns 0.0 if usage is empty.
    """
    if not usage:
        return 0.0

    rates = _resolve_rates(model or "")
    input_rate = rates["input"]
    output_rate = rates["output"]
    cache_read_rate = rates["cache_read"]

    input_tokens = usage.get("input_tokens", 0) or 0
    output_tokens = usage.get("output_tokens", 0) or 0
    cache_read = usage.get("cache_read_input_tokens", 0) or 0
    cache_create_total = usage.get("cache_creation_input_tokens", 0) or 0

    # Split cache writes by TTL if available; otherwise assume all 5m (cheaper end).
    cache_creation = usage.get("cache_creation") or {}
    cache_5m = cache_creation.get("ephemeral_5m_input_tokens")
    cache_1h = cache_creation.get("ephemeral_1h_input_tokens")
    if cache_5m is None and cache_1h is None:
        cache_5m = cache_create_total
        cache_1h = 0
    else:
        cache_5m = cache_5m or 0
        cache_1h = cache_1h or 0

    cost = (
        (input_tokens / 1_000_000) * input_rate
        + (output_tokens / 1_000_000) * output_rate
        + (cache_read / 1_000_000) * cache_read_rate
        + (cache_5m / 1_000_000) * input_rate * CACHE_5M_MULTIPLIER
        + (cache_1h / 1_000_000) * input_rate * CACHE_1H_MULTIPLIER
    )
    return cost


def known_models() -> list[str]:
    return list(_RATES_PER_MTOK.keys())
