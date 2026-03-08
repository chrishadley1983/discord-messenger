"""Weekly price cache for common proteins and staples.

Caches Sainsbury's prices to avoid repeated API calls during meal plan generation.
Refreshed by the price-scanner scheduled job (Monday 06:00).
"""

import json
import asyncio
from datetime import datetime
from pathlib import Path

from logger import logger

CACHE_FILE = Path(__file__).resolve().parents[3] / "data" / "price_cache.json"

# Common proteins and staples to scan
SCAN_ITEMS = [
    # Proteins
    "chicken breast", "chicken thighs", "minced beef", "beef steak",
    "pork chops", "pork mince", "lamb mince", "lamb chops",
    "salmon fillets", "cod fillets", "prawns", "tuna steaks",
    "tofu", "halloumi",
    # Key staples
    "pasta", "rice", "bread", "eggs", "milk", "butter", "cheese",
    "onions", "potatoes", "tomatoes", "peppers",
]


def load_cache() -> dict:
    """Load the price cache from disk."""
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text())
        except (json.JSONDecodeError, IOError):
            return {"items": [], "scanned_at": None}
    return {"items": [], "scanned_at": None}


def save_cache(data: dict):
    """Save the price cache to disk."""
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(data, indent=2))


async def scan_prices(store: str = "sainsburys") -> dict:
    """Scan prices for all common items. Called by price-scanner scheduled job."""
    from domains.nutrition.services.grocery_service import search_products

    results = []
    for item_name in SCAN_ITEMS:
        try:
            products = await search_products(store, item_name, limit=3)
            if products:
                best = products[0]
                on_offer = bool(best.get("promotions"))
                results.append({
                    "item": item_name,
                    "product": best.get("name", ""),
                    "price": best.get("price"),
                    "unit_price": best.get("unit_price"),
                    "unit_measure": best.get("unit_measure"),
                    "on_offer": on_offer,
                    "offer_text": best["promotions"][0] if best.get("promotions") else None,
                })
            else:
                results.append({"item": item_name, "product": None, "price": None, "on_offer": False})
        except Exception as e:
            logger.warning(f"Price scan failed for '{item_name}': {e}")
            results.append({"item": item_name, "error": str(e)})

    cache_data = {
        "items": results,
        "scanned_at": datetime.now().isoformat(),
        "store": store,
        "on_offer_count": sum(1 for r in results if r.get("on_offer")),
        "deals": [r for r in results if r.get("on_offer")],
    }

    save_cache(cache_data)
    logger.info(f"Price scan complete: {len(results)} items, {cache_data['on_offer_count']} on offer")
    return cache_data


def get_cached_prices() -> dict:
    """Get the most recent price cache."""
    return load_cache()


def get_deals() -> list[dict]:
    """Get items currently on offer from the cache."""
    cache = load_cache()
    return cache.get("deals", [])
