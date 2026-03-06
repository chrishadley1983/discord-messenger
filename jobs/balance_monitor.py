"""API Balance Monitoring scheduled job.

Runs hourly to check balances and daily costs across AI platforms:
  - Anthropic API (credit balance + month spend via console scraping)
  - xAI Grok (prepaid balance + today's cost via management API)
  - Moonshot Kimi (balance via REST API)

Posts to #api-costs with alerts if any balance < $5.
"""

from datetime import datetime, timezone
from pathlib import Path

import httpx

from config import (
    MOONSHOT_API_KEY,
    CLAUDE_BALANCE_LOG,
    MOONSHOT_BALANCE_LOG,
    GROK_MANAGEMENT_KEY,
    GROK_TEAM_ID
)
from logger import logger
from domains.api_usage.services.anthropic_scraper import get_anthropic_usage as scrape_anthropic

# Claude Code OAuth credentials path
CLAUDE_CODE_CREDS = Path.home() / ".claude" / ".credentials.json"
CLAUDE_OAUTH_USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
CLAUDE_OAUTH_TOKEN_URL = "https://console.anthropic.com/api/oauth/token"
CLAUDE_OAUTH_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"

# Channel ID for #api-costs
API_COSTS_CHANNEL_ID = 1465761699582972142

# Alert threshold
BALANCE_THRESHOLD = 5.00


async def _get_max_usage() -> dict:
    """Get Claude Max subscription utilization via OAuth usage endpoint.

    Returns dict with: five_hour, seven_day, seven_day_opus, seven_day_sonnet, extra_usage, error
    """
    import json

    try:
        if not CLAUDE_CODE_CREDS.exists():
            return {"error": "No Claude Code credentials found"}

        with open(CLAUDE_CODE_CREDS) as f:
            creds = json.load(f)

        oauth = creds.get("claudeAiOauth", {})
        access_token = oauth.get("accessToken")
        refresh_token = oauth.get("refreshToken")
        expires_at = oauth.get("expiresAt", 0)

        if not access_token:
            return {"error": "No OAuth access token"}

        # Refresh token if expired (expiresAt is milliseconds)
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        if now_ms >= expires_at and refresh_token:
            logger.info("Claude OAuth token expired, refreshing...")
            async with httpx.AsyncClient() as client:
                resp = await client.post(CLAUDE_OAUTH_TOKEN_URL, json={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": CLAUDE_OAUTH_CLIENT_ID,
                }, timeout=15)

                if resp.status_code == 200:
                    new_tokens = resp.json()
                    access_token = new_tokens["access_token"]
                    # Update credentials file
                    oauth["accessToken"] = access_token
                    oauth["refreshToken"] = new_tokens.get("refresh_token", refresh_token)
                    oauth["expiresAt"] = int(datetime.now(timezone.utc).timestamp() * 1000) + (new_tokens.get("expires_in", 28800) * 1000)
                    creds["claudeAiOauth"] = oauth
                    with open(CLAUDE_CODE_CREDS, "w") as f:
                        json.dump(creds, f)
                    logger.info("Claude OAuth token refreshed successfully")
                else:
                    logger.warning(f"Token refresh failed: {resp.status_code}")

        headers = {
            "Authorization": f"Bearer {access_token}",
            "anthropic-beta": "oauth-2025-04-20",
            "Accept": "application/json",
        }

        async with httpx.AsyncClient() as client:
            resp = await client.get(CLAUDE_OAUTH_USAGE_URL, headers=headers, timeout=15)

            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 401:
                return {"error": "OAuth token expired - re-auth Claude Code"}
            else:
                return {"error": f"HTTP {resp.status_code}"}

    except Exception as e:
        logger.error(f"Max usage query error: {e}")
        return {"error": str(e)}


async def _get_claude_data() -> dict:
    """Get Claude API credit balance and month spend via console scraping.

    Returns dict with: balance, current_month_cost, period, error
    """
    import asyncio
    import concurrent.futures

    def _scrape_sync():
        return scrape_anthropic()

    try:
        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            usage = await loop.run_in_executor(pool, _scrape_sync)

        if usage is not None:
            return {
                "balance": usage.credit_balance,
                "current_month_cost": usage.current_month_cost,
                "period": usage.period,
                "source": usage.source
            }
        else:
            return {"balance": None, "error": "Session expired - run anthropic_auth.py"}
    except Exception as e:
        logger.error(f"Claude balance query error: {e}")
        return {"error": str(e), "balance": None}


async def _get_grok_data() -> dict:
    """Get xAI Grok balance and today's cost via management API.

    Returns dict with: balance, today_cost, error
    """
    try:
        if not GROK_MANAGEMENT_KEY or not GROK_TEAM_ID:
            return {"error": "Grok management credentials not configured", "balance": None}

        headers = {
            "Authorization": f"Bearer {GROK_MANAGEMENT_KEY}",
            "Content-Type": "application/json"
        }
        base_url = "https://management-api.x.ai"

        async with httpx.AsyncClient() as client:
            # 1. Get prepaid credits
            prepaid_resp = await client.get(
                f"{base_url}/v1/billing/teams/{GROK_TEAM_ID}/prepaid/balance",
                headers=headers, timeout=30
            )

            if prepaid_resp.status_code == 401:
                return {"error": "Management key expired - regenerate at console.x.ai", "balance": None}

            if prepaid_resp.status_code != 200:
                return {"error": f"Prepaid API HTTP {prepaid_resp.status_code}", "balance": None}

            prepaid_data = prepaid_resp.json()

            # Sum successful prepaid purchases
            prepaid_cents = 0
            for change in prepaid_data.get("changes", []):
                if change.get("changeOrigin") == "PURCHASE" and change.get("topupStatus") == "SUCCEEDED":
                    prepaid_cents += abs(int(change.get("amount", {}).get("val", 0)))
            prepaid_usd = prepaid_cents / 100

            # 2. Get all-time usage (for balance calculation)
            now = datetime.now(timezone.utc)
            usage_body = {
                "analyticsRequest": {
                    "timeRange": {
                        "startTime": "2025-01-01 00:00:00",
                        "endTime": now.strftime("%Y-%m-%d %H:%M:%S"),
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
            usage_resp = await client.post(
                f"{base_url}/v1/billing/teams/{GROK_TEAM_ID}/usage",
                headers=headers, json=usage_body, timeout=30
            )

            if usage_resp.status_code != 200:
                return {"error": f"Usage API HTTP {usage_resp.status_code}", "balance": None}

            usage_data = usage_resp.json()

            # Sum all usage and extract today's cost
            total_usage = 0.0
            today_cost = 0.0
            today_str = now.strftime("%Y-%m-%d")

            for series in usage_data.get("timeSeries", []):
                for dp in series.get("dataPoints", []):
                    values = dp.get("values", [])
                    cost = values[0] if values else 0.0

                    total_usage += cost

                    # Check if this datapoint is today
                    ts = dp.get("timestamp", "")
                    if ts.startswith(today_str):
                        today_cost = cost

            remaining = prepaid_usd - total_usage

            return {
                "balance": round(remaining, 2),
                "today_cost": round(today_cost, 4),
                "source": "api"
            }

    except Exception as e:
        logger.error(f"Grok balance query error: {e}")
        return {"error": str(e), "balance": None}


async def _get_moonshot_data() -> dict:
    """Get Moonshot Kimi balance via REST API.

    Returns dict with: balance, voucher, cash, error
    """
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


def _format_message(claude_data: dict, grok_data: dict, kimi_data: dict, max_data: dict) -> str:
    """Format the Discord message with all platform data."""
    lines = ["**AI Platform Summary**", ""]

    # Claude Max subscription usage
    five_hour = max_data.get("five_hour")
    seven_day = max_data.get("seven_day")
    if five_hour and seven_day:
        five_pct = five_hour.get("utilization", 0)
        seven_pct = seven_day.get("utilization", 0)
        # Show per-model breakdown if available
        model_parts = []
        for key, label in [("seven_day_opus", "Opus"), ("seven_day_sonnet", "Sonnet")]:
            model = max_data.get(key)
            if model and model.get("utilization") is not None:
                model_parts.append(f"{label} {model['utilization']:.0f}%")
        model_str = f" ({', '.join(model_parts)})" if model_parts else ""
        # Reset time for 5h window
        resets = five_hour.get("resets_at", "")
        reset_str = ""
        if resets:
            try:
                from datetime import datetime as dt
                reset_dt = dt.fromisoformat(resets)
                reset_str = f" | 5h resets {reset_dt.strftime('%H:%M')}"
            except Exception:
                pass
        emoji = "\u26a0\ufe0f" if five_pct >= 80 or seven_pct >= 80 else "\U0001f4bb"
        lines.append(f"{emoji} **Max 20x:** 5h: {five_pct:.0f}% | 7d: {seven_pct:.0f}%{model_str}{reset_str}")
    elif max_data.get("error"):
        lines.append(f"\U0001f4bb **Max:** {max_data['error']}")

    # Grok
    grok_balance = grok_data.get("balance")
    grok_today = grok_data.get("today_cost")
    if grok_balance is not None:
        emoji = "\u26a0\ufe0f" if grok_balance < BALANCE_THRESHOLD else "\U0001f916"
        cost_part = f" | Today: ${grok_today:.2f}" if grok_today is not None else ""
        lines.append(f"{emoji} **Grok:** ${grok_balance:.2f} balance{cost_part}")
    else:
        lines.append(f"\U0001f916 **Grok:** {grok_data.get('error', 'unavailable')}")

    # Anthropic API credits
    claude_balance = claude_data.get("balance")
    claude_month = claude_data.get("current_month_cost")
    claude_period = claude_data.get("period", "")
    if claude_balance is not None:
        emoji = "\u26a0\ufe0f" if claude_balance < BALANCE_THRESHOLD else "\U0001f52e"
        month_part = f" | {claude_period}: ${claude_month:.2f}" if claude_month else ""
        lines.append(f"{emoji} **Anthropic API:** ${claude_balance:.2f} credits{month_part}")
    elif claude_month is not None:
        lines.append(f"\U0001f52e **Anthropic API:** ${claude_month:.2f} spent {claude_period}")
    else:
        lines.append(f"\U0001f52e **Anthropic API:** {claude_data.get('error', 'unavailable')}")

    # Kimi
    kimi_balance = kimi_data.get("balance")
    if kimi_balance is not None:
        emoji = "\u26a0\ufe0f" if kimi_balance < BALANCE_THRESHOLD else "\U0001f319"
        lines.append(f"{emoji} **Kimi:** ${kimi_balance:.2f} available")
    else:
        lines.append(f"\U0001f319 **Kimi:** {kimi_data.get('error', 'unavailable')}")

    # Alerts
    alerts = []
    if five_hour and five_hour.get("utilization", 0) >= 80:
        alerts.append("\u26a0\ufe0f Max 5h window at {:.0f}%!".format(five_hour["utilization"]))
    if seven_day and seven_day.get("utilization", 0) >= 80:
        alerts.append("\u26a0\ufe0f Max 7d window at {:.0f}%!".format(seven_day["utilization"]))
    if claude_balance is not None and claude_balance < BALANCE_THRESHOLD:
        alerts.append("\u26a0\ufe0f Anthropic API credits low!")
    if grok_balance is not None and grok_balance < BALANCE_THRESHOLD:
        alerts.append("\u26a0\ufe0f Grok credits low!")
    if kimi_balance is not None and kimi_balance < BALANCE_THRESHOLD:
        alerts.append("\u26a0\ufe0f Kimi credits low!")

    if alerts:
        lines.append("")
        lines.extend(alerts)

    return "\n".join(lines)


async def balance_monitor(bot):
    """Check and report API balances across all platforms."""
    logger.info(f"Balance monitor starting - looking for channel {API_COSTS_CHANNEL_ID}")
    channel = bot.get_channel(API_COSTS_CHANNEL_ID)
    if not channel:
        try:
            channel = await bot.fetch_channel(API_COSTS_CHANNEL_ID)
        except Exception as e:
            logger.error(f"Could not find or fetch #api-costs channel {API_COSTS_CHANNEL_ID}: {e}")
            return
    logger.info(f"Found channel: {channel.name}")

    try:
        # Fetch all platform data concurrently
        import asyncio
        claude_data, grok_data, kimi_data, max_data = await asyncio.gather(
            _get_claude_data(),
            _get_grok_data(),
            _get_moonshot_data(),
            _get_max_usage(),
            return_exceptions=False
        )

        # Log balances
        _log_balance(CLAUDE_BALANCE_LOG, "Claude", claude_data.get("balance"))
        _log_balance(MOONSHOT_BALANCE_LOG, "Moonshot", kimi_data.get("balance"))

        # Format and send
        message = _format_message(claude_data, grok_data, kimi_data, max_data)
        await channel.send(message)

        logger.info(
            f"Posted balance summary - "
            f"Claude: ${claude_data.get('balance')}, "
            f"Grok: ${grok_data.get('balance')}, "
            f"Kimi: ${kimi_data.get('balance')}, "
            f"Max 5h: {max_data.get('five_hour', {}).get('utilization')}%"
        )

    except Exception as e:
        logger.error(f"Failed to post balance summary: {e}")


def register_balance_monitor(scheduler, bot):
    """Register the balance monitor job with the scheduler."""
    scheduler.add_job(
        balance_monitor,
        'cron',
        args=[bot],
        hour='7-21',  # 7am to 9pm UK time only
        minute=0,     # Top of every hour
        timezone="Europe/London",
        id="api_balance_monitor"
    )
    logger.info("Registered API balance monitor job (hourly, 7am-9pm UK)")
