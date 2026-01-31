"""Anthropic API usage tracking via console scraping."""

from datetime import datetime, timedelta

from logger import logger
from .anthropic_scraper import get_anthropic_usage as scrape_usage, get_session_status


async def get_anthropic_usage(days: int = 7) -> dict:
    """Get Claude API usage by scraping the Anthropic console.

    Uses saved session cookies from anthropic_auth.py script.
    """
    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        # Try to scrape usage data
        usage = scrape_usage()

        if usage is None:
            # Session expired or not set up
            status = get_session_status()
            logger.warning(f"Anthropic scraping unavailable: {status}")
            return {
                "total_cost": None,
                "session_status": status,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "note": f"Run 'python scripts/anthropic_auth.py' to authenticate. Status: {status}"
            }

        result = {
            "total_cost": usage.current_month_cost,
            "total_tokens": usage.current_month_tokens,
            "credit_balance": usage.credit_balance,
            "period": usage.period or f"{start_date.strftime('%B %Y')}",
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "session_status": "valid"
        }

        logger.info(f"Anthropic usage scraped: ${usage.current_month_cost:.2f}")
        return result

    except Exception as e:
        logger.error(f"Anthropic usage error: {e}")
        return {"error": str(e), "total_cost": None}
