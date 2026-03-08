"""Google AI (Gemini) API usage tracking via Supabase.

All Gemini consumers (Vinted Sniper, Hadley Bricks web, Review Queue)
log each API call to the gemini_api_usage table. This service aggregates
that data for the weekly summary and daily spend reports.
"""

import os
from datetime import datetime, timedelta, timezone

import httpx

from logger import logger

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")

# Published Gemini pricing (USD per 1M tokens) — input / output
GEMINI_PRICING = {
    "gemini-2.0-flash": {"input": 0.10, "output": 0.40, "free_tier": True},
    "gemini-2.5-flash": {"input": 0.15, "output": 3.50, "free_tier": True},
    "gemini-3-flash-preview": {"input": 0.15, "output": 0.60, "free_tier": False},
    "gemini-3-pro-preview": {"input": 1.25, "output": 10.00, "free_tier": False},
    "_default": {"input": 0.50, "output": 2.00, "free_tier": False},
}


async def _fetch_usage_rows(start_date: str) -> list[dict] | str:
    """Fetch usage rows from Supabase. Returns rows or error string."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return "Supabase not configured"

    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
    }

    all_rows = []
    offset = 0
    page_size = 1000

    async with httpx.AsyncClient() as client:
        while True:
            response = await client.get(
                f"{SUPABASE_URL}/rest/v1/gemini_api_usage",
                params={
                    "select": "model,consumer,input_tokens,output_tokens,total_tokens,success,created_at,metadata,response_time_ms",
                    "created_at": f"gte.{start_date}",
                    "order": "created_at.asc",
                    "limit": str(page_size),
                    "offset": str(offset),
                },
                headers=headers,
                timeout=15,
            )

            if response.status_code == 404:
                return "gemini_api_usage table not found — run the migration"

            if response.status_code != 200:
                return f"Supabase returned {response.status_code}"

            rows = response.json()
            all_rows.extend(rows)

            if len(rows) < page_size:
                break
            offset += page_size

    return all_rows


def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate cost for a model given token counts."""
    pricing = GEMINI_PRICING.get(model, GEMINI_PRICING["_default"])
    input_cost = input_tokens * pricing["input"] / 1_000_000
    output_cost = output_tokens * pricing["output"] / 1_000_000
    return input_cost + output_cost


async def get_google_usage(days: int = 7) -> dict:
    """Get Google AI (Gemini) API usage for a period."""
    try:
        start_date = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        result = await _fetch_usage_rows(start_date)

        if isinstance(result, str):
            return {"error": result, "total_cost": None}

        rows = result
        if not rows:
            return {
                "total_cost": 0,
                "total_requests": 0,
                "breakdown": {},
                "note": "No tracked Gemini API calls in this period",
            }

        # Aggregate by model
        breakdown = {}
        for row in rows:
            model = row.get("model", "unknown")
            input_tokens = row.get("input_tokens") or 0
            output_tokens = row.get("output_tokens") or 0
            consumer = row.get("consumer", "unknown")

            if model not in breakdown:
                pricing = GEMINI_PRICING.get(model, GEMINI_PRICING["_default"])
                breakdown[model] = {
                    "requests": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "estimated_cost": 0,
                    "free_tier": pricing.get("free_tier", False),
                    "consumers": {},
                }

            breakdown[model]["requests"] += 1
            breakdown[model]["input_tokens"] += input_tokens
            breakdown[model]["output_tokens"] += output_tokens
            breakdown[model]["consumers"][consumer] = (
                breakdown[model]["consumers"].get(consumer, 0) + 1
            )

        # Calculate costs
        total_cost = 0
        for model, info in breakdown.items():
            cost = _estimate_cost(model, info["input_tokens"], info["output_tokens"])
            info["estimated_cost"] = round(cost, 3)
            total_cost += cost

        total_requests = sum(m["requests"] for m in breakdown.values())

        logger.info(
            f"Google AI usage: ~${total_cost:.2f} ({total_requests} requests) for {days} days"
        )

        return {
            "total_cost": round(total_cost, 2),
            "total_requests": total_requests,
            "breakdown": breakdown,
        }

    except Exception as e:
        logger.error(f"Google usage error: {e}")
        return {"error": str(e), "total_cost": None}


async def get_google_daily_breakdown(days: int = 7) -> dict:
    """Get day-by-day Google AI spend for focused cost analysis."""
    try:
        start_date = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        result = await _fetch_usage_rows(start_date)

        if isinstance(result, str):
            return {"error": result, "days": []}

        rows = result
        if not rows:
            return {"days": []}

        # Group by day, model, consumer
        daily = {}
        for row in rows:
            day = row["created_at"][:10]
            model = row.get("model", "unknown")
            consumer = row.get("consumer", "unknown")
            input_tokens = row.get("input_tokens") or 0
            output_tokens = row.get("output_tokens") or 0

            if day not in daily:
                daily[day] = {}
            if model not in daily[day]:
                daily[day][model] = {
                    "requests": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "consumers": {},
                }

            daily[day][model]["requests"] += 1
            daily[day][model]["input_tokens"] += input_tokens
            daily[day][model]["output_tokens"] += output_tokens
            daily[day][model]["consumers"][consumer] = (
                daily[day][model]["consumers"].get(consumer, 0) + 1
            )

        result_days = []
        for day in sorted(daily.keys()):
            models = daily[day]
            day_cost = 0
            model_details = []

            for model, info in models.items():
                cost = _estimate_cost(model, info["input_tokens"], info["output_tokens"])
                pricing = GEMINI_PRICING.get(model, GEMINI_PRICING["_default"])
                is_free = pricing.get("free_tier", False)
                day_cost += cost

                model_details.append({
                    "model": model,
                    "requests": info["requests"],
                    "input_tokens": info["input_tokens"],
                    "output_tokens": info["output_tokens"],
                    "estimated_cost": round(cost, 3),
                    "free_tier": is_free,
                    "consumers": info["consumers"],
                })

            result_days.append({
                "date": day,
                "total_requests": sum(m["requests"] for m in model_details),
                "estimated_cost": round(day_cost, 2),
                "models": model_details,
            })

        return {"days": result_days}

    except Exception as e:
        logger.error(f"Google daily breakdown error: {e}")
        return {"error": str(e), "days": []}


async def get_vision_effectiveness(days: int = 1) -> dict:
    """Get Vinted Sniper vision effectiveness stats.

    Returns hit/miss rates and per-day breakdown for gemini-2.0-flash
    calls that have set_found tracking in metadata.
    """
    try:
        start_date = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        result = await _fetch_usage_rows(start_date)

        if isinstance(result, str):
            return {"error": result}

        # Filter to vinted-sniper calls with effectiveness data
        tracked = [
            r for r in result
            if r.get("consumer") == "vinted-sniper"
            and r.get("metadata")
            and "set_found" in (r.get("metadata") or {})
        ]

        if not tracked:
            return {"total": 0, "note": "No tracked vision calls yet"}

        found = [r for r in tracked if r["metadata"].get("set_found")]
        missed = [r for r in tracked if not r["metadata"].get("set_found")]

        # Per-day breakdown
        daily = {}
        for row in tracked:
            day = row["created_at"][:10]
            if day not in daily:
                daily[day] = {"found": 0, "missed": 0, "sets": []}
            if row["metadata"].get("set_found"):
                daily[day]["found"] += 1
                sn = row["metadata"].get("set_number")
                if sn:
                    daily[day]["sets"].append(sn)
            else:
                daily[day]["missed"] += 1

        daily_list = []
        for day in sorted(daily.keys()):
            d = daily[day]
            total = d["found"] + d["missed"]
            daily_list.append({
                "date": day,
                "total": total,
                "found": d["found"],
                "missed": d["missed"],
                "hit_rate_pct": round(100 * d["found"] / total, 1) if total else 0,
                "sets_identified": d["sets"],
            })

        # Avg response time
        times = [r.get("response_time_ms") for r in tracked if r.get("response_time_ms")]
        avg_ms = round(sum(times) / len(times)) if times else None

        return {
            "total": len(tracked),
            "found": len(found),
            "missed": len(missed),
            "hit_rate_pct": round(100 * len(found) / len(tracked), 1),
            "avg_response_ms": avg_ms,
            "daily": daily_list,
            "sets_identified": [r["metadata"].get("set_number") for r in found if r["metadata"].get("set_number")],
        }

    except Exception as e:
        logger.error(f"Vision effectiveness error: {e}")
        return {"error": str(e)}
