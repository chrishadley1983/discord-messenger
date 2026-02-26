#!/usr/bin/env python3
"""Scrape ALL Vercel usage metrics from the dashboard.

The Vercel v2 API on Hobby plans doesn't expose most metrics (Fluid Active CPU,
ISR, Edge Request CPU Duration, etc.). This script scrapes the full usage table
via Playwright and stores each metric in Supabase for the vercel-usage cron to read.

Usage:
    python scripts/scrape_vercel_usage.py            # Headless scrape (default)
    python scripts/scrape_vercel_usage.py --setup     # Headed browser for login
    python scripts/scrape_vercel_usage.py --check     # Validate session is alive

Exit codes:
    0 - Success
    1 - General error
    2 - Session expired (needs re-login via --setup)
"""

import argparse
import asyncio
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root
load_dotenv(Path(__file__).parent.parent / ".env")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")  # service-role key
DISCORD_WEBHOOK_ALERTS = os.getenv("DISCORD_WEBHOOK_ALERTS")

SESSIONS_DIR = Path(__file__).parent.parent / "data" / "browser_sessions"
PROFILE_DIR = SESSIONS_DIR / "vercel_profile"
SCREENSHOT_PATH = Path(__file__).parent.parent / "data" / "vercel_usage_screenshot.png"

USAGE_URL = "https://vercel.com/chrishadley1983s-projects/~/usage"
LOGIN_URL = "https://vercel.com/login"

# Billing period starts on the 13th
BILLING_START_DAY = 13

# ---------------------------------------------------------------------------
# Metric configuration: dashboard name → (scraped_metrics key, target unit)
# Only metrics with a limit on the dashboard are included.
# ---------------------------------------------------------------------------
METRIC_CONFIG = {
    "Fast Data Transfer":           ("vercel_fast_data_transfer", "GB"),
    "Fast Origin Transfer":         ("vercel_fast_origin_transfer", "GB"),
    "Edge Requests":                ("vercel_edge_requests", "count"),
    "Edge Request CPU Duration":    ("vercel_edge_request_cpu_duration", "seconds"),
    "Microfrontends Routing":       ("vercel_microfrontends_routing", "count"),
    "ISR Reads":                    ("vercel_isr_reads", "count"),
    "ISR Writes":                   ("vercel_isr_writes", "count"),
    "Function Invocations":         ("vercel_function_invocations", "count"),
    "Function Duration":            ("vercel_function_duration", "GB-Hrs"),
    "Fluid Provisioned Memory":     ("vercel_fluid_provisioned_memory", "GB-Hrs"),
    "Fluid Active CPU":             ("vercel_fluid_active_cpu", "seconds"),
    "Edge Function Execution Units": ("vercel_edge_function_execution_units", "count"),
    "Edge Middleware Invocations":   ("vercel_edge_middleware_invocations", "count"),
    "Blob Data Storage":            ("vercel_blob_data_storage", "GB"),
    "Blob Simple Operations":       ("vercel_blob_simple_operations", "count"),
}


# ---------------------------------------------------------------------------
# Billing period
# ---------------------------------------------------------------------------

def _get_billing_period() -> tuple[str, str]:
    """Return (start_date, end_date) as ISO date strings for the current billing period."""
    now = datetime.now(timezone.utc)
    if now.day >= BILLING_START_DAY:
        start = now.replace(day=BILLING_START_DAY)
        if now.month == 12:
            end = now.replace(year=now.year + 1, month=1, day=BILLING_START_DAY - 1)
        else:
            end = now.replace(month=now.month + 1, day=BILLING_START_DAY - 1)
    else:
        if now.month == 1:
            start = now.replace(year=now.year - 1, month=12, day=BILLING_START_DAY)
        else:
            start = now.replace(month=now.month - 1, day=BILLING_START_DAY)
        end = now.replace(day=BILLING_START_DAY - 1)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Value parsing
# ---------------------------------------------------------------------------

def _parse_time_to_seconds(text: str) -> float | None:
    """Parse time-like text into seconds.

    Handles: "3h 13m", "1h", "45m", "33s", "1h 23m 45s"
    """
    hours = minutes = secs = 0
    h = re.search(r'(\d+)\s*h', text)
    m = re.search(r'(\d+)\s*m(?!i)', text)  # 'm' but not 'mi' (million)
    s = re.search(r'(\d[\d,]*)\s*s', text)

    if not (h or m or s):
        return None

    if h:
        hours = int(h.group(1))
    if m:
        minutes = int(m.group(1))
    if s:
        secs = int(s.group(1).replace(",", ""))
    return hours * 3600 + minutes * 60 + secs


def _parse_value_text(text: str) -> tuple[float | None, str]:
    """Parse a single value like '1.45 GB', '278K', '3h 13m', '120.5 GB-Hrs'.

    Returns (numeric_value, detected_unit).
    """
    text = text.strip()
    if not text:
        return None, ""

    # Time format: "3h 13m", "33s", "1h"
    if re.search(r'\d+\s*[hms]', text) and not re.search(r'GB|MB|KB', text):
        val = _parse_time_to_seconds(text)
        if val is not None:
            return val, "seconds"

    # GB-Hrs format
    if 'GB-Hrs' in text or 'GB-hrs' in text:
        num = re.search(r'[\d.,]+', text)
        return (float(num.group().replace(',', '')), "GB-Hrs") if num else (None, "")

    # GB format (but not GB-Hrs)
    if re.search(r'GB\b', text) and 'GB-' not in text:
        num = re.search(r'[\d.,]+', text)
        return (float(num.group().replace(',', '')), "GB") if num else (None, "")

    # MB format
    if re.search(r'MB\b', text):
        num = re.search(r'[\d.,]+', text)
        return (float(num.group().replace(',', '')) / 1024, "GB") if num else (None, "")

    # B (bytes) format — convert to GB
    if re.search(r'\d\s*B\b', text) and 'GB' not in text and 'MB' not in text:
        num = re.search(r'[\d.,]+', text)
        val = float(num.group().replace(',', '')) if num else 0
        return val / (1024 ** 3), "GB"

    # K suffix (thousands)
    if re.search(r'[\d.,]+\s*K\b', text):
        num = re.search(r'[\d.,]+', text)
        return (float(num.group().replace(',', '')) * 1_000, "count") if num else (None, "")

    # M suffix (millions)
    if re.search(r'[\d.,]+\s*M\b', text):
        num = re.search(r'[\d.,]+', text)
        return (float(num.group().replace(',', '')) * 1_000_000, "count") if num else (None, "")

    # Plain number
    num = re.match(r'^[\d.,]+$', text)
    if num:
        return float(text.replace(',', '')), "count"

    return None, ""


def _parse_usage_text(usage_text: str) -> tuple[float | None, str]:
    """Parse 'current / limit' format, returning parsed current value and unit."""
    if '/' in usage_text:
        current_text = usage_text.split('/')[0].strip()
    else:
        current_text = usage_text.strip()
    return _parse_value_text(current_text)


def _name_to_key(name: str) -> str:
    """Convert metric name to scraped_metrics key.

    'Fluid Active CPU' → 'vercel_fluid_active_cpu'
    """
    slug = re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')
    return f"vercel_{slug}"


# ---------------------------------------------------------------------------
# Discord alerts
# ---------------------------------------------------------------------------

def _send_discord_alert(message: str):
    """Send alert to Discord #alerts channel."""
    if not DISCORD_WEBHOOK_ALERTS:
        print(f"[ALERT] {message}")
        return
    try:
        import httpx
        httpx.post(DISCORD_WEBHOOK_ALERTS, json={"content": message}, timeout=10)
    except Exception as e:
        print(f"Failed to send Discord alert: {e}")


# ---------------------------------------------------------------------------
# Supabase upsert
# ---------------------------------------------------------------------------

async def _upsert_to_supabase(records: list[dict]) -> bool:
    """Batch upsert scraped metrics to Supabase."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("SUPABASE_URL or SUPABASE_KEY not set — skipping upsert")
        return False
    if not records:
        print("No records to upsert")
        return False

    import httpx

    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates",
    }

    url = f"{SUPABASE_URL}/rest/v1/scraped_metrics?on_conflict=key"

    async with httpx.AsyncClient() as client:
        resp = await client.post(url, headers=headers, json=records, timeout=15)

    if resp.status_code in (200, 201):
        print(f"Upserted {len(records)} metrics to Supabase")
        return True
    else:
        print(f"Supabase upsert failed: {resp.status_code} {resp.text}")
        return False


# ---------------------------------------------------------------------------
# Page parsing
# ---------------------------------------------------------------------------

def _extract_metrics_from_text(body_text: str) -> list[tuple[str, float, str]]:
    """Parse the usage page text to extract (name, value, unit) tuples.

    The Vercel usage page renders metrics in two formats:
    1. Split format (compact table):
         Fast Data Transfer    ← metric name
         1.45 GB               ← current value
         /                     ← separator (own line)
         100 GB                ← limit
    2. Combined format (detailed sections):
         Fast Data Transfer
         ...description text...
         1.45 GB / 100 GB      ← value / limit on one line

    We detect both formats and deduplicate by metric name (first match wins).
    """
    lines = [l.strip() for l in body_text.split('\n') if l.strip()]
    results_by_name: dict[str, tuple[float, str]] = {}

    # --- Strategy 1: Split format (value, /, limit on separate lines) ---
    # Find lines that are just "/" and look at context
    for i, line in enumerate(lines):
        if line != '/':
            continue
        # line i is "/", line i-1 should be current value, line i+1 should be limit
        if i < 2 or i + 1 >= len(lines):
            continue

        current_text = lines[i - 1]
        # Validate current_text looks like a value (digits present, short)
        if not re.search(r'\d', current_text) or len(current_text) > 30:
            continue

        # Find the metric name: go back from the value line
        name = None
        for j in range(i - 2, max(0, i - 6), -1):
            candidate = lines[j]
            if not candidate or len(candidate) > 80:
                continue
            # Skip lines that look like values or limits
            if re.match(r'^[\d.,\s/KMGBTBHhms\-]+$', candidate):
                continue
            # Skip known non-name lines
            if candidate.lower() in ('product', 'usage', 'overview', 'pro', 'enterprise'):
                continue
            # Check if this is a known metric name
            if candidate in METRIC_CONFIG:
                name = candidate
                break
            # Also check if it looks like a metric name (starts with upper, reasonable length)
            if re.match(r'^[A-Z]', candidate) and len(candidate) < 50:
                name = candidate
                break

        if name and name not in results_by_name:
            value, unit = _parse_value_text(current_text)
            if value is not None:
                results_by_name[name] = (value, unit)

    # --- Strategy 2: Combined format (value / limit on one line) ---
    for i, line in enumerate(lines):
        if '/' not in line or not re.search(r'\d', line):
            continue
        if line == '/':
            continue  # Already handled above

        parts = line.split('/')
        if len(parts) != 2:
            continue
        left, right = parts[0].strip(), parts[1].strip()
        if not re.search(r'\d', left) or not re.search(r'\d', right):
            continue

        # Find the metric name by looking backwards
        name = None
        for j in range(i - 1, max(0, i - 5), -1):
            candidate = lines[j]
            if not candidate or len(candidate) > 80:
                continue
            if re.match(r'^[\d.,\s/KMGBTBHhms\-]+$', candidate):
                continue
            if candidate.lower() in ('product', 'usage', 'overview', 'pro', 'enterprise'):
                continue
            if candidate in METRIC_CONFIG:
                name = candidate
                break
            if re.match(r'^[A-Z]', candidate) and len(candidate) < 50:
                name = candidate
                break

        if name and name not in results_by_name:
            value, unit = _parse_usage_text(line)
            if value is not None:
                results_by_name[name] = (value, unit)

    return [(name, val, unit) for name, (val, unit) in results_by_name.items()]


# ---------------------------------------------------------------------------
# Browser modes
# ---------------------------------------------------------------------------

async def setup(headed: bool = True):
    """Open browser for manual Vercel login."""
    from playwright.async_api import async_playwright

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print("  Vercel Dashboard Login Setup")
    print(f"{'='*60}\n")

    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=not headed,
            viewport={"width": 1280, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
        )

        page = browser.pages[0] if browser.pages else await browser.new_page()
        print(f"Navigating to {LOGIN_URL}...")
        await page.goto(LOGIN_URL, wait_until="networkidle")

        print(f"\n{'*'*60}")
        print("  MANUAL ACTION REQUIRED")
        print(f"{'*'*60}")
        print("\n  1. Log in to Vercel in the browser window")
        print("  2. Complete any verification if prompted")
        print("  3. Once logged in, PRESS ENTER here to save")
        print(f"\n{'*'*60}\n")

        import threading
        input_received = threading.Event()

        def wait_for_input():
            input("  Press ENTER when logged in... ")
            input_received.set()

        t = threading.Thread(target=wait_for_input, daemon=True)
        t.start()

        while not input_received.is_set():
            await asyncio.sleep(0.5)

        print("  Session saved (persistent context).")
        await browser.close()
        return True


async def check_session() -> bool:
    """Validate that the Vercel session is still active."""
    from playwright.async_api import async_playwright

    if not PROFILE_DIR.exists():
        print("No profile directory found. Run --setup first.")
        return False

    print("Checking Vercel session...")

    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=True,
            viewport={"width": 1280, "height": 900},
        )

        page = browser.pages[0] if browser.pages else await browser.new_page()

        try:
            await page.goto(USAGE_URL, wait_until="networkidle", timeout=30000)
            current_url = page.url

            if "/login" in current_url or "/signup" in current_url:
                print("Session EXPIRED — redirected to login page.")
                await browser.close()
                return False

            content = await page.text_content("body")
            if content and "usage" in content.lower():
                print("Session VALID — usage page loaded.")
                await browser.close()
                return True

            print(f"Session UNKNOWN — ended up at {current_url}")
            await browser.close()
            return False

        except Exception as e:
            print(f"Session check failed: {e}")
            await browser.close()
            return False


async def scrape() -> int:
    """Scrape all usage metrics from the Vercel dashboard.

    Returns exit code: 0=success, 1=error, 2=session expired.
    """
    from playwright.async_api import async_playwright

    if not PROFILE_DIR.exists():
        print("No profile directory. Run --setup first.")
        _send_discord_alert(
            "**Vercel Scraper** — No browser profile found. "
            "Run `python scripts/scrape_vercel_usage.py --setup` to log in."
        )
        return 1

    print(f"Scraping Vercel usage from {USAGE_URL}...")

    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=True,
            viewport={"width": 1280, "height": 900},
        )

        page = browser.pages[0] if browser.pages else await browser.new_page()

        try:
            await page.goto(USAGE_URL, wait_until="networkidle", timeout=45000)
            current_url = page.url

            # Session expired?
            if "/login" in current_url or "/signup" in current_url:
                print("Session expired — redirected to login.")
                _send_discord_alert(
                    "**Vercel Scraper** — Session expired. "
                    "Run `python scripts/scrape_vercel_usage.py --setup` to re-login."
                )
                await browser.close()
                return 2

            # Scroll to bottom to ensure all metrics are loaded
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(2000)
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(1000)

            # Get full page text
            body_text = await page.inner_text("body")

            # Extract all metrics
            raw_metrics = _extract_metrics_from_text(body_text)

            if not raw_metrics:
                SCREENSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
                await page.screenshot(path=str(SCREENSHOT_PATH), full_page=True)
                print(f"No metrics found on page. Screenshot saved to {SCREENSHOT_PATH}")
                _send_discord_alert(
                    "**Vercel Scraper** — No metrics found on usage page. "
                    "Page structure may have changed. Screenshot saved."
                )
                await browser.close()
                return 1

            # Match to known metrics and build upsert records
            period_start, period_end = _get_billing_period()
            now_iso = datetime.now(timezone.utc).isoformat()
            records = []
            matched = 0
            unmatched = []

            for name, value, unit in raw_metrics:
                # Try exact match first, then fuzzy
                config = METRIC_CONFIG.get(name)
                if not config:
                    # Try case-insensitive / partial match
                    for cfg_name, cfg in METRIC_CONFIG.items():
                        if cfg_name.lower() == name.lower():
                            config = cfg
                            break

                if config:
                    key, target_unit = config
                    records.append({
                        "key": key,
                        "value": value,
                        "unit": target_unit,
                        "scraped_at": now_iso,
                        "billing_period_start": period_start,
                        "billing_period_end": period_end,
                    })
                    matched += 1
                    print(f"  {name}: {value} {unit}")
                else:
                    unmatched.append(name)

            if unmatched:
                print(f"  Unmatched metrics (skipped): {', '.join(unmatched)}")

            print(f"\nMatched {matched}/{len(raw_metrics)} metrics")

            if not records:
                print("No known metrics matched — check page structure")
                _send_discord_alert(
                    "**Vercel Scraper** — Found metrics but none matched known names. "
                    "Dashboard may have changed."
                )
                await browser.close()
                return 1

            # Upsert to Supabase
            success = await _upsert_to_supabase(records)
            await browser.close()
            return 0 if success else 1

        except Exception as e:
            print(f"Scrape failed: {e}")
            try:
                SCREENSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
                await page.screenshot(path=str(SCREENSHOT_PATH), full_page=True)
            except Exception:
                pass
            _send_discord_alert(f"**Vercel Scraper** — Error: {e}")
            await browser.close()
            return 1


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

async def main():
    parser = argparse.ArgumentParser(description="Scrape Vercel usage metrics")
    parser.add_argument("--setup", action="store_true", help="Open headed browser for login")
    parser.add_argument("--check", action="store_true", help="Check if session is valid")
    args = parser.parse_args()

    if args.setup:
        success = await setup()
        sys.exit(0 if success else 1)

    if args.check:
        valid = await check_session()
        sys.exit(0 if valid else 1)

    # Default: headless scrape
    exit_code = await scrape()
    sys.exit(exit_code)


if __name__ == "__main__":
    asyncio.run(main())
