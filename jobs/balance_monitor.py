"""API Balance Monitoring scheduled job.

Runs hourly to check Claude and Moonshot Kimi API balances.
Posts to #api-costs with alerts if balance < $5.
"""

from datetime import datetime
from pathlib import Path

import httpx

from config import (
    SUPABASE_URL,
    SUPABASE_KEY,
    MOONSHOT_API_KEY,
    CLAUDE_BALANCE_LOG,
    MOONSHOT_BALANCE_LOG,
    GROK_MANAGEMENT_KEY,
    GROK_TEAM_ID
)
from logger import logger
from domains.api_usage.services.anthropic_scraper import get_anthropic_usage as scrape_anthropic

# Channel ID for #api-costs
API_COSTS_CHANNEL_ID = 1465761699582972142

# Alert threshold
BALANCE_THRESHOLD = 5.00


def _get_supabase_headers():
    """Get headers for Supabase API calls."""
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json"
    }


async def _get_claude_balance() -> dict:
    """Get Claude balance by scraping the Anthropic console."""
    import asyncio
    import concurrent.futures

    def _scrape_sync():
        """Run the sync Playwright scraper in a thread."""
        return scrape_anthropic()

    try:
        # Run sync Playwright in a thread pool to avoid async conflict
        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            usage = await loop.run_in_executor(pool, _scrape_sync)

        if usage is not None:
            # Return the credit balance if available, otherwise the current month cost
            if usage.credit_balance is not None:
                return {"balance": usage.credit_balance, "source": "console"}
            else:
                return {
                    "balance": None,
                    "current_month_cost": usage.current_month_cost,
                    "note": "Credit balance not available, showing monthly cost"
                }
        else:
            return {"balance": None, "error": "Session expired - run anthropic_auth.py"}
    except Exception as e:
        logger.error(f"Claude balance query error: {e}")
        return {"error": str(e), "balance": None}


async def _get_grok_balance() -> dict:
    """Get xAI Grok balance via management API.

    xAI uses a management API at https://management-api.x.ai (separate from inference API).
    Balance is calculated as: prepaid credits - total usage (from /usage analytics endpoint).
    See: https://docs.x.ai/developers/management-api/billing
    """
    from datetime import datetime

    try:
        if not GROK_MANAGEMENT_KEY or not GROK_TEAM_ID:
            return {"error": "Grok management credentials not configured", "balance": None}

        headers = {
            "Authorization": f"Bearer {GROK_MANAGEMENT_KEY}",
            "Content-Type": "application/json"
        }
        base_url = "https://management-api.x.ai"

        async with httpx.AsyncClient() as client:
            # 1. Get prepaid credits (purchase history)
            prepaid_url = f"{base_url}/v1/billing/teams/{GROK_TEAM_ID}/prepaid/balance"
            prepaid_resp = await client.get(prepaid_url, headers=headers, timeout=30)

            if prepaid_resp.status_code != 200:
                return {"error": f"Prepaid API HTTP {prepaid_resp.status_code}", "balance": None, "check": "console.x.ai"}

            prepaid_data = prepaid_resp.json()

            # Sum all successful prepaid purchases (negative values = credits in accounting)
            prepaid_cents = 0
            for change in prepaid_data.get("changes", []):
                if change.get("changeOrigin") == "PURCHASE" and change.get("topupStatus") == "SUCCEEDED":
                    prepaid_cents += abs(int(change.get("amount", {}).get("val", 0)))
            prepaid_usd = prepaid_cents / 100

            # 2. Get total usage via analytics endpoint (real-time)
            usage_url = f"{base_url}/v1/billing/teams/{GROK_TEAM_ID}/usage"
            usage_body = {
                "analyticsRequest": {
                    "timeRange": {
                        "startTime": "2025-01-01 00:00:00",
                        "endTime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "timezone": "Etc/GMT"
                    },
                    "timeUnit": "TIME_UNIT_DAY",
                    "values": [
                        {"name": "usd", "aggregation": "AGGREGATION_SUM"}
                    ],
                    "groupBy": [],
                    "filters": []
                }
            }
            usage_resp = await client.post(usage_url, headers=headers, json=usage_body, timeout=30)

            if usage_resp.status_code != 200:
                return {"error": f"Usage API HTTP {usage_resp.status_code}", "balance": None, "check": "console.x.ai"}

            usage_data = usage_resp.json()

            # Sum all usage from time series data
            total_usage = 0.0
            for series in usage_data.get("timeSeries", []):
                for dp in series.get("dataPoints", []):
                    for val in dp.get("values", []):
                        total_usage += val

            # Calculate remaining balance
            remaining = prepaid_usd - total_usage

            return {"balance": round(remaining, 2), "source": "api"}

    except Exception as e:
        logger.error(f"Grok balance query error: {e}")
        return {"error": str(e), "balance": None, "check": "console.x.ai"}


async def _get_moonshot_balance() -> dict:
    """Get Moonshot Kimi balance via REST API."""
    try:
        if not MOONSHOT_API_KEY:
            return {"error": "Moonshot API key not configured", "balance": None}

        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.moonshot.ai/v1/users/me/balance",
                headers={"Authorization": f"Bearer {MOONSHOT_API_KEY}"},
                timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                if data.get("code") == 0:
                    return {
                        "balance": float(data["data"]["available_balance"]),
                        "voucher": float(data["data"].get("voucher_balance", 0)),
                        "cash": float(data["data"].get("cash_balance", 0))
                    }
                else:
                    return {"error": f"API error code: {data.get('code')}", "balance": None}
            else:
                return {"error": f"HTTP {response.status_code}", "balance": None}
    except Exception as e:
        logger.error(f"Moonshot balance query error: {e}")
        return {"error": str(e), "balance": None}


def _log_balance(log_file: Path, service: str, balance: float | None):
    """Log balance to file."""
    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        balance_str = f"${balance:.2f}" if balance is not None else "N/A"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {service}: {balance_str}\n")
    except Exception as e:
        logger.warning(f"Failed to log balance: {e}")


async def balance_monitor(bot):
    """Check and report API balances."""
    logger.info(f"Balance monitor starting - looking for channel {API_COSTS_CHANNEL_ID}")
    channel = bot.get_channel(API_COSTS_CHANNEL_ID)
    if not channel:
        # Try fetching the channel if not in cache
        try:
            channel = await bot.fetch_channel(API_COSTS_CHANNEL_ID)
        except Exception as e:
            logger.error(f"Could not find or fetch #api-costs channel {API_COSTS_CHANNEL_ID}: {e}")
            return
    logger.info(f"Found channel: {channel.name}")

    try:
        claude_data = await _get_claude_balance()
        moonshot_data = await _get_moonshot_balance()

        # Log balances
        _log_balance(CLAUDE_BALANCE_LOG, "Claude", claude_data.get("balance"))
        _log_balance(MOONSHOT_BALANCE_LOG, "Moonshot", moonshot_data.get("balance"))

        # Build message
        lines = ["💰 **API Balance Summary**", ""]

        # Claude balance
        claude_balance = claude_data.get("balance")
        if claude_balance is not None:
            emoji = "⚠️" if claude_balance < BALANCE_THRESHOLD else "💳"
            lines.append(f"{emoji} **Claude:** ${claude_balance:.2f} (threshold: ${BALANCE_THRESHOLD:.2f})")
        elif claude_data.get("current_month_cost") is not None:
            lines.append(f"💳 **Claude:** ${claude_data['current_month_cost']:.2f} spent this month")
        else:
            lines.append(f"💳 **Claude:** {claude_data.get('error', 'unavailable')}")

        # Moonshot balance
        moonshot_balance = moonshot_data.get("balance")
        if moonshot_balance is not None:
            emoji = "⚠️" if moonshot_balance < BALANCE_THRESHOLD else "🌙"
            lines.append(f"{emoji} **Kimi:** ${moonshot_balance:.2f} available (threshold: ${BALANCE_THRESHOLD:.2f})")
        else:
            lines.append(f"🌙 **Kimi:** {moonshot_data.get('error', 'unavailable')}")

        # Add alerts if needed
        alerts = []
        if claude_balance is not None and claude_balance < BALANCE_THRESHOLD:
            alerts.append("⚠️ Claude credits low!")
        if moonshot_balance is not None and moonshot_balance < BALANCE_THRESHOLD:
            alerts.append("⚠️ Kimi credits low!")

        if alerts:
            lines.append("")
            lines.extend(alerts)

        message = "\n".join(lines)
        await channel.send(message)
        logger.info(f"Posted balance summary - Claude: ${claude_balance}, Kimi: ${moonshot_balance}")

    except Exception as e:
        logger.error(f"Failed to post balance summary: {e}")


def register_balance_monitor(scheduler, bot):
    """Register the balance monitor job with the scheduler."""
    scheduler.add_job(
        balance_monitor,
        'cron',
        args=[bot],
        hour='7-21',  # 7am to 9pm UK time only
        minute=0,  # Top of every hour
        timezone="Europe/London",
        id="api_balance_monitor"
    )
    logger.info("Registered API balance monitor job (hourly, 7am-9pm UK)")
