"""MCP Server for Keepa Amazon Pricing Data.

Provides tools to look up Amazon UK pricing data via the Keepa API:
- Current buy box price, Amazon price, sales rank, offer counts
- 90-day average prices (was90)
- Price history over time
- EAN/UPC to ASIN lookup
- Token balance monitoring

Usage:
    python mcp_servers/keepa_mcp.py
"""

import os
import sys
import time
import json
from datetime import datetime
from typing import Optional

import httpx

# Add project root to path for .env loading
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

KEEPA_API_KEY = os.environ.get("KEEPA_API_KEY", "")
KEEPA_BASE_URL = "https://api.keepa.com"
KEEPA_DOMAIN = 2  # Amazon UK

# Keepa timestamps are minutes since 2011-01-01
KEEPA_EPOCH_MINUTES = 21564000


def _keepa_ts_to_date(keepa_minutes: int) -> str:
    unix_s = (keepa_minutes + KEEPA_EPOCH_MINUTES) * 60
    return datetime.utcfromtimestamp(unix_s).strftime("%Y-%m-%d")


def _price_to_gbp(raw: int | None) -> float | None:
    if raw is None or raw < 0:
        return None
    return round(raw / 100, 2)


# CSV indices from Keepa docs
CSV_AMAZON = 0
CSV_NEW = 1
CSV_USED = 2
CSV_SALES_RANK = 3
CSV_COUNT_NEW = 11
CSV_BUY_BOX = 18


# ---------------------------------------------------------------------------
# Keepa API helpers
# ---------------------------------------------------------------------------

_last_request = 0.0
_tokens_left = 999


async def _keepa_get(path: str, params: dict) -> dict:
    """Make a GET request to the Keepa API with rate limiting."""
    global _last_request, _tokens_left

    if not KEEPA_API_KEY:
        return {"error": "KEEPA_API_KEY not configured in environment"}

    # Minimum 2s between requests
    elapsed = time.time() - _last_request
    if elapsed < 2.0:
        time.sleep(2.0 - elapsed)

    params["key"] = KEEPA_API_KEY
    params["domain"] = str(KEEPA_DOMAIN)

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{KEEPA_BASE_URL}/{path}", params=params)

        if resp.status_code == 429:
            return {"error": "Rate limited (429). Wait a minute and try again."}
        resp.raise_for_status()

        data = resp.json()
        _last_request = time.time()
        _tokens_left = data.get("tokensLeft", _tokens_left)

        if data.get("error"):
            return {"error": data["error"].get("message", str(data["error"]))}

        return data


def _extract_current_pricing(product: dict) -> dict:
    """Extract current pricing summary from a Keepa product object."""
    stats = product.get("stats") or {}
    current = stats.get("current") or []
    avg90 = stats.get("avg90") or []
    avg30 = stats.get("avg30") or []

    def stat(arr, idx):
        if idx < len(arr):
            v = arr[idx]
            if v is not None and v >= 0:
                return v
        return None

    buy_box_raw = stat(current, CSV_BUY_BOX)
    amazon_raw = stat(current, CSV_AMAZON)
    new_raw = stat(current, CSV_NEW)
    used_raw = stat(current, CSV_USED)
    sales_rank_raw = stat(current, CSV_SALES_RANK)
    offer_count_raw = stat(current, CSV_COUNT_NEW)

    was90_bb_raw = stat(avg90, CSV_BUY_BOX)
    was90_amazon_raw = stat(avg90, CSV_AMAZON)
    was30_bb_raw = stat(avg30, CSV_BUY_BOX)

    return {
        "asin": product.get("asin"),
        "title": product.get("title"),
        "buy_box_price": _price_to_gbp(buy_box_raw),
        "amazon_price": _price_to_gbp(amazon_raw),
        "lowest_new_price": _price_to_gbp(new_raw),
        "lowest_used_price": _price_to_gbp(used_raw),
        "sales_rank": sales_rank_raw,
        "new_offer_count": offer_count_raw,
        "was90_buy_box_avg": _price_to_gbp(was90_bb_raw),
        "was90_amazon_avg": _price_to_gbp(was90_amazon_raw),
        "was30_buy_box_avg": _price_to_gbp(was30_bb_raw),
        "ean_list": product.get("eanList") or [],
        "tokens_left": _tokens_left,
    }


def _extract_price_history(product: dict, days: int = 90) -> dict:
    """Extract price history from Keepa CSV data."""
    csv_data = product.get("csv") or []

    def parse_csv_pairs(csv_index: int) -> list[dict]:
        if csv_index >= len(csv_data) or csv_data[csv_index] is None:
            return []
        raw = csv_data[csv_index]
        points = []
        for i in range(0, len(raw) - 1, 2):
            ts, val = raw[i], raw[i + 1]
            if val >= 0:
                points.append({"date": _keepa_ts_to_date(ts), "value": val})
        return points

    # Filter to requested days
    cutoff = datetime.utcnow().strftime("%Y-%m-%d")
    from datetime import timedelta
    cutoff_date = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")

    def filter_recent(points):
        return [p for p in points if p["date"] >= cutoff_date]

    buy_box_pts = filter_recent(parse_csv_pairs(CSV_BUY_BOX))
    amazon_pts = filter_recent(parse_csv_pairs(CSV_AMAZON))
    new_pts = filter_recent(parse_csv_pairs(CSV_NEW))
    rank_pts = filter_recent(parse_csv_pairs(CSV_SALES_RANK))

    # Convert prices to GBP (rank stays as-is)
    for pts in [buy_box_pts, amazon_pts, new_pts]:
        for p in pts:
            p["value"] = _price_to_gbp(p["value"])

    return {
        "asin": product.get("asin"),
        "title": product.get("title"),
        "days": days,
        "buy_box_history": buy_box_pts[-50:],  # Cap to avoid huge responses
        "amazon_price_history": amazon_pts[-50:],
        "lowest_new_history": new_pts[-50:],
        "sales_rank_history": rank_pts[-50:],
        "tokens_left": _tokens_left,
    }


# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "keepa-amazon-pricing",
    instructions=(
        "Amazon UK pricing data via Keepa API. Use these tools when Chris asks about "
        "Amazon prices, buy box, sales rank (BSR), price history, was90 averages, "
        "or needs to look up an ASIN from an EAN/UPC barcode. "
        "All prices are in GBP (Amazon UK). Each lookup costs ~3 Keepa tokens."
    ),
)


@mcp.tool()
async def product_lookup(asins: str) -> str:
    """Look up current Amazon UK pricing for one or more ASINs.

    Returns: buy box price, Amazon price, lowest new/used, sales rank (BSR),
    offer count, 90-day and 30-day averages, and EAN codes.

    Args:
        asins: One or more ASINs, comma-separated (max 10). Example: "B0CXXX1234" or "B0CXXX1234,B0CYYY5678"

    Use when Chris asks: "What's the buy box on [ASIN]?", "Check Amazon price for...",
    "What's the BSR?", "How much is [set] on Amazon?"
    """
    asin_list = [a.strip().upper() for a in asins.split(",") if a.strip()]
    if not asin_list:
        return "No ASINs provided."
    if len(asin_list) > 10:
        return "Maximum 10 ASINs per lookup."

    data = await _keepa_get("product", {
        "asin": ",".join(asin_list),
        "stats": "90",
        "buybox": "1",
        "history": "0",
    })

    if "error" in data:
        return f"Keepa error: {data['error']}"

    products = data.get("products") or []
    if not products:
        return f"No products found for: {', '.join(asin_list)}"

    results = [_extract_current_pricing(p) for p in products]

    lines = []
    for r in results:
        lines.append(f"## {r['title'] or r['asin']}")
        lines.append(f"**ASIN:** {r['asin']}")
        lines.append(f"**Buy Box:** £{r['buy_box_price']}" if r['buy_box_price'] else "**Buy Box:** N/A")
        lines.append(f"**Amazon Price:** £{r['amazon_price']}" if r['amazon_price'] else "**Amazon Price:** N/A")
        lines.append(f"**Lowest New:** £{r['lowest_new_price']}" if r['lowest_new_price'] else "**Lowest New:** N/A")
        lines.append(f"**Lowest Used:** £{r['lowest_used_price']}" if r['lowest_used_price'] else "**Lowest Used:** N/A")
        lines.append(f"**Sales Rank (BSR):** {r['sales_rank']:,}" if r['sales_rank'] else "**Sales Rank:** N/A")
        lines.append(f"**New Offers:** {r['new_offer_count']}" if r['new_offer_count'] else "**New Offers:** N/A")
        lines.append(f"**Was90 (Buy Box Avg):** £{r['was90_buy_box_avg']}" if r['was90_buy_box_avg'] else "**Was90 BB:** N/A")
        lines.append(f"**Was30 (Buy Box Avg):** £{r['was30_buy_box_avg']}" if r['was30_buy_box_avg'] else "**Was30 BB:** N/A")
        lines.append(f"**Was90 (Amazon Avg):** £{r['was90_amazon_avg']}" if r['was90_amazon_avg'] else "**Was90 Amazon:** N/A")
        if r['ean_list']:
            lines.append(f"**EANs:** {', '.join(r['ean_list'][:5])}")
        lines.append(f"\n*Tokens remaining: {r['tokens_left']}*")
        lines.append("")

    return "\n".join(lines)


@mcp.tool()
async def price_history(asin: str, days: int = 90) -> str:
    """Get price history for an ASIN over a time period.

    Shows buy box, Amazon price, lowest new, and sales rank trends.
    Returns up to 50 data points per metric.

    Args:
        asin: A single ASIN (e.g. "B0CXXX1234")
        days: Number of days of history (default 90, max 365)

    Use when Chris asks: "Show me the price trend for...", "Has the price dropped?",
    "What's the price history?", "Is this a good time to buy?"
    """
    asin = asin.strip().upper()
    days = min(max(days, 7), 365)

    data = await _keepa_get("product", {
        "asin": asin,
        "stats": "90",
        "buybox": "1",
        "history": "1",
    })

    if "error" in data:
        return f"Keepa error: {data['error']}"

    products = data.get("products") or []
    if not products:
        return f"No product found for ASIN: {asin}"

    result = _extract_price_history(products[0], days)

    lines = [f"## Price History: {result['title'] or asin} ({result['days']} days)"]

    if result['buy_box_history']:
        lines.append(f"\n**Buy Box** ({len(result['buy_box_history'])} points):")
        for p in result['buy_box_history'][-10:]:
            lines.append(f"  {p['date']}: £{p['value']}")
        if len(result['buy_box_history']) > 10:
            lines.append(f"  ... ({len(result['buy_box_history']) - 10} earlier points omitted)")

    if result['amazon_price_history']:
        lines.append(f"\n**Amazon Price** ({len(result['amazon_price_history'])} points):")
        for p in result['amazon_price_history'][-10:]:
            lines.append(f"  {p['date']}: £{p['value']}")

    if result['sales_rank_history']:
        lines.append(f"\n**Sales Rank** ({len(result['sales_rank_history'])} points):")
        for p in result['sales_rank_history'][-10:]:
            lines.append(f"  {p['date']}: #{p['value']:,}")

    lines.append(f"\n*Tokens remaining: {result['tokens_left']}*")
    return "\n".join(lines)


@mcp.tool()
async def search_by_code(codes: str) -> str:
    """Look up ASINs from EAN or UPC barcodes.

    Useful when you have a barcode but not the Amazon ASIN.
    Returns matched products with their ASINs and titles.

    Args:
        codes: One or more EAN/UPC codes, comma-separated (max 100).
               Example: "5702017100708" or "5702017100708,5702017153162"

    Use when Chris asks: "What ASIN is this EAN?", "Look up this barcode on Amazon",
    "Find the Amazon listing for EAN..."
    """
    code_list = [c.strip() for c in codes.split(",") if c.strip()]
    if not code_list:
        return "No codes provided."
    if len(code_list) > 100:
        return "Maximum 100 codes per lookup."

    data = await _keepa_get("product", {
        "code": ",".join(code_list),
        "history": "0",
        "stats": "90",
    })

    if "error" in data:
        return f"Keepa error: {data['error']}"

    products = data.get("products") or []
    if not products:
        return f"No products found for codes: {', '.join(code_list[:5])}"

    lines = [f"Found {len(products)} product(s):\n"]
    for p in products:
        pricing = _extract_current_pricing(p)
        lines.append(f"**{pricing['title'] or 'Unknown'}**")
        lines.append(f"  ASIN: {pricing['asin']}")
        if pricing['buy_box_price']:
            lines.append(f"  Buy Box: £{pricing['buy_box_price']}")
        if pricing['sales_rank']:
            lines.append(f"  BSR: {pricing['sales_rank']:,}")
        if pricing['ean_list']:
            lines.append(f"  EANs: {', '.join(pricing['ean_list'][:3])}")
        lines.append("")

    lines.append(f"*Tokens remaining: {_tokens_left}*")
    return "\n".join(lines)


@mcp.tool()
async def token_balance() -> str:
    """Check your remaining Keepa API token balance.

    Useful to see how many lookups you have left before needing to wait.
    Each product lookup costs ~3 tokens. Tokens refill at ~20/minute.

    Use when Chris asks: "How many Keepa tokens do I have?", "Can I do more lookups?"
    """
    data = await _keepa_get("product", {
        "asin": "B000P6FLPY",  # Cheap lookup just to check balance
        "history": "0",
        "stats": "0",
    })

    if "error" in data:
        return f"Keepa error: {data['error']}"

    tokens = data.get("tokensLeft", "unknown")
    refill_rate = data.get("refillRate", "unknown")
    refill_in = data.get("refillIn", "unknown")

    return (
        f"**Keepa Token Balance**\n"
        f"Tokens remaining: {tokens}\n"
        f"Refill rate: {refill_rate} tokens/minute\n"
        f"Next refill in: {refill_in}ms"
    )


if __name__ == "__main__":
    mcp.run()
