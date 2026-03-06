"""Anthropic Console Usage Scraper.

Uses Playwright to scrape billing data from the Anthropic console.
Two strategies:
  1. Network interception - capture JSON API responses the console frontend makes
  2. Element extraction - use Playwright selectors on visible page text (fallback)
"""

import json
import logging
import re
import time
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Circuit breaker: after N consecutive failures, skip scraping for a cooldown period
_consecutive_failures = 0
_circuit_open_until = 0.0
_FAILURE_THRESHOLD = 3      # Open circuit after 3 consecutive failures
_COOLDOWN_SECONDS = 1800    # Stay open for 30 minutes

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

STORAGE_PATH = Path(__file__).parent.parent.parent.parent / "data" / "anthropic_session.json"

# Console has moved from console.anthropic.com to platform.claude.com
BILLING_URL = "https://platform.claude.com/settings/billing"
COST_URL = "https://platform.claude.com/settings/cost"
USAGE_URL = "https://platform.claude.com/settings/usage"

# Fallback to old domain if new one fails
LEGACY_BILLING_URL = "https://console.anthropic.com/settings/billing"


@dataclass
class AnthropicUsage:
    """Anthropic usage data."""
    current_month_cost: float = 0.0
    current_month_tokens: int = 0
    credit_balance: Optional[float] = None
    period: str = ""
    source: str = ""  # "network" or "element" or "regex"


def _intercept_api_data(page) -> dict:
    """Capture JSON data from the console's internal API calls.

    The billing page makes these key requests:
      /api/organizations/{id}/prepaid/credits  -> {"amount": 905, "currency": "USD"}  (cents)
      /api/organizations/{id}/current_spend    -> {"amount": 137, "resets_at": "..."}  (cents)
      /api/organizations/{id}/invoiced_balance -> {"amount": 0, "resets_at": "..."}    (cents)
    """
    captured = {}

    def handle_response(response):
        url = response.url
        try:
            ct = response.headers.get("content-type", "")
            if response.status == 200 and "json" in ct and "/api/" in url:
                data = response.json()
                captured[url] = data
                logger.info(f"Captured API response from: {url}")
        except Exception as e:
            logger.debug(f"Failed to parse response from {url}: {e}")

    page.on("response", handle_response)
    return captured


def _extract_from_api_data(captured: dict) -> Optional[AnthropicUsage]:
    """Parse captured API responses from known console endpoints.

    Known endpoints (all amounts in cents):
      /prepaid/credits   -> {"amount": 905}           = $9.05 credit balance
      /current_spend     -> {"amount": 137}            = $1.37 current month spend
      /invoiced_balance  -> {"amount": 0, "resets_at"} = outstanding invoice balance
    """
    if not captured:
        return None

    credit_balance = None
    current_month_cost = 0.0
    period = ""

    for url, data in captured.items():
        if not isinstance(data, dict):
            continue

        # /prepaid/credits -> credit balance in cents
        if "prepaid/credits" in url:
            amount = data.get("amount")
            if isinstance(amount, (int, float)):
                credit_balance = amount / 100.0
                logger.info(f"Credit balance: ${credit_balance:.2f} (from {amount} cents)")

        # /current_spend -> month-to-date spend in cents
        elif "current_spend" in url:
            amount = data.get("amount")
            if isinstance(amount, (int, float)):
                current_month_cost = amount / 100.0
                logger.info(f"Current month spend: ${current_month_cost:.2f} (from {amount} cents)")
            resets_at = data.get("resets_at", "")
            if resets_at:
                # Extract month from reset date (e.g., "2026-04-01" means current period is March)
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(resets_at.replace("Z", "+00:00"))
                    # Period is the month before the reset
                    month_names = ["January", "February", "March", "April", "May", "June",
                                   "July", "August", "September", "October", "November", "December"]
                    # Reset month - 1 = current billing month
                    current_month = dt.month - 1 if dt.month > 1 else 12
                    current_year = dt.year if dt.month > 1 else dt.year - 1
                    period = f"{month_names[current_month - 1]} {current_year}"
                except Exception:
                    pass

    if credit_balance is not None or current_month_cost > 0:
        return AnthropicUsage(
            current_month_cost=current_month_cost,
            credit_balance=credit_balance,
            period=period,
            source="network"
        )

    return None


def _extract_from_elements(page) -> Optional[AnthropicUsage]:
    """Extract billing data using Playwright element selectors.

    More robust than regex on raw HTML - uses the visible text content.
    """
    try:
        # Get all visible text on the page
        body_text = page.locator("body").inner_text(timeout=5000)

        credit_balance = None
        current_month_cost = 0.0

        # Look for credit balance patterns in visible text
        # Common patterns: "US$3.56", "$3.56 remaining", "Credit Balance: $3.56"
        balance_patterns = [
            r'US\$(\d+\.?\d*)\s*(?:remaining|balance)',
            r'(?:remaining|balance)[:\s]*US?\$(\d+\.?\d*)',
            r'(?:credit|prepaid)[:\s]*US?\$(\d+\.?\d*)',
            r'US\$(\d+\.\d{2})',  # Any US$ amount as last resort
        ]

        for pattern in balance_patterns:
            match = re.search(pattern, body_text, re.IGNORECASE)
            if match:
                credit_balance = float(match.group(1))
                break

        # Look for monthly cost
        cost_patterns = [
            r'(?:this month|current month|monthly)[:\s]*\$?(\d+\.?\d*)',
            r'\$(\d+\.\d{2})\s*(?:this month|spent|used)',
        ]

        for pattern in cost_patterns:
            match = re.search(pattern, body_text, re.IGNORECASE)
            if match:
                current_month_cost = float(match.group(1))
                break

        # Look for billing period
        period = ""
        period_match = re.search(
            r'(January|February|March|April|May|June|July|August|'
            r'September|October|November|December)\s+\d{4}',
            body_text
        )
        if period_match:
            period = period_match.group(0)

        if credit_balance is not None or current_month_cost > 0:
            return AnthropicUsage(
                current_month_cost=current_month_cost,
                credit_balance=credit_balance,
                period=period,
                source="element"
            )

    except Exception as e:
        logger.debug(f"Element extraction failed: {e}")

    return None


def _extract_from_html_regex(content: str) -> Optional[AnthropicUsage]:
    """Legacy fallback: extract data from raw HTML using regex.

    Least reliable method but covers edge cases.
    """
    credit_balance = None
    cost = 0.0
    tokens = 0

    # Credit balance patterns
    us_dollar_matches = re.findall(r'US\$(\d+\.\d{2})', content)
    if us_dollar_matches:
        credit_balance = float(us_dollar_matches[0])

    if credit_balance is None:
        remaining_match = re.search(
            r'US\$(\d+(?:\.\d{2})?).*?(?:Remaining|Balance)',
            content, re.IGNORECASE | re.DOTALL
        )
        if remaining_match:
            credit_balance = float(remaining_match.group(1))

    # Cost patterns
    cost_matches = re.findall(r'\$(\d+(?:\.\d{2})?)', content)
    if cost_matches:
        cost = max(float(m) for m in cost_matches)

    # Token counts
    token_matches = re.findall(r'([\d,]+)\s*tokens?', content, re.IGNORECASE)
    for m in token_matches:
        cleaned = m.replace(',', '').strip()
        if cleaned and cleaned.isdigit():
            tokens = max(tokens, int(cleaned))

    # Period
    period = ""
    period_match = re.search(
        r'(January|February|March|April|May|June|July|August|'
        r'September|October|November|December)\s+\d{4}',
        content
    )
    if period_match:
        period = period_match.group(0)

    if credit_balance is not None or cost > 0:
        return AnthropicUsage(
            current_month_cost=cost,
            current_month_tokens=tokens,
            credit_balance=credit_balance,
            period=period,
            source="regex"
        )

    return None


def _is_login_page(page) -> bool:
    """Check if we've been redirected to a login page."""
    url = page.url.lower()
    return any(kw in url for kw in ["login", "sign-in", "signin", "auth"])


def get_anthropic_usage() -> Optional[AnthropicUsage]:
    """Scrape usage data from the Anthropic console.

    Uses a 3-tier extraction strategy:
    1. Network interception (most reliable - captures actual API JSON)
    2. Element extraction (uses visible page text via Playwright selectors)
    3. HTML regex (legacy fallback)

    Includes a circuit breaker: after 3 consecutive failures, skips scraping
    for 30 minutes to avoid blocking the event loop with repeated timeouts.

    Returns None if session is expired or all methods fail.
    """
    global _consecutive_failures, _circuit_open_until

    # Circuit breaker: skip if too many recent failures
    if _consecutive_failures >= _FAILURE_THRESHOLD:
        remaining = _circuit_open_until - time.monotonic()
        if remaining > 0:
            logger.info(f"Anthropic scraper circuit open — skipping ({remaining:.0f}s remaining)")
            return None
        else:
            logger.info("Anthropic scraper circuit half-open — retrying")

    if not PLAYWRIGHT_AVAILABLE:
        logger.warning("Playwright not available")
        return None

    if not STORAGE_PATH.exists():
        logger.warning(f"No session file at {STORAGE_PATH}")
        return None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)

            with open(STORAGE_PATH) as f:
                storage_state = json.load(f)

            context = browser.new_context(storage_state=storage_state)
            page = context.new_page()

            # Set up network interception before navigating
            captured = _intercept_api_data(page)

            # Try the new platform URL first (15s timeout, down from 30s)
            billing_url = BILLING_URL
            page.goto(billing_url, wait_until="domcontentloaded", timeout=15000)

            # If redirected to login, try legacy URL
            if _is_login_page(page):
                logger.info("Redirected to login on platform.claude.com, trying legacy URL")
                page.goto(LEGACY_BILLING_URL, wait_until="domcontentloaded", timeout=15000)

                if _is_login_page(page):
                    logger.warning("Session expired - redirected to login on both URLs")
                    _save_session(context)
                    browser.close()
                    _record_failure()
                    return None

            # Wait for key API responses to arrive (don't use networkidle - the
            # console has long-polling connections that prevent it from going idle)
            try:
                page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:
                pass  # Timeout is fine - API data is usually captured by now
            page.wait_for_timeout(1500)  # Extra buffer for slow API calls

            # Strategy 1: Try network-intercepted API data
            result = _extract_from_api_data(captured)
            if result:
                logger.info(f"Extracted via network interception: balance={result.credit_balance}")
                _save_session(context)
                browser.close()
                _record_success()
                return result

            # Strategy 2: Try element-based extraction
            result = _extract_from_elements(page)
            if result:
                logger.info(f"Extracted via elements: balance={result.credit_balance}")
                _save_session(context)
                browser.close()
                _record_success()
                return result

            # Strategy 3: Fall back to HTML regex
            content = page.content()
            result = _extract_from_html_regex(content)
            if result:
                logger.info(f"Extracted via regex: balance={result.credit_balance}")
                _save_session(context)
                browser.close()
                _record_success()
                return result

            # All strategies failed - log the page URL for debugging
            logger.warning(f"All extraction strategies failed. Page URL: {page.url}")
            logger.debug(f"Page title: {page.title()}")

            _save_session(context)
            browser.close()
            _record_failure()
            return None

    except Exception as e:
        logger.error(f"Error scraping Anthropic usage: {e}")
        _record_failure()
        return None


def _record_failure():
    """Record a scraper failure and open circuit if threshold reached."""
    global _consecutive_failures, _circuit_open_until
    _consecutive_failures += 1
    if _consecutive_failures >= _FAILURE_THRESHOLD:
        _circuit_open_until = time.monotonic() + _COOLDOWN_SECONDS
        logger.warning(
            f"Anthropic scraper circuit OPEN after {_consecutive_failures} failures "
            f"— cooling down for {_COOLDOWN_SECONDS}s"
        )


def _record_success():
    """Reset circuit breaker on success."""
    global _consecutive_failures, _circuit_open_until
    if _consecutive_failures > 0:
        logger.info(f"Anthropic scraper recovered after {_consecutive_failures} failures")
    _consecutive_failures = 0
    _circuit_open_until = 0.0


def _save_session(context):
    """Save updated session cookies after successful navigation."""
    try:
        state = context.storage_state()
        STORAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(STORAGE_PATH, "w") as f:
            json.dump(state, f)
        logger.debug("Updated session cookies saved")
    except Exception as e:
        logger.debug(f"Failed to save session: {e}")


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
