"""Subscriptions API for Peter Dashboard.

Provides endpoints for managing personal and business subscriptions:
- GET  /api/subscriptions           — List all with filters + summary stats
- GET  /api/subscriptions/upcoming  — Next 30 days renewals
- GET  /api/subscriptions/health    — Run health check (price changes, missed payments, new recurring)
- POST /api/subscriptions           — Create or update a subscription
- DELETE /api/subscriptions/{id}    — Delete a subscription
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

# Ensure project root on sys.path so we can import mcp_servers
_project_root = str(Path(__file__).parent.parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from mcp_servers.financial_data.supabase_client import finance_query, finance_count

import httpx

# Supabase config (reuse from financial_data)
from mcp_servers.financial_data.config import SUPABASE_URL, API_KEY

_REST = f"{SUPABASE_URL}/rest/v1"

router = APIRouter(prefix="/api/subscriptions", tags=["subscriptions"])


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class SubscriptionCreate(BaseModel):
    name: str
    provider: Optional[str] = None
    scope: str = "personal"
    category: Optional[str] = None
    amount: float
    currency: str = "GBP"
    frequency: str = "monthly"
    billing_day: Optional[int] = None
    next_renewal_date: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    auto_renew: bool = True
    cancellation_notice_days: Optional[int] = None
    payment_method: Optional[str] = None
    bank_description_pattern: Optional[str] = None
    status: str = "active"
    plan_tier: Optional[str] = None
    notes: Optional[str] = None
    url: Optional[str] = None


class SubscriptionUpdate(SubscriptionCreate):
    id: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _headers(*, write: bool = False) -> dict[str, str]:
    h = {
        "apikey": API_KEY,
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "Accept-Profile": "finance",
        "Content-Profile": "finance",
    }
    if write:
        h["Prefer"] = "return=representation"
    return h


def _annual_cost(amount: float, frequency: str) -> float:
    multipliers = {
        "weekly": 52,
        "fortnightly": 26,
        "monthly": 12,
        "quarterly": 4,
        "termly": 3,
        "annual": 1,
    }
    return amount * multipliers.get(frequency, 12)


def _monthly_cost(amount: float, frequency: str) -> float:
    return _annual_cost(amount, frequency) / 12


# ---------------------------------------------------------------------------
# GET /api/subscriptions
# ---------------------------------------------------------------------------
@router.get("")
async def list_subscriptions(
    scope: Optional[str] = Query(None, description="personal, business, or all"),
    status: Optional[str] = Query(None, description="active, paused, cancelled, trial"),
    category: Optional[str] = Query(None),
):
    params: dict[str, str] = {
        "select": "*",
        "order": "category.asc,name.asc",
    }
    if scope and scope != "all":
        params["scope"] = f"eq.{scope}"
    if status and status != "all":
        params["status"] = f"eq.{status}"
    if category:
        params["category"] = f"eq.{category}"

    rows = await finance_query("subscriptions", params, paginate=True)

    # Compute summary
    active = [r for r in rows if r.get("status") == "active"]
    total_monthly = sum(_monthly_cost(float(r["amount"]), r["frequency"]) for r in active)
    total_annual = sum(_annual_cost(float(r["amount"]), r["frequency"]) for r in active)
    personal_monthly = sum(
        _monthly_cost(float(r["amount"]), r["frequency"])
        for r in active if r.get("scope") == "personal"
    )
    business_monthly = sum(
        _monthly_cost(float(r["amount"]), r["frequency"])
        for r in active if r.get("scope") == "business"
    )

    # Category breakdown
    by_category: dict[str, dict] = {}
    for r in active:
        cat = r.get("category") or "Uncategorised"
        if cat not in by_category:
            by_category[cat] = {"count": 0, "monthly": 0.0}
        by_category[cat]["count"] += 1
        by_category[cat]["monthly"] += _monthly_cost(float(r["amount"]), r["frequency"])

    # Enrich rows with computed fields
    for r in rows:
        r["monthly_cost"] = round(_monthly_cost(float(r["amount"]), r["frequency"]), 2)
        r["annual_cost"] = round(_annual_cost(float(r["amount"]), r["frequency"]), 2)

    return {
        "subscriptions": rows,
        "summary": {
            "total_monthly": round(total_monthly, 2),
            "total_annual": round(total_annual, 2),
            "personal_monthly": round(personal_monthly, 2),
            "business_monthly": round(business_monthly, 2),
            "active_count": len(active),
            "total_count": len(rows),
            "by_category": by_category,
        },
    }


# ---------------------------------------------------------------------------
# GET /api/subscriptions/upcoming
# ---------------------------------------------------------------------------
@router.get("/upcoming")
async def upcoming_renewals(days: int = Query(30)):
    today = date.today()
    end = today + timedelta(days=days)

    rows = await finance_query("subscriptions", {
        "select": "*",
        "status": "eq.active",
        "next_renewal_date": f"gte.{today.isoformat()}",
        "order": "next_renewal_date.asc",
    })

    # Filter to within range
    upcoming = [
        r for r in rows
        if r.get("next_renewal_date") and r["next_renewal_date"] <= end.isoformat()
    ]

    for r in upcoming:
        r["monthly_cost"] = round(_monthly_cost(float(r["amount"]), r["frequency"]), 2)
        r["annual_cost"] = round(_annual_cost(float(r["amount"]), r["frequency"]), 2)

    return {"upcoming": upcoming, "days": days}


# ---------------------------------------------------------------------------
# GET /api/subscriptions/health
# ---------------------------------------------------------------------------
@router.get("/health")
async def subscription_health_check():
    """Run a full subscription health check.

    Returns alerts for price changes, missed payments, new recurring
    charges, cancellation windows, and upcoming renewals.
    """
    import re
    from collections import defaultdict

    today = date.today()
    alerts = []

    # 1. Get all subscriptions
    subs = await finance_query("subscriptions", {
        "select": "*",
        "order": "name.asc",
    }, paginate=True)

    active_subs = [s for s in subs if s.get("status") == "active"]

    # 2. Get last 6 months of outgoing transactions
    six_months_ago = (today - timedelta(days=180)).isoformat()
    all_txns = await finance_query("transactions", {
        "select": "description,amount,date",
        "amount": "lt.0",
        "date": f"gte.{six_months_ago}",
        "order": "date.desc",
    }, paginate=True)

    # 3. Analyse each tracked subscription
    tracked_patterns: list[str] = []
    for sub in active_subs:
        pattern = sub.get("bank_description_pattern")
        if not pattern:
            continue

        clean = pattern.replace("*", "").strip()
        if not clean:
            continue

        tracked_patterns.append(clean.lower())

        matching = [
            t for t in all_txns
            if clean.lower() in t.get("description", "").lower()
        ]

        if not matching:
            continue

        # Price change detection (10% tolerance for FX)
        stored_amount = abs(float(sub["amount"]))
        latest_txn = matching[0]
        latest_amount = abs(float(latest_txn["amount"]))

        if stored_amount > 0 and abs(latest_amount - stored_amount) / stored_amount > 0.10:
            alerts.append({
                "type": "price_change",
                "subscription": sub["name"],
                "subscription_id": sub["id"],
                "scope": sub.get("scope", "personal"),
                "old_amount": stored_amount,
                "new_amount": round(latest_amount, 2),
                "last_transaction_date": latest_txn["date"],
                "description": latest_txn["description"][:60],
            })

        # Missed payment detection
        freq = sub.get("frequency", "monthly")
        expected_gap_days = {
            "weekly": 10, "fortnightly": 20, "monthly": 45,
            "quarterly": 105, "termly": 140, "annual": 400,
        }.get(freq, 45)

        latest_date = date.fromisoformat(latest_txn["date"])
        days_since = (today - latest_date).days

        if days_since > expected_gap_days:
            alerts.append({
                "type": "missed_payment",
                "subscription": sub["name"],
                "subscription_id": sub["id"],
                "scope": sub.get("scope", "personal"),
                "amount": stored_amount,
                "frequency": freq,
                "last_payment_date": latest_txn["date"],
                "days_overdue": days_since - expected_gap_days,
            })

    # 4. Cancellation windows
    for sub in active_subs:
        notice_days = sub.get("cancellation_notice_days")
        renewal_date = sub.get("next_renewal_date")
        if not notice_days or not renewal_date:
            continue

        renewal = date.fromisoformat(renewal_date)
        deadline = renewal - timedelta(days=notice_days)
        if today <= deadline <= today + timedelta(days=14):
            alerts.append({
                "type": "cancellation_window",
                "subscription": sub["name"],
                "subscription_id": sub["id"],
                "scope": sub.get("scope", "personal"),
                "renewal_date": renewal_date,
                "cancellation_deadline": deadline.isoformat(),
                "amount": float(sub["amount"]),
                "frequency": sub.get("frequency", "monthly"),
            })

    # 5. Upcoming renewals (next 7 days)
    upcoming = []
    for sub in active_subs:
        renewal_date = sub.get("next_renewal_date")
        if not renewal_date:
            continue
        renewal = date.fromisoformat(renewal_date)
        if today <= renewal <= today + timedelta(days=7):
            upcoming.append({
                "name": sub["name"],
                "renewal_date": renewal_date,
                "amount": float(sub["amount"]),
                "frequency": sub.get("frequency", "monthly"),
                "scope": sub.get("scope", "personal"),
            })

    # 6. Detect new recurring transactions
    # Load user-dismissed exclusions
    exclusion_rows = await finance_query("subscription_exclusions", {
        "select": "description_pattern",
    })
    user_exclusions = [r["description_pattern"].lower() for r in exclusion_rows]

    groups: dict[str, list[dict]] = defaultdict(list)
    for t in all_txns:
        desc = t.get("description", "").strip()
        norm = re.sub(r"\s+\d{2,}[/-]\d{2,}.*$", "", desc.lower()).strip()
        norm = re.sub(r"\s+", " ", norm)
        if norm:
            groups[norm].append(t)

    # Exclude known non-subscription merchants (shops, restaurants, transport, etc.)
    _EXCLUDE_PATTERNS = {
        "aldi", "tesco", "sainsbury", "lidl", "asda", "waitrose", "co-op",
        "morrisons", "marks and spencer", "m&s", "ocado",
        "pret a manger", "costa", "starbucks", "greggs", "mcdonalds",
        "nandos", "pizza", "burger", "kitchen", "restaurant", "cafe",
        "bar ", "pub ", "deli", "bakery", "chippy",
        "tfl travel", "ringgo", "parking", "petrol", "shell", "bp ",
        "amazon marketplace", "amazon.co.uk", "ebay", "paypal",
        "hsbc", "non-sterling", "transaction fee", "interest",
        "atm", "cash", "withdrawal",
        "stocks green prima",  # school
        "burnhill",  # renovation
        "next directory",  # clothing
        "box bar",  # restaurant
        "se hildenborough",  # petrol station
        "accenture",  # work expenses
    }

    for desc, txs in groups.items():
        if len(txs) < 3:
            continue
        if "mmbill" in desc or "mmbil" in desc:
            continue
        # Skip excluded patterns
        if any(excl in desc for excl in _EXCLUDE_PATTERNS):
            continue
        # Skip user-dismissed exclusions
        if any(excl in desc for excl in user_exclusions):
            continue
        already_tracked = any(tp in desc for tp in tracked_patterns)
        if already_tracked:
            continue

        amounts = [abs(float(t["amount"])) for t in txs]
        avg = sum(amounts) / len(amounts)
        if avg < 2:
            continue

        # Subscription heuristic: consistent amounts (low coefficient of variation)
        # Real subs charge the same amount each time; shopping varies wildly
        if len(amounts) >= 3:
            std_dev = (sum((a - avg) ** 2 for a in amounts) / len(amounts)) ** 0.5
            cv = std_dev / avg if avg > 0 else 1
            # Skip if amounts vary by more than 20% (not a fixed subscription)
            if cv > 0.20:
                continue

        alerts.append({
            "type": "new_recurring",
            "description": txs[0].get("description", desc)[:60],
            "avg_amount": round(avg, 2),
            "occurrences": len(txs),
            "first_seen": txs[-1].get("date", ""),
            "latest": txs[0].get("date", ""),
        })

    # Summary
    total_monthly = sum(
        _monthly_cost(float(s["amount"]), s.get("frequency", "monthly"))
        for s in active_subs
    )

    return {
        "alerts": alerts,
        "upcoming_renewals": upcoming,
        "summary": {
            "total_active": len(active_subs),
            "total_monthly_cost": round(total_monthly, 2),
            "alerts_count": len(alerts),
            "scanned_transactions": len(all_txns),
        },
    }


# ---------------------------------------------------------------------------
# POST /api/subscriptions
# ---------------------------------------------------------------------------
@router.post("")
async def upsert_subscription(sub: SubscriptionCreate):
    body = sub.model_dump(exclude_none=True)

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{_REST}/subscriptions",
            headers={**_headers(write=True), "Prefer": "return=representation,resolution=merge-duplicates"},
            json=body,
        )
        if resp.status_code >= 400:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        return resp.json()


# ---------------------------------------------------------------------------
# PUT /api/subscriptions/{id}
# ---------------------------------------------------------------------------
@router.put("/{sub_id}")
async def update_subscription(sub_id: str, sub: SubscriptionCreate):
    body = sub.model_dump(exclude_none=True)
    body["updated_at"] = "now()"

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.patch(
            f"{_REST}/subscriptions?id=eq.{sub_id}",
            headers=_headers(write=True),
            json=body,
        )
        if resp.status_code >= 400:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        result = resp.json()
        if not result:
            raise HTTPException(status_code=404, detail="Subscription not found")
        return result[0]


# ---------------------------------------------------------------------------
# DELETE /api/subscriptions/{id}
# ---------------------------------------------------------------------------
@router.delete("/{sub_id}")
async def delete_subscription(sub_id: str):
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.delete(
            f"{_REST}/subscriptions?id=eq.{sub_id}",
            headers=_headers(write=True),
        )
        if resp.status_code >= 400:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        return {"deleted": True}


# ---------------------------------------------------------------------------
# GET /api/subscriptions/{id}/transactions
# ---------------------------------------------------------------------------
@router.get("/{sub_id}/transactions")
async def subscription_transactions(sub_id: str, limit: int = Query(20)):
    """Find matching bank transactions for a subscription using its bank_description_pattern."""
    # Get the subscription
    rows = await finance_query("subscriptions", {
        "select": "*",
        "id": f"eq.{sub_id}",
    })
    if not rows:
        raise HTTPException(status_code=404, detail="Subscription not found")

    sub = rows[0]
    pattern = sub.get("bank_description_pattern")

    if not pattern:
        return {"subscription": sub, "transactions": [], "message": "No bank pattern configured"}

    # Clean pattern for PostgREST ilike: strip wildcards from the pattern itself
    # PostgREST uses * as wildcard (maps to SQL %)
    clean = pattern.replace("*", "").strip()
    if not clean:
        return {"subscription": sub, "transactions": [], "message": "Pattern too broad"}

    # Search transactions using ilike pattern
    txns = await finance_query("transactions", {
        "select": "id,date,description,amount,category_id",
        "description": f"ilike.*{clean}*",
        "order": "date.desc",
        "limit": str(limit),
    })

    return {
        "subscription": sub,
        "transactions": txns,
        "match_count": len(txns),
    }
