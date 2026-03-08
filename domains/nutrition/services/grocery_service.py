"""Grocery shopping automation via Chrome CDP.

Connects to Chrome on port 9222 to automate Sainsbury's (and later Ocado).
Uses internal REST APIs via page.evaluate() for speed and reliability,
falling back to UI automation where needed.
"""

import asyncio
import json
import re
from datetime import datetime

from logger import logger

CDP_ENDPOINT = "http://localhost:9222"

STORES = {
    "sainsburys": {
        "name": "Sainsbury's",
        "base_url": "https://www.sainsburys.co.uk",
        "groceries_url": "https://www.sainsburys.co.uk/gol-ui/groceries",
        "slot_url": "https://www.sainsburys.co.uk/gol-ui/slot/book",
        "search_api": "/groceries-api/gol-services/product/v1/product",
        "basket_api": "/groceries-api/gol-services/basket/v2/basket",
        "slot_api": "/groceries-api/gol-services/slot/v2/slots",
        "min_order_pence": 2500,
        "slot_hold_minutes": 120,
    },
}


def _connect_browser():
    """Connect to Chrome via CDP. Returns (playwright, browser)."""
    from playwright.sync_api import sync_playwright
    p = sync_playwright().start()
    browser = p.chromium.connect_over_cdp(CDP_ENDPOINT)
    return p, browser


def _get_page(browser):
    """Get a new page in the existing browser context."""
    ctx = browser.contexts[0]
    return ctx.new_page()


# ============================================================
# Session Management
# ============================================================

def _check_sainsburys_login(page) -> bool:
    """Check if logged in to Sainsbury's by looking for login state."""
    page.goto(
        "https://www.sainsburys.co.uk/gol-ui/groceries",
        wait_until="domcontentloaded",
        timeout=20000,
    )
    page.wait_for_timeout(3000)
    body = page.inner_text("body")
    # Logged in shows "Welcome to Sainsbury's [name]"; logged out shows "Log in / Register"
    if "Log in / Register" in body:
        return False
    if "Welcome to Sainsbury" in body or "My account" in body or "Sign out" in body:
        return True
    return False


async def check_login(store: str) -> dict:
    """Check if Chris is logged in to the store."""
    def _check():
        p, browser = _connect_browser()
        try:
            page = _get_page(browser)
            try:
                if store == "sainsburys":
                    logged_in = _check_sainsburys_login(page)
                    return {
                        "store": store,
                        "logged_in": logged_in,
                        "login_url": "https://www.sainsburys.co.uk/gol-ui/groceries" if not logged_in else None,
                        "message": None if logged_in else "Please log in to Sainsbury's in Chrome, then retry.",
                    }
                else:
                    return {"store": store, "logged_in": False, "message": f"Store '{store}' not supported yet."}
            finally:
                page.close()
        finally:
            browser.close()
            p.stop()

    return await asyncio.to_thread(_check)


# ============================================================
# Product Search
# ============================================================

def _search_sainsburys(page, query: str, limit: int = 10) -> list[dict]:
    """Search Sainsbury's products via internal API."""
    # Navigate to Sainsbury's to get cookies in scope
    if "sainsburys.co.uk" not in page.url:
        page.goto(
            "https://www.sainsburys.co.uk/gol-ui/groceries",
            wait_until="domcontentloaded",
            timeout=20000,
        )
        page.wait_for_timeout(2000)

    # Call the internal API directly
    result = page.evaluate("""async (params) => {
        const resp = await fetch(
            '/groceries-api/gol-services/product/v1/product?filter[keyword]='
            + encodeURIComponent(params.query)
            + '&page_number=1&page_size=' + params.limit
            + '&sort_order=FAVOURITES_FIRST'
        );
        if (!resp.ok) return {error: resp.status, products: []};
        const data = await resp.json();
        return {
            products: (data.products || []).map(p => ({
                name: p.name,
                sain_id: p.sainId,
                product_uid: p.product_uid,
                price: p.retail_price ? p.retail_price.price : null,
                unit_price: p.unit_price ? p.unit_price.price : null,
                unit_measure: p.unit_price ? p.unit_price.measure : null,
                available: p.is_available,
                image: p.image,
                promotions: (p.promotions || []).map(pr => pr.strap_line || pr.description || ''),
                badges: (p.badges || []).map(b => b.text || ''),
            }))
        };
    }""", {"query": query, "limit": limit})

    return result.get("products", [])


async def search_products(store: str, query: str, limit: int = 10) -> list[dict]:
    """Search for products at the specified store."""
    def _search():
        p, browser = _connect_browser()
        try:
            page = _get_page(browser)
            try:
                if store == "sainsburys":
                    return _search_sainsburys(page, query, limit)
                else:
                    raise ValueError(f"Store '{store}' not supported yet")
            finally:
                page.close()
        finally:
            browser.close()
            p.stop()

    result = await asyncio.to_thread(_search)
    logger.info(f"Searched {store} for '{query}': {len(result)} results")
    return result


# ============================================================
# Slot Booking
# ============================================================

def _get_sainsburys_slots(page) -> dict:
    """Get available delivery slots from Sainsbury's.

    Requires login. Navigates to slot booking page and intercepts the /slot/v2/slots API.
    """
    slots_data = []

    def handle_response(response):
        url = response.url
        # Capture the slot API response — v2 endpoint
        if "slot/v2/slots" in url or "slot/v1" in url:
            try:
                data = response.json()
                slots_data.append({"url": url, "data": data})
            except Exception:
                pass

    page.on("response", handle_response)

    page.goto(
        "https://www.sainsburys.co.uk/gol-ui/slot/book",
        wait_until="domcontentloaded",
        timeout=20000,
    )
    page.wait_for_timeout(5000)

    # Check if redirected to login
    if "login" in page.url.lower() or "account.sainsburys" in page.url:
        return {"error": "not_logged_in", "slots": [], "message": "Please log in to Sainsbury's in Chrome first."}

    # If we got API data, parse it
    if slots_data:
        return _parse_sainsburys_slots(slots_data)

    # Fallback: try to read the slot data from the page DOM
    return _parse_sainsburys_slots_from_dom(page)


def _parse_sainsburys_slots(api_data: list[dict]) -> dict:
    """Parse slot availability from intercepted /slot/v2/slots API response.

    Actual API structure:
    {
        "slots": [
            {
                "start_time": "2026-03-10T07:00:00Z",
                "end_time": "2026-03-10T08:00:00Z",
                "price": 4.0,
                "is_available": true,
                "is_green": false,
                "slot_type": "saver_slot" | "1hour",
                "booking_key": "abc123...",
                ...
            },
            ...
        ],
        "weeks": [...],
        "slot_types": [...],
        "has_xmas_slots": false,
        "postcode": "...",
        ...
    }
    """
    all_slots = []

    for entry in api_data:
        data = entry.get("data", {})
        raw_slots = data.get("slots", [])

        if not isinstance(raw_slots, list):
            continue

        for slot in raw_slots:
            # Parse start_time to extract date
            start_time = slot.get("start_time", "")
            end_time = slot.get("end_time", "")
            date = ""
            if start_time:
                try:
                    dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
                    date = dt.strftime("%Y-%m-%d")
                    start_time = dt.strftime("%H:%M")
                except (ValueError, AttributeError):
                    pass
            if end_time:
                try:
                    dt = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
                    end_time = dt.strftime("%H:%M")
                except (ValueError, AttributeError):
                    pass

            all_slots.append({
                "date": date,
                "start": start_time,
                "end": end_time,
                "price": slot.get("price", 0),
                "available": slot.get("is_available", False),
                "type": _classify_slot_type(slot),
                "booking_key": slot.get("booking_key", ""),
                "is_green": slot.get("is_green", False),
            })

    # If we couldn't parse any slots but did capture data, return debug info
    if not all_slots and api_data:
        return {
            "slots": [],
            "raw_api_count": len(api_data),
            "raw_keys": [list(d.get("data", {}).keys()) for d in api_data[:3]],
            "message": "Captured API data but couldn't parse slot structure.",
        }

    available = [s for s in all_slots if s["available"]]
    saver_available = [s for s in available if s["type"] == "saver"]
    return {
        "slots": available,
        "total": len(all_slots),
        "available": len(available),
        "saver_available": len(saver_available),
    }


def _parse_sainsburys_slots_from_dom(page) -> dict:
    """Fallback: parse slots from the page DOM/accessibility tree."""
    body = page.inner_text("body")
    lines = [l.strip() for l in body.split("\n") if l.strip()]

    # Look for slot-like patterns: time ranges and prices
    slots = []
    current_date = None

    for line in lines:
        # Date headers like "Saturday 15 March"
        date_match = re.match(r"(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+(\d+\s+\w+)", line)
        if date_match:
            current_date = line
            continue

        # Slot times like "10:00 - 11:00" or "8:00am - 12:00pm"
        time_match = re.match(r"(\d{1,2}[:.]\d{2}\s*(?:am|pm)?)\s*[-–]\s*(\d{1,2}[:.]\d{2}\s*(?:am|pm)?)", line, re.IGNORECASE)
        if time_match and current_date:
            slots.append({
                "date": current_date,
                "start": time_match.group(1),
                "end": time_match.group(2),
                "type": "unknown",
                "raw_line": line,
            })

    return {
        "slots": slots,
        "source": "dom_fallback",
        "page_text_preview": body[:500],
    }


def _classify_slot_type(slot: dict) -> str:
    """Classify a slot as saver, standard, or green."""
    slot_type = str(slot.get("slot_type", slot.get("type", ""))).lower()
    description = str(slot.get("description", slot.get("strap_line", ""))).lower()

    if "saver" in slot_type or "saver" in description or "flexi" in slot_type:
        return "saver"
    if slot.get("is_green") or "green" in slot_type or "green" in description:
        return "green"
    return "standard"


async def get_slots(store: str, date: str = None, prefer: str = None) -> dict:
    """Get available delivery slots.

    Args:
        store: Store name (sainsburys)
        date: Optional date filter (YYYY-MM-DD)
        prefer: Optional preference (saver, standard)
    """
    def _get():
        p, browser = _connect_browser()
        try:
            page = _get_page(browser)
            try:
                if store == "sainsburys":
                    result = _get_sainsburys_slots(page)
                else:
                    raise ValueError(f"Store '{store}' not supported yet")

                # Filter by date if specified
                if date and result.get("slots"):
                    result["slots"] = [s for s in result["slots"] if date in s.get("date", "")]

                # Sort by preference
                if prefer and result.get("slots"):
                    if prefer == "saver":
                        result["slots"].sort(key=lambda s: (0 if s["type"] == "saver" else 1, s.get("price", 99)))
                    elif prefer == "standard":
                        result["slots"].sort(key=lambda s: (0 if s["type"] == "standard" else 1, s.get("price", 99)))

                return result
            finally:
                page.close()
        finally:
            browser.close()
            p.stop()

    result = await asyncio.to_thread(_get)
    logger.info(f"Got slots for {store}: {result.get('available', len(result.get('slots', [])))} available")
    return result


async def book_slot(store: str, booking_key: str) -> dict:
    """Book a delivery slot using the booking key from get_slots."""
    def _book():
        p, browser = _connect_browser()
        try:
            page = _get_page(browser)
            try:
                if store != "sainsburys":
                    raise ValueError(f"Store '{store}' not supported yet")

                # Navigate to Sainsbury's first to get cookies
                if "sainsburys.co.uk" not in page.url:
                    page.goto(
                        "https://www.sainsburys.co.uk/gol-ui/slot/book",
                        wait_until="domcontentloaded",
                        timeout=20000,
                    )
                    page.wait_for_timeout(3000)

                # Check login
                if "login" in page.url.lower() or "account.sainsburys" in page.url:
                    return {"error": "not_logged_in", "message": "Please log in to Sainsbury's in Chrome first."}

                # Book the slot via internal API
                result = page.evaluate("""async (bookingKey) => {
                    const resp = await fetch('/groceries-api/gol-services/slot/v2/slots/book', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({booking_key: bookingKey})
                    });
                    const data = await resp.json();
                    return {status: resp.status, ok: resp.ok, data: data};
                }""", booking_key)

                if result.get("ok"):
                    return {
                        "booked": True,
                        "booking_key": booking_key,
                        "message": "Slot booked successfully. You have 2 hours to complete your order.",
                        "details": result.get("data"),
                    }
                else:
                    return {
                        "booked": False,
                        "booking_key": booking_key,
                        "error": result.get("data", {}),
                        "status": result.get("status"),
                        "message": "Failed to book slot. It may have been taken.",
                    }
            finally:
                page.close()
        finally:
            browser.close()
            p.stop()

    result = await asyncio.to_thread(_book)
    logger.info(f"Slot booking for {store}: {'success' if result.get('booked') else 'failed'}")
    return result


# ============================================================
# Trolley Management
# ============================================================

def _add_to_sainsburys_trolley(page, product_uid: str, quantity: int = 1) -> dict:
    """Add a product to the Sainsbury's trolley via internal API.

    Extracts auth tokens inline from OIDC localStorage + cookies, then calls
    the basket API. This ensures tokens are always fresh.
    """
    result = page.evaluate("""async (params) => {
        // Extract auth tokens
        const oidcRaw = localStorage.getItem("oidc.user:https://account.sainsburys.co.uk:gol");
        if (!oidcRaw) return {status: 401, ok: false, data: {error: "no_oidc_token"}};
        const oidc = JSON.parse(oidcRaw);
        const token = oidc.access_token;
        if (!token) return {status: 401, ok: false, data: {error: "no_access_token"}};

        // Get WC auth token from cookies
        const cookies = document.cookie.split(";").map(c => c.trim());
        let wcToken = "";
        for (const c of cookies) {
            if (c.startsWith("WC_AUTHENTICATION_")) {
                wcToken = c.split("=").slice(1).join("=");
                break;
            }
        }

        const now = new Date().toISOString();
        const url = "/groceries-api/gol-services/basket/v2/basket/item"
            + "?pick_time=" + encodeURIComponent(now)
            + "&store_number=0020"
            + "&slot_booked=false";

        const resp = await fetch(url, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": "Bearer " + token,
                "wcauthtoken": wcToken
            },
            body: JSON.stringify({
                product_uid: params.product_uid,
                quantity: params.quantity,
                uom: "ea",
                selected_catchweight: ""
            })
        });
        const text = await resp.text();
        let data;
        try { data = JSON.parse(text); } catch(e) { data = {raw: text.substring(0, 300)}; }
        return {status: resp.status, ok: resp.ok, data: data};
    }""", {"product_uid": product_uid, "quantity": quantity})

    return result


async def get_trolley(store: str) -> dict:
    """Get the current trolley contents."""
    def _get():
        p, browser = _connect_browser()
        try:
            page = _get_page(browser)
            try:
                if store != "sainsburys":
                    raise ValueError(f"Store '{store}' not supported yet")

                if "sainsburys.co.uk" not in page.url:
                    page.goto(
                        "https://www.sainsburys.co.uk/gol-ui/groceries",
                        wait_until="domcontentloaded",
                        timeout=20000,
                    )
                    page.wait_for_timeout(2000)

                result = page.evaluate("""async () => {
                    const oidcRaw = localStorage.getItem("oidc.user:https://account.sainsburys.co.uk:gol");
                    if (!oidcRaw) return {error: "not_logged_in"};
                    const oidc = JSON.parse(oidcRaw);
                    const token = oidc.access_token;

                    const cookies = document.cookie.split(";").map(c => c.trim());
                    let wcToken = "";
                    for (const c of cookies) {
                        if (c.startsWith("WC_AUTHENTICATION_")) {
                            wcToken = c.split("=").slice(1).join("=");
                            break;
                        }
                    }

                    const resp = await fetch("/groceries-api/gol-services/basket/v2/basket", {
                        headers: {
                            "Accept": "application/json",
                            "Authorization": "Bearer " + token,
                            "wcauthtoken": wcToken
                        }
                    });
                    if (!resp.ok) return {error: "api_error", status: resp.status};
                    return await resp.json();
                }""")

                if "error" in result:
                    return result

                items = []
                for item in result.get("items", []):
                    product = item.get("product", {})
                    items.append({
                        "name": product.get("name", ""),
                        "quantity": item.get("quantity", 1),
                        "price": item.get("subtotal_price", 0),
                        "product_uid": product.get("sku", ""),
                        "image": product.get("image", ""),
                    })

                return {
                    "items": items,
                    "item_count": result.get("item_count", len(items)),
                    "subtotal": result.get("subtotal_price", 0),
                    "total": result.get("total_price", 0),
                    "savings": result.get("savings", 0),
                    "min_spend": result.get("minimum_spend", 0),
                    "exceeds_minimum": result.get("has_exceeded_minimum_spend", False),
                }
            finally:
                page.close()
        finally:
            browser.close()
            p.stop()

    return await asyncio.to_thread(_get)


def _strip_quantity_prefix(query: str) -> str:
    """Remove leading quantity/number from a query.

    '12 eggs' -> 'eggs', '500g chicken breast' -> 'chicken breast',
    '2 pints milk' -> 'milk', 'jar of olives' -> 'olives'
    """
    # Remove leading numbers + optional unit
    cleaned = re.sub(
        r"^\d+\s*(?:g|kg|ml|l|pints?|pack|packs|x|jar|jars|tin|tins|bag|bags|bunch|bunches|of\s+)*\s*",
        "",
        query,
        flags=re.IGNORECASE,
    ).strip()
    # Also handle "jar of", "tin of", "bag of" without a number
    cleaned = re.sub(
        r"^(?:jar|tin|bag|bunch|pack|box|bottle|carton|tub)\s+of\s+",
        "",
        cleaned,
        flags=re.IGNORECASE,
    ).strip()
    return cleaned if cleaned else query


def _match_score(query: str, product: dict) -> float:
    """Score how well a product matches a shopping list item query."""
    name = product.get("name", "").lower()
    query_lower = query.lower()

    # Also try with quantity prefix stripped
    stripped = _strip_quantity_prefix(query_lower)
    queries_to_try = [query_lower]
    if stripped != query_lower:
        queries_to_try.append(stripped)

    best_score = 0.0

    for q in queries_to_try:
        score = 0.0
        q_words = q.split()

        # Exact match
        if q == name:
            return 1.0

        # All query words appear in product name
        if all(w in name for w in q_words):
            score += 0.7
            # Bonus for shorter names (more specific match)
            score += max(0, 0.2 - len(name) / 500)
        else:
            # Partial word match
            matched = sum(1 for w in q_words if w in name)
            if q_words:
                score += 0.3 * (matched / len(q_words))

        # If original query had a quantity, check if it appears in the product name
        if query_lower != stripped:
            qty_match = re.match(r"^(\d+)", query_lower)
            if qty_match and qty_match.group(1) in name:
                score += 0.1

        best_score = max(best_score, score)

    # Prefer available products
    if not product.get("available", True):
        best_score *= 0.1

    # Prefer own-brand (Sainsbury's) for staples
    if "sainsbury" in name:
        best_score += 0.05

    return min(best_score, 1.0)


async def add_shopping_list(store: str, items: list[dict]) -> dict:
    """Add a shopping list to the store's trolley.

    Args:
        items: List of {name, quantity?, unit?, category?}

    Returns dict with matched, ambiguous, not_found lists.
    """
    def _add_list():
        p, browser = _connect_browser()
        try:
            page = _get_page(browser)
            try:
                if store != "sainsburys":
                    raise ValueError(f"Store '{store}' not supported yet")

                # Check login first
                if not _check_sainsburys_login(page):
                    return {"error": "not_logged_in", "message": "Please log in to Sainsbury's in Chrome first."}

                matched = []
                ambiguous = []
                not_found = []

                for item in items:
                    item_name = item.get("name", "")
                    # Try original query first, then stripped version
                    search_results = _search_sainsburys(page, item_name, limit=5)
                    stripped_name = _strip_quantity_prefix(item_name.lower())
                    if stripped_name != item_name.lower():
                        # Also search with the cleaned query and merge
                        extra = _search_sainsburys(page, stripped_name, limit=5)
                        seen_uids = {r["product_uid"] for r in search_results}
                        for r in extra:
                            if r["product_uid"] not in seen_uids:
                                search_results.append(r)

                    if not search_results:
                        not_found.append({"item": item_name, "reason": "no_results"})
                        continue

                    # Score each result
                    scored = [(prod, _match_score(item_name, prod)) for prod in search_results]
                    scored.sort(key=lambda x: x[1], reverse=True)

                    best_score = scored[0][1]
                    best_product = scored[0][0]

                    if best_score >= 0.7:
                        # Strong match — auto-add
                        add_result = _add_to_sainsburys_trolley(
                            page,
                            best_product["product_uid"],
                            quantity=1,
                        )
                        matched.append({
                            "item": item_name,
                            "product": {
                                "name": best_product["name"],
                                "price": best_product["price"],
                                "product_uid": best_product["product_uid"],
                            },
                            "score": round(best_score, 2),
                            "added": add_result.get("ok", False),
                        })
                    elif best_score >= 0.3:
                        # Ambiguous — present options
                        options = [
                            {
                                "name": prod["name"],
                                "price": prod["price"],
                                "product_uid": prod["product_uid"],
                                "score": round(sc, 2),
                            }
                            for prod, sc in scored[:3]
                            if sc >= 0.2
                        ]
                        ambiguous.append({"item": item_name, "options": options})
                    else:
                        not_found.append({
                            "item": item_name,
                            "reason": "no_good_match",
                            "best_match": best_product["name"],
                            "best_score": round(best_score, 2),
                        })

                return {
                    "matched": matched,
                    "ambiguous": ambiguous,
                    "not_found": not_found,
                    "summary": {
                        "total_items": len(items),
                        "auto_added": len(matched),
                        "needs_choice": len(ambiguous),
                        "not_found": len(not_found),
                    },
                }
            finally:
                page.close()
        finally:
            browser.close()
            p.stop()

    result = await asyncio.to_thread(_add_list)
    logger.info(
        f"Shopping list for {store}: {result.get('summary', {}).get('auto_added', 0)} added, "
        f"{result.get('summary', {}).get('needs_choice', 0)} ambiguous, "
        f"{result.get('summary', {}).get('not_found', 0)} not found"
    )
    return result
