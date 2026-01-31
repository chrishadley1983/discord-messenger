"""OpenAI API usage tracking."""

from datetime import datetime, timedelta

import httpx

from config import OPENAI_API_KEY
from logger import logger


async def get_openai_usage(days: int = 7) -> dict:
    """Get OpenAI API usage for a period."""
    try:
        if not OPENAI_API_KEY:
            return {"error": "OpenAI API key not configured", "total_cost": None}

        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        # OpenAI usage API endpoint
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.openai.com/v1/dashboard/billing/usage",
                params={
                    "start_date": start_date.strftime("%Y-%m-%d"),
                    "end_date": end_date.strftime("%Y-%m-%d")
                },
                headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}"
                },
                timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                total_cost = data.get("total_usage", 0) / 100  # Convert cents to dollars

                result = {
                    "total_cost": round(total_cost, 2),
                    "breakdown": data.get("daily_costs", []),
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat()
                }

                logger.info(f"OpenAI usage: ${total_cost:.2f} for {days} days")
                return result
            else:
                logger.warning(f"OpenAI usage API returned {response.status_code}")
                return {
                    "error": f"API returned {response.status_code}",
                    "total_cost": None,
                    "note": "Check platform.openai.com/usage manually"
                }
    except Exception as e:
        logger.error(f"OpenAI usage error: {e}")
        return {"error": str(e), "total_cost": None}
