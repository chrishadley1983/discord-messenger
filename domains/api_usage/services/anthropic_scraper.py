"""Anthropic Console Usage Scraper.

Uses saved session cookies to scrape usage data from the Anthropic console.
"""

import json
import re
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

# Try playwright
try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

STORAGE_PATH = Path(__file__).parent.parent.parent.parent / "data" / "anthropic_session.json"
BILLING_URL = "https://console.anthropic.com/settings/billing"


@dataclass
class AnthropicUsage:
    """Anthropic usage data."""
    current_month_cost: float
    current_month_tokens: int
    credit_balance: Optional[float] = None
    period: str = ""


def get_anthropic_usage() -> Optional[AnthropicUsage]:
    """Scrape usage data from Anthropic console.

    Returns None if session is expired or scraping fails.
    """
    if not PLAYWRIGHT_AVAILABLE:
        return None

    if not STORAGE_PATH.exists():
        return None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)

            # Load saved session
            with open(STORAGE_PATH) as f:
                storage_state = json.load(f)

            context = browser.new_context(storage_state=storage_state)
            page = context.new_page()

            # Navigate to usage page
            page.goto(BILLING_URL)
            page.wait_for_load_state("networkidle")

            # Check if redirected to login (session expired)
            if "login" in page.url or "sign" in page.url:
                browser.close()
                return None

            # Wait for usage data to load
            page.wait_for_timeout(2000)

            # Extract usage data from page
            content = page.content()

            # Try to find cost information
            # The page structure may vary, so we try multiple patterns
            cost = 0.0
            tokens = 0

            # Look for dollar amounts (e.g., "$12.34" or "12.34 USD")
            cost_matches = re.findall(r'\$(\d+(?:\.\d{2})?)', content)
            if cost_matches:
                # Take the largest value as likely the current usage
                cost = max(float(m) for m in cost_matches)

            # Look for token counts (e.g., "1,234,567 tokens")
            token_matches = re.findall(r'([\d,]+)\s*tokens?', content, re.IGNORECASE)
            if token_matches:
                # Filter out empty matches and convert
                valid_tokens = []
                for m in token_matches:
                    cleaned = m.replace(',', '').strip()
                    if cleaned and cleaned.isdigit():
                        valid_tokens.append(int(cleaned))
                if valid_tokens:
                    tokens = max(valid_tokens)

            # Look for credit balance - try multiple patterns
            credit_balance = None

            # Pattern 1: "US$X.XX" anywhere near "Remaining Balance" (with HTML tags between)
            remaining_match = re.search(r'US\$(\d+(?:\.\d{2})?).*?Remaining\s*Balance', content, re.IGNORECASE | re.DOTALL)
            if remaining_match:
                credit_balance = float(remaining_match.group(1))

            # Pattern 2: Look for the visible text pattern directly
            if credit_balance is None:
                # The page shows "US$3.56" then later "Remaining Balance"
                us_dollar_matches = re.findall(r'US\$(\d+\.\d{2})', content)
                if us_dollar_matches:
                    # Take the first one (usually the main balance display)
                    credit_balance = float(us_dollar_matches[0])

            # Pattern 3: Fallback to older pattern
            if credit_balance is None:
                credit_matches = re.findall(r'[Cc]redit[s]?[:\s]+\$?(\d+(?:\.\d{2})?)', content)
                if credit_matches:
                    credit_balance = float(credit_matches[0])

            # Try to get the billing period
            period = ""
            period_match = re.search(r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}', content)
            if period_match:
                period = period_match.group(0)

            browser.close()

            return AnthropicUsage(
                current_month_cost=cost,
                current_month_tokens=tokens,
                credit_balance=credit_balance,
                period=period
            )

    except Exception as e:
        print(f"Error scraping Anthropic usage: {e}")
        return None


def is_session_valid() -> bool:
    """Check if saved session is still valid."""
    if not STORAGE_PATH.exists():
        return False

    usage = get_anthropic_usage()
    return usage is not None


def get_session_status() -> str:
    """Get human-readable session status."""
    if not PLAYWRIGHT_AVAILABLE:
        return "Playwright not installed"

    if not STORAGE_PATH.exists():
        return "No session saved - run anthropic_auth.py"

    if is_session_valid():
        return "Session valid"
    else:
        return "Session expired - run anthropic_auth.py to re-authenticate"
