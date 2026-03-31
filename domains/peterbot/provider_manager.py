"""Model provider state management for Peterbot.

3-tier priority cascade: claude_cc → claude_cc2 → kimi
State is persisted in data/model_config.json with mtime-based caching.
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from logger import logger
from .config import PROVIDER_PRIORITY

UK_TZ = ZoneInfo("Europe/London")

# State file location
STATE_FILE = Path(__file__).parent.parent.parent / "data" / "model_config.json"

# Cache: avoid re-reading file on every message
_cache_mtime: float = 0.0
_cache_data: dict = {}

# Valid provider names
VALID_PROVIDERS = set(PROVIDER_PRIORITY)

# Default state
DEFAULT_STATE = {
    "active_provider": PROVIDER_PRIORITY[0],  # claude_cc
    "reason": "default",
    "switched_at": None,
    "auto_switch_enabled": True,
    "kimi_requests": 0,
    "failover_history": [],  # Recent failover events for diagnostics
}

# Substrings that indicate Anthropic credit/billing exhaustion
CREDIT_ERROR_KEYWORDS = [
    "hit your limit",
    "you've hit your limit",
    "rate-limit-options",
    "credit",
    "billing",
    "quota",
    "exceeded",
    "rate limit",
    "rate_limit",
    "ratelimit",
    "insufficient",
    "subscription",
    "limit reached",
    "payment",
    "overloaded",
    "too many requests",
    "429",
    "usage cap",
    "cooldown",
    "try again later",
    "capacity",
    "throttl",
]


def _read_state() -> dict:
    """Read state from file with mtime caching."""
    global _cache_mtime, _cache_data

    try:
        current_mtime = STATE_FILE.stat().st_mtime
        if current_mtime == _cache_mtime and _cache_data:
            return _cache_data
    except FileNotFoundError:
        return DEFAULT_STATE.copy()

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        _cache_mtime = STATE_FILE.stat().st_mtime
        _cache_data = data
        return data
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Failed to read model config: {e}")
        return DEFAULT_STATE.copy()


def _write_state(data: dict) -> None:
    """Atomic write: temp file + os.replace."""
    global _cache_mtime, _cache_data

    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = STATE_FILE.with_suffix(".tmp")

    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(str(tmp_path), str(STATE_FILE))
        _cache_mtime = STATE_FILE.stat().st_mtime
        _cache_data = data
    except OSError as e:
        logger.error(f"Failed to write model config: {e}")
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass


def _migrate_legacy_provider(provider: str) -> str:
    """Migrate old provider names to new 3-tier names.

    Old state files may have 'claude' instead of 'claude_cc'.
    """
    if provider == "claude":
        return "claude_cc"
    return provider


def get_active_provider() -> str:
    """Get the currently active provider name.

    Returns one of: 'claude_cc', 'claude_cc2', 'kimi'
    """
    raw = _read_state().get("active_provider", PROVIDER_PRIORITY[0])
    provider = _migrate_legacy_provider(raw)
    if provider not in VALID_PROVIDERS:
        logger.warning(f"Unknown provider '{provider}' in state, resetting to {PROVIDER_PRIORITY[0]}")
        return PROVIDER_PRIORITY[0]
    return provider


def get_next_provider(current: str) -> str | None:
    """Get the next provider in the priority cascade.

    Returns None if current is already the last provider (kimi).
    """
    current = _migrate_legacy_provider(current)
    try:
        idx = PROVIDER_PRIORITY.index(current)
        if idx + 1 < len(PROVIDER_PRIORITY):
            return PROVIDER_PRIORITY[idx + 1]
    except ValueError:
        pass
    return None


def set_active_provider(provider: str, reason: str) -> None:
    """Switch active provider and record reason.

    Args:
        provider: One of PROVIDER_PRIORITY values
        reason: Why the switch happened (e.g., 'auto_failover', 'manual', 'auto_recovery')
    """
    provider = _migrate_legacy_provider(provider)
    if provider not in VALID_PROVIDERS:
        raise ValueError(f"Invalid provider: {provider}. Must be one of {PROVIDER_PRIORITY}")

    state = _read_state()
    old_provider = _migrate_legacy_provider(state.get("active_provider", PROVIDER_PRIORITY[0]))
    state["active_provider"] = provider
    state["reason"] = reason
    state["switched_at"] = datetime.now(UK_TZ).isoformat()

    # Reset kimi request counter when switching back to any Claude provider
    if provider.startswith("claude_"):
        state["kimi_requests"] = 0

    # Record failover event (keep last 20)
    history = state.get("failover_history", [])
    history.append({
        "from": old_provider,
        "to": provider,
        "reason": reason,
        "at": datetime.now(UK_TZ).isoformat(),
    })
    state["failover_history"] = history[-20:]

    _write_state(state)
    logger.info(f"Provider switched: {old_provider} → {provider} (reason: {reason})")

    # Alert on failover (fire-and-forget with delivery guarantee)
    if "auto_failover" in reason:
        _send_failover_alert(old_provider, provider, reason)


# Deduplication: suppress repeat alerts within 60 seconds per transition
_last_failover_alert: dict[str, float] = {}
_FAILOVER_ALERT_COOLDOWN = 60  # seconds


def _send_failover_alert(old_provider: str, new_provider: str, reason: str) -> None:
    """Post failover alert to Discord #alerts. Deduped with 60s cooldown."""
    try:
        import threading
        import httpx as _httpx

        # Dedup: skip if same transition alerted recently
        transition_key = f"{old_provider}->{new_provider}"
        now = time.time()
        last = _last_failover_alert.get(transition_key, 0)
        if now - last < _FAILOVER_ALERT_COOLDOWN:
            logger.info(f"Failover alert suppressed (cooldown): {transition_key}")
            return
        _last_failover_alert[transition_key] = now

        webhook_url = os.environ.get("DISCORD_WEBHOOK_ALERTS", "")
        if not webhook_url:
            return

        msg = f"⚠️ **Provider failover**: {old_provider} → {new_provider}. Reason: {reason}"

        def _post():
            try:
                _httpx.post(webhook_url, json={"content": msg, "username": "Provider Monitor"}, timeout=10)
            except Exception as e:
                logger.warning(f"Failover alert delivery failed: {e}")

        t = threading.Thread(target=_post, daemon=False)
        t.start()
        t.join(timeout=5)  # Wait up to 5s for delivery before continuing
    except Exception as e:
        logger.warning(f"Failover alert error: {e}")


def get_provider_status() -> dict:
    """Get full provider status for API/dashboard."""
    state = _read_state()
    # Normalise legacy names in output
    state["active_provider"] = _migrate_legacy_provider(
        state.get("active_provider", PROVIDER_PRIORITY[0])
    )
    state["provider_priority"] = PROVIDER_PRIORITY
    return state


def increment_kimi_requests() -> None:
    """Increment the Kimi request counter."""
    state = _read_state()
    state["kimi_requests"] = state.get("kimi_requests", 0) + 1
    _write_state(state)


def is_credit_exhaustion_error(error_msg: str) -> bool:
    """Check if an error message indicates Anthropic credit/billing exhaustion."""
    if not error_msg:
        return False
    lower = error_msg.lower()
    return any(keyword in lower for keyword in CREDIT_ERROR_KEYWORDS)
