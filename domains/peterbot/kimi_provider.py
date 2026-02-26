"""Kimi 2.5 (Moonshot AI) fallback provider for Peterbot.

Direct API caller using httpx. Used when Anthropic credits are exhausted.
Degraded mode: no MCP tools, no CLAUDE.md auto-load, but pre-fetched context
(memory, knowledge, skill data) is still injected into the user message.
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable, Awaitable
from zoneinfo import ZoneInfo

import httpx

from logger import logger
from .config import KIMI_API_BASE, KIMI_MODEL, KIMI_MAX_TOKENS, KIMI_TIMEOUT
from .provider_manager import increment_kimi_requests

UK_TZ = ZoneInfo("Europe/London")

# Approximate USD to GBP conversion rate
USD_TO_GBP = 0.79

# Cost log file (shared with router_v2)
COST_LOG_PATH = Path(__file__).parent.parent.parent / "data" / "cli_costs.jsonl"

# PETERBOT_SOUL.md cached content
_soul_cache: str = ""
_soul_mtime: float = 0.0
SOUL_PATH = Path(__file__).parent / "wsl_config" / "PETERBOT_SOUL.md"

# Kimi pricing (per million tokens)
KIMI_INPUT_COST_PER_M = 0.60   # $0.60/M input tokens
KIMI_OUTPUT_COST_PER_M = 3.00  # $3.00/M output tokens

# Approximate tokens per character (conservative estimate)
CHARS_PER_TOKEN = 4


def _get_soul_prompt() -> str:
    """Read and cache PETERBOT_SOUL.md as system prompt."""
    global _soul_cache, _soul_mtime

    try:
        current_mtime = SOUL_PATH.stat().st_mtime
        if current_mtime == _soul_mtime and _soul_cache:
            return _soul_cache
    except FileNotFoundError:
        logger.warning(f"PETERBOT_SOUL.md not found at {SOUL_PATH}")
        return "You are Peter, the Hadley family assistant."

    try:
        _soul_cache = SOUL_PATH.read_text(encoding="utf-8")
        _soul_mtime = current_mtime
        return _soul_cache
    except OSError as e:
        logger.warning(f"Failed to read PETERBOT_SOUL.md: {e}")
        return "You are Peter, the Hadley family assistant."


def _estimate_cost(input_chars: int, output_chars: int) -> float:
    """Estimate cost in USD based on character counts."""
    input_tokens = input_chars / CHARS_PER_TOKEN
    output_tokens = output_chars / CHARS_PER_TOKEN
    cost = (input_tokens / 1_000_000 * KIMI_INPUT_COST_PER_M +
            output_tokens / 1_000_000 * KIMI_OUTPUT_COST_PER_M)
    return cost


def _log_cost(cost_usd: float, duration_ms: float, input_chars: int,
              output_chars: int, source: str, channel: str, message: str):
    """Append cost entry to shared JSONL log."""
    cost_gbp = cost_usd * USD_TO_GBP
    entry = {
        "timestamp": datetime.now().isoformat(),
        "source": source,
        "channel": channel,
        "message": message[:80],
        "cost_usd": round(cost_usd, 6),
        "cost_gbp": round(cost_gbp, 6),
        "model": KIMI_MODEL,
        "duration_ms": round(duration_ms, 1),
        "num_turns": 1,
        "tools_used": [],
        "response_chars": output_chars,
        "provider": "kimi",
    }

    try:
        COST_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(COST_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        logger.debug(f"Cost log write failed: {e}")

    logger.info(
        f"Kimi cost: ${cost_usd:.4f} (£{cost_gbp:.4f}) | "
        f"{duration_ms:.0f}ms | {output_chars} chars | {source}"
    )


DISCORD_FORMAT_RULES = """
### Discord Formatting Rules
- Discord does NOT render markdown tables. Use bullet lists with inline formatting.
- Use emoji indicators: ✅ for success, ❌ for failure, ⚠️ for warnings
- Section headers: emoji + **bold title**
- Keep responses compact — no excessive blank lines
- Code blocks use triple backticks with language hint
"""


async def invoke_kimi(
    context: str,
    timeout: int = KIMI_TIMEOUT,
    interim_callback: Optional[Callable[[str], Awaitable[None]]] = None,
    cost_source: str = "unknown",
    cost_channel: str = "",
    cost_message: str = "",
) -> str:
    """Call Kimi 2.5 API with context and return response text.

    Args:
        context: Full context string (same format as Claude gets via stdin)
        timeout: Max seconds for API call
        interim_callback: Optional async function for interim status updates
        cost_source: Label for cost log
        cost_channel: Channel name for cost log
        cost_message: Message preview for cost log

    Returns:
        Response text, or error message string
    """
    api_key = os.environ.get("MOONSHOT_API_KEY", "")
    if not api_key:
        logger.error("MOONSHOT_API_KEY not set — cannot use Kimi fallback")
        return "⚠️ Kimi fallback unavailable — API key not configured."

    # Build messages
    soul = _get_soul_prompt()
    system_prompt = f"{soul}\n\n{DISCORD_FORMAT_RULES}"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": context},
    ]

    # Post interim update if callback provided
    if interim_callback:
        try:
            await interim_callback("🔄 Using Kimi 2.5 fallback...")
        except Exception:
            pass

    wall_start = time.monotonic()

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{KIMI_API_BASE}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": KIMI_MODEL,
                    "messages": messages,
                    "max_tokens": KIMI_MAX_TOKENS,
                    "temperature": 0.7,
                },
            )

        duration_ms = (time.monotonic() - wall_start) * 1000

        if response.status_code != 200:
            error_body = response.text[:300]
            logger.error(f"Kimi API error {response.status_code}: {error_body}")
            return f"⚠️ Kimi API error ({response.status_code}). Please try again."

        data = response.json()
        result_text = data.get("choices", [{}])[0].get("message", {}).get("content", "")

        if not result_text:
            logger.error(f"Kimi returned empty response: {json.dumps(data)[:200]}")
            return "⚠️ Kimi returned an empty response. Please try again."

        # Estimate cost and log
        input_chars = len(system_prompt) + len(context)
        output_chars = len(result_text)

        # Use reported token counts if available
        usage = data.get("usage", {})
        if usage:
            input_tokens = usage.get("prompt_tokens", input_chars / CHARS_PER_TOKEN)
            output_tokens = usage.get("completion_tokens", output_chars / CHARS_PER_TOKEN)
            cost_usd = (input_tokens / 1_000_000 * KIMI_INPUT_COST_PER_M +
                        output_tokens / 1_000_000 * KIMI_OUTPUT_COST_PER_M)
        else:
            cost_usd = _estimate_cost(input_chars, output_chars)

        _log_cost(cost_usd, duration_ms, input_chars, output_chars,
                  cost_source, cost_channel, cost_message)

        increment_kimi_requests()
        return result_text

    except httpx.TimeoutException:
        duration_ms = (time.monotonic() - wall_start) * 1000
        logger.error(f"Kimi API timed out after {timeout}s ({duration_ms:.0f}ms)")
        return "⚠️ Kimi response timed out. Try a simpler question or try again."

    except httpx.ConnectError as e:
        logger.error(f"Kimi API connection error: {e}")
        return "⚠️ Could not connect to Kimi API. Please try again later."

    except Exception as e:
        logger.error(f"Kimi API unexpected error: {e}")
        return "⚠️ Kimi encountered an error. Please try again."
